# SyntheticShield — Fraud Fusion Scoring Engine: Implementation Specification

> **Audience:** Claude Code (implementation agent).
> **Purpose:** Implement the complete fraud-confidence scoring pipeline for SyntheticShield exactly as specified here. Where this document defines a rule, table, formula, or threshold, implement it verbatim — do NOT substitute your own values, invent additional signals, or "improve" the logic. All weights/thresholds live in a config file so the team can calibrate later without code changes.
> **Stack context:** Python 3.11+, FastAPI, SQLAlchemy, local SQLite. This engine is a backend module invoked after a claim's evidence is uploaded at FNOL. No LLM is used anywhere in this scoring path.

---

## 0. Core Design Principles (non-negotiable invariants)

1. **Deterministic.** Same inputs → same score, always. No randomness, no LLM calls, no time-dependent logic inside scoring (timestamps are *inputs*, compared deterministically). Any float math uses plain IEEE-754; round only at the final display step.
2. **Decomposable.** Every final score must decompose into its sub-scores and every sub-score into its individual findings. The engine returns a full `ScoreBreakdown` object (schema in §7) that the SIU explanation panel renders. If a finding didn't contribute points, it isn't in the breakdown.
3. **Worst-signal escalation.** One near-certain fake signal must never be averaged away (§6.3).
4. **The engine only routes; it never denies.** Output is a score + routing band. There is no "reject" output anywhere in this module.
5. **Append-only persistence.** Score results are INSERTed, never UPDATEd or DELETEd. Re-scoring a claim (e.g., on reappeal with new evidence) creates a new score row with an incremented `version`.
6. **Config-driven.** All weights, penalty values, thresholds, and escalation parameters come from `scoring_config.yaml` (§8), loaded once at startup, validated with pydantic. The config carries a `config_version` string that is stored with every score row.
7. **Fail-safe on errors.** If any analyzer fails (vendor API down, corrupt file), that sub-score is marked `status="unavailable"` and the fusion re-normalizes over available signals (§6.4). An analyzer failure must NEVER cause auto-approval by silently producing a 0 sub-score, and must never crash the pipeline.

---

## 1. Pipeline Overview

For each claim, evidence is analyzed in three levels, producing six sub-scores, each on a 0–100 scale where **higher = more fraud-suspicious**:

| Sub-score | Source | Level |
|---|---|---|
| `S_metadata` | In-house metadata forensics (all files) | Level 1 — Metadata Analysis |
| `S_image` | **In-house pixel-level forensic analysis** of photos | Level 2 — AI Manipulation Analysis |
| `S_video` | **In-house pixel-level (frame-level) forensic analysis** of video | Level 2 — AI Manipulation Analysis |
| `S_audio` | **Foreign detector:** Resemble AI Detect API | Level 2 — AI Manipulation Analysis |
| `S_text` | **Foreign detectors:** GPTZero (primary) + Pangram (cross-check) | Level 2 — AI Manipulation Analysis |
| `S_consistency` | In-house cross-evidence rules + reverse image search + per-part price verification | Level 3 — Consistency Check |

Then: normalization → weighted fusion → worst-signal escalation → routing (§6).

**Architecture note (current product decision):** images and video are analyzed **in-house** using published classical-forensics methods (no vendor API call, no model training). Audio and text use foreign detector APIs only. After every image/video analysis, a **reverse image search** runs (internal hash match first, external web search second). The claim-amount check is **per-damaged-part** price verification. All external integrations sit behind the swappable provider pattern (§9).

```
uploads ──► Level 1: MetadataAnalyzer ──────────────► S_metadata
        ├─► Level 2: ImagePixelAnalyzer (in-house) ─► S_image
        ├─► Level 2: VideoPixelAnalyzer (in-house) ─► S_video
        ├─► Level 2: AudioDetector (Resemble API) ──► S_audio
        ├─► Level 2: TextDetector (GPTZero+Pangram)─► S_text
        └─► Level 3: ConsistencyEngine ─────────────► S_consistency
                 (facts x-check, weather, reverse
                  image search, per-part pricing)
                            │
                            ▼
              FusionEngine: normalize → Σ wᵢ·Sᵢ → escalation → route
                            │
                            ▼
        ScoreBreakdown JSON + routing band → append-only `claim_scores` table
```

---

## 2. Module Layout

Create this structure (adjust root to the existing backend package):

```
app/scoring/
  __init__.py
  config.py            # pydantic models + YAML loader for scoring_config.yaml
  models.py            # dataclasses/pydantic: Finding, SubScore, ScoreBreakdown, RoutingDecision
  orchestrator.py      # run_scoring(claim_id) — coordinates all analyzers, calls fusion, persists
  level1_metadata/
    analyzer.py        # MetadataAnalyzer (images, video, audio, pdf)
    exif_rules.py      # rule functions, one per anomaly check
    pdf_rules.py
  level2_manipulation/
    image_pixel.py     # ImagePixelAnalyzer: ELA, JPEG-DQ, noise/PRNU-consistency, frequency artifacts, copy-move
    video_pixel.py     # VideoPixelAnalyzer: frame sampling + per-frame image analysis + temporal checks
    providers/
      base.py          # DetectorProvider ABC: detect(file) -> ProviderResult
      resemble_audio.py
      gptzero_text.py
      pangram_text.py
  level3_consistency/
    engine.py          # ConsistencyEngine
    fact_extraction.py # transcript + written statement → structured IncidentFacts
    weather.py         # weather provider (swappable)
    reverse_search.py  # internal pHash/SHA-256 match + external web reverse search (swappable)
    part_pricing.py    # per-part market price lookup via SerpApi (swappable)
  fusion.py            # normalize, weighted sum, worst-signal escalation, routing
  persistence.py       # append-only writes to claim_scores + score_findings tables
scoring_config.yaml
tests/scoring/         # see §10
```

---

## 3. Level 1 — Metadata Analysis (`S_metadata`)

### 3.1 What it does
Extract metadata from every uploaded file and run rule checks. Each triggered rule emits a `Finding` with penalty (or credit) points. `S_metadata = clamp(sum(points), 0, 100)`.

Libraries: `exifread` or `Pillow` + `piexif` for EXIF; `pymediainfo` or `ffprobe` (subprocess) for video/audio containers; `pypdf` for PDF metadata; `hashlib` for SHA-256.

### 3.2 Rule table (implement each as a separate pure function returning `Finding | None`)

Severity tiers and default points (all values read from config; defaults shown):

**HIGH severity (+35 each, config key `metadata.high`):**
| Rule ID | Check |
|---|---|
| `M-H1` | Editing-software trace on purportedly original capture: EXIF `Software`/XMP `CreatorTool` matches known editor list (`Photoshop`, `GIMP`, `Lightroom`, `Snapseed`, `Canva`, `Pixelmator`, `Affinity`) OR XMP history (`xmpMM:History`) shows edit operations. |
| `M-H2` | GPS contradiction: EXIF GPS present AND haversine distance from claimed incident location > `metadata.gps_radius_km` (default 25 km). |
| `M-H3` | Impossible timestamp: `DateTimeOriginal` is in the future relative to submission time, OR after the claim's submission timestamp, OR before vehicle policy start where incident date is claimed after policy start. |
| `M-H4` | Duplicate evidence: SHA-256 exact match OR perceptual-hash (pHash, hamming distance ≤ `metadata.phash_threshold`, default 6) match against any file from a *different* prior claim in the internal DB. |
| `M-H5` | Screenshot signature: image dimensions exactly match a known device screen resolution AND no camera Make/Model AND filename or metadata indicates screenshot (`Screenshot`, `PNG` with no EXIF from a "photo" upload). |

**MEDIUM severity (+20 each, config key `metadata.medium`):**
| Rule ID | Check |
|---|---|
| `M-M1` | `DateTimeOriginal` vs file `ModifyDate` differ by > `metadata.modify_gap_hours` (default 1h) AND any editor/software tag present. |
| `M-M2` | Timezone inconsistency: GPS longitude implies a timezone whose local time is inconsistent with EXIF local timestamp by > 2 hours. |
| `M-M3` | PDF re-saved in different tool: `Creator` and `Producer` indicate different applications, OR PDF has ≥ 2 cross-reference revisions (incremental updates after creation). |
| `M-M4` | Camera Make/Model absent on a file the claimant flow labels as "captured now" (in-app capture), where EXIF should exist. |

**LOW severity (+8 each, config key `metadata.low`):**
| Rule ID | Check |
|---|---|
| `M-L1` | Missing EXIF entirely on an uploaded (not in-app-captured) photo. **Deliberately weak**: WhatsApp/Instagram/Signal strip EXIF benignly. NEVER raise this tier. |
| `M-L2` | Generic `Producer` like `Microsoft: Print To PDF` / browser print on a document claimed to be an official/original document. |

**CREDITS (negative points):**
| Rule ID | Check | Points |
|---|---|---|
| `M-C1` | Valid C2PA manifest verified (use `c2pa-python` if available; else skip rule, do not fake it) | −25 |
| `M-C2` | Intact camera EXIF (Make+Model+DateTimeOriginal+GPS) all consistent with claim time/place | −8 |

Rules are independent; sum all triggered points then clamp to [0, 100]. Each `Finding` records: `rule_id`, `severity`, `points`, `file_id`, `human_readable` (one sentence, e.g., `"Photo IMG_2201.jpg carries an Adobe Photoshop software tag but was submitted as an original capture."`).

---

## 4. Level 2 — AI Manipulation Analysis

### 4.1 `S_image` — In-house pixel-level analysis (NO vendor API)

Implement `ImagePixelAnalyzer.analyze(image_path) -> SubScore` composed of four independent, published classical-forensics checks. Each check returns a component score 0–100; combine as a **weighted mean** with component weights from config (`image_pixel.component_weights`, defaults below), then that value is `S_image` for the file; for multiple photos, `S_image` for the claim = **max over files** (the most suspicious photo governs).

Libraries: `Pillow`, `numpy`, `opencv-python-headless`, `scipy`.

**Component 1 — Error Level Analysis (ELA), weight 0.20.**
Re-save the image as JPEG quality 92 to an in-memory buffer; compute per-pixel absolute difference vs original; normalize difference to 0–255. Compute the ratio `r = (95th percentile of block-mean differences) / (median block-mean difference + ε)` over 8×8 blocks. Map: `score = clamp((r - r0) / (r1 - r0), 0, 1) * 100` with `r0=2.0`, `r1=8.0` (config `image_pixel.ela`). Rationale: localized bright regions in ELA (splice candidates) push the 95th percentile far above the median. ELA is *suggestive only* — its component weight is deliberately the lowest.

**Component 2 — JPEG Double-Quantization (DQ) detection, weight 0.35.**
For JPEG inputs: extract luminance DCT-coefficient histograms per frequency (use `jpegio` if installable, else decode DCT via `cv2` on 8×8 blocks of the Y channel). Compute FFT of each low-frequency coefficient histogram; detect periodic peaks (peak-to-mean spectral ratio). `score = clamp((peak_ratio - p0)/(p1 - p0), 0, 1) * 100`, defaults `p0=2.5`, `p1=10.0`. If the file is not JPEG (PNG/HEIC), mark this component `not_applicable` and re-normalize component weights over applicable components. This is the mathematically strongest signal (Popescu & Farid 2004; Lin et al. 2009) — hence the largest weight.

**Component 3 — Noise/sensor-consistency analysis (PRNU-style residual check), weight 0.25.**
Denoise with a wavelet or bilateral filter; residual = original − denoised. Split image into a 4×4 grid; compute residual variance per cell; flag inconsistency when `max_cell_var / (median_cell_var + ε) > n0` (default `n0=4.0`, full score at `n1=12.0`, linear in between). True per-camera PRNU fingerprinting needs reference images — we implement *intra-image noise consistency* only. Name it "noise-consistency (PRNU-style)" in findings; never claim device fingerprinting.

**Component 4 — Generative-artifact frequency analysis, weight 0.20.**
Compute 2-D DFT of the grayscale image; azimuthally average the power spectrum into a 1-D radial profile; detect (a) abnormal high-frequency roll-off flatness and (b) periodic spectral spikes characteristic of upsampling in GAN/diffusion generators. Score via the same linear ramp pattern with config bounds (`freq.f0=0.15`, `freq.f1=0.45` on a normalized spike-energy metric). Also check: complete absence of JPEG blocking on a `.jpg` claimed as camera-original (cameras always leave blocking) → if detected, floor this component at 60.

`SubScore.human_readable` must name which components fired, e.g., `"Rear-damage photo: double-quantization periodicity (82/100) and noise inconsistency in lower-left region (71/100) indicate localized editing."`

### 4.2 `S_video` — In-house frame-level analysis (NO vendor API)

`VideoPixelAnalyzer.analyze(video_path) -> SubScore`:
1. Probe with `ffprobe`; reject/flag non-video containers (that's a metadata finding `M-M4`-style, not a crash).
2. Sample frames at `video_pixel.fps_sample` (default 1 frame/second, cap `video_pixel.max_frames` = 60) via `ffmpeg`/`cv2.VideoCapture`.
3. Run the **image component battery (§4.1)** on each sampled frame → per-frame score.
4. Temporal checks across consecutive sampled frames:
   - **Noise-profile discontinuity:** z-score of frame-residual variance sequence; a spike > 3σ on ≥ `video_pixel.min_anomalous_frames` (default 3) frames → temporal component score ramps 0→100 over 3→10 anomalous frames.
   - **Optical-flow discontinuity:** `cv2.calcOpticalFlowFarneback` between consecutive sampled frames; flag physically implausible global-flow reversals/jumps (config-bounded ramp).
5. `S_video = 0.7 * (95th percentile of per-frame scores) + 0.3 * temporal_component`, clamped [0,100].

### 4.3 `S_audio` — Foreign detector: Resemble AI Detect

Provider class `ResembleAudioProvider(DetectorProvider)`:
- `detect(file) -> ProviderResult(raw_score: float in [0,1], label: str, latency_ms, provider_name, provider_version)`.
- Endpoint/key from env (`AUDIO_DETECTOR_PROVIDER=resemble`, `RESEMBLE_API_KEY`). Timeout `providers.timeout_s` (default 30 s), retries: 2 with exponential backoff.
- `S_audio = raw_score * 100` (Resemble outputs probability-of-fake; verify direction against the API docs at integration time — if the API returns probability-of-REAL, invert: `S = (1 - raw) * 100`. Put the direction in the provider class as an explicit constant `SCORE_IS_FAKE_PROBABILITY = True`, asserted in tests).
- Multiple audio files: claim-level `S_audio = max` over files.
- On API failure after retries → `SubScore(status="unavailable")` (§6.4).

### 4.4 `S_text` — Foreign detectors: GPTZero + Pangram cross-check

Providers `GPTZeroTextProvider`, `PangramTextProvider`, run on: the written claim description, any extracted PDF text > `text.min_chars` (default 300 chars).
- Both return probability-of-AI in [0,1] → scale to 0–100.
- **Cross-check combination rule (implement exactly):**
  - If both available: `S_text = min(g, p) if |g - p| <= 25 else (g + p) / 2`, where `g`,`p` are the two 0–100 scores. Rationale: agreement gate — when they agree, trust the conservative (lower) one to suppress false positives; when they disagree strongly, average and let a `Finding` note the disagreement.
  - If one available: use it, add a `Finding(rule_id="T-SINGLE", points=0)` noting single-detector mode.
  - If none: `status="unavailable"`.
- Text below `text.min_chars` → `status="not_applicable"` (people write short descriptions; do not score them).

---

## 5. Level 3 — Consistency Check (`S_consistency`)

`ConsistencyEngine.analyze(claim) -> SubScore`. Additive penalties, clamp [0,100]. AI models may be used ONLY for *fact extraction* (speech-to-text, damage localization) — the comparisons/judgments below are fixed deterministic rules.

### 5.1 Fact extraction (inputs to the rules)
`IncidentFacts` extracted from (a) voice-statement transcript (speech-to-text; store transcript), (b) written description, (c) image damage localization (from §4.1 pipeline, a simple damage-region classifier or the in-house analyzer's region flags), (d) structured claim fields (incident type, date/time, location, claimed amount, damaged parts list):
```python
@dataclass
class IncidentFacts:
    source: str                      # "voice" | "written" | "photos" | "claim_form"
    incident_type: str | None        # "rear_end" | "side_impact" | "front_collision" | "parked" | "theft" | "weather" | "other"
    impact_zone: str | None          # "front" | "rear" | "left" | "right" | "roof" | "multiple"
    incident_dt: datetime | None
    location: tuple[float,float] | None
    weather_claimed: str | None      # "hail" | "storm" | "rain" | "flood" | None
    damaged_parts: list[str]         # normalized part names, e.g. "rear_bumper"
```
Extraction keyword maps live in `fact_extraction.py` as explicit dictionaries (deterministic; no LLM).

### 5.2 Rule table

| Rule ID | Check | Points |
|---|---|---|
| `C-H1` | Hard narrative contradiction: `impact_zone(voice)` vs `impact_zone(written)` vs `impact_zone(photos)` — any pairwise hard conflict (front vs rear; left vs right) | +45 per conflicting pair (max one award per pair type) |
| `C-H2` | Weather contradiction: `weather_claimed` set AND historical weather API for `location`,`incident_dt` shows no such event within `consistency.weather_window_h` (default ±6h) | +45 |
| `C-H3` | **Reverse image search — external web match:** any claim photo found on the public web predating the incident (see §5.3) | +50 AND mark finding `escalation_eligible=True` (this signal participates in worst-signal escalation with its own sub-score of `max(S_consistency, 92)` — see §6.3 note) |
| `C-M1` | Temporal mismatch: media `DateTimeOriginal` earlier than claimed `incident_dt` by > `consistency.temporal_gap_h` (default 2h) | +25 |
| `C-M2` | **Per-part price inflation** (§5.4): for any part, `claimed_part_cost / market_estimate` ≥ 2.0 | +15 per part at ratio ≥2, +30 per part at ratio ≥4 (cap +45 total from this rule) |
| `C-M3` | Damage-pattern implausibility: `incident_type` vs `impact_zone` mismatch per a fixed compatibility matrix (e.g., `parked` scrape incompatible with `roof` damage; `rear_end` incompatible with front-only damage) | +25 |
| `C-L1` | Minor narrative discrepancy (times differ < 2h between sources; part list differs by one minor item) | +10 |

### 5.3 Reverse image search (runs after EVERY image/video analysis)
Order (privacy-preserving):
1. **Internal first (always):** SHA-256 + pHash of every photo and sampled video keyframe vs the internal `evidence_hashes` table (all prior claims). Match → this is metadata rule `M-H4` (do not double-count here).
2. **External second (conditional):** send to the external reverse-search provider ONLY if `consistency.external_reverse_search: "always" | "suspicious_only"` — default `suspicious_only`, meaning only when the claim's provisional base (computed with available sub-scores) ≥ 15 or any single sub-score ≥ 50. Provider behind `ReverseSearchProvider` ABC (SerpApi Google Lens/Images endpoint as default implementation; swappable). A confident match on a third-party website (marketplace, news, stock, prior social post) → rule `C-H3`. Store matched URL(s) in the finding.

### 5.4 Per-part price verification
`PartPricingProvider` (SerpApi default, swappable):
- For each `damaged_part` with a claimed line-item cost: query market price for `"{year} {make} {model} {part} replacement cost {region}"`; parse top shopping/result prices; `market_estimate = median` of parsed prices; require ≥ 3 price points else mark part `estimate_unavailable` (no penalty — never penalize on missing market data).
- Cache lookups per (make, model, part, region) for `pricing.cache_days` (default 7).
- Also compute `payout_cap = min(total_claimed, sum(market_estimates_where_available) * (1 + pricing.labor_buffer) , coverage_limit)` with `labor_buffer` default 0.35. The cap is informational output (`ScoreBreakdown.payout_cap`) — it does NOT affect the fraud score.

---

## 6. Fusion Engine (`fusion.py`)

### 6.1 Normalization
All sub-scores are already produced on 0–100 with higher = more suspicious. `normalize()` therefore: (a) clamps to [0,100]; (b) asserts orientation via provider constants; (c) is the single place min-max rescaling would be added if a future provider outputs another scale. Keep it as an explicit function even while it is near-identity — tests pin its behavior.

### 6.2 Weighted base score
Default weights (config `fusion.weights`, MUST sum to 1.0 — validate at startup, raise on mismatch):
```yaml
image: 0.22
video: 0.22
audio: 0.18
consistency: 0.20
metadata: 0.10
text: 0.08
```
`Base = Σ wᵢ · Sᵢ` over sub-scores with `status == "ok"`.

### 6.3 Worst-signal escalation
```
E = fusion.escalation_threshold   # default 90
d = fusion.escalation_discount    # default 5
S_max = max over ok sub-scores of Sᵢ,
        ALSO considering any finding with escalation_eligible=True
        as a virtual signal of value max(its subscore, 92)   # C-H3 external web match
if S_max >= E:
    Final = max(Base, S_max - d)
else:
    Final = Base
Final = clamp(Final, 0, 100)
```
Record in the breakdown whether escalation fired, from which signal, and both `Base` and `Final`.

### 6.4 Missing / unavailable sub-scores (re-normalization)
For sub-scores with `status in ("unavailable", "not_applicable")` (vendor outage, no video submitted, short text):
- Drop them from the weighted sum and **re-normalize remaining weights to sum to 1.0** (`wᵢ' = wᵢ / Σ w_available`).
- If **either S_image or S_video analysis is unavailable due to an internal error** (not merely absent media), force routing band to at least HUMAN REVIEW regardless of Final (set `RoutingDecision.forced_review_reason`). Absent media that the FNOL flow marks optional does NOT force review; failed analysis of present media does.
- If ≥ 3 of the 6 sub-scores are unavailable → force HUMAN REVIEW.

### 6.5 Routing (deterministic thresholds, config `fusion.routing`)
```
Final < 15            → band = "AUTO_APPROVE"
15 <= Final <= 85     → band = "HUMAN_REVIEW"
Final > 85            → band = "SIU_INVESTIGATION"
```
Apply `forced_review_reason` overrides (§6.4) by raising `AUTO_APPROVE → HUMAN_REVIEW` (never downgrade a band). The engine emits the band; downstream workflow (moderator UI, SIU quorum) is outside this module. **No code path may output a denial.**

---

## 7. Data Contracts & Persistence

```python
class Finding(BaseModel):
    rule_id: str; severity: Literal["high","medium","low","credit","info"]
    points: float; file_id: str | None
    human_readable: str
    escalation_eligible: bool = False
    extra: dict = {}          # e.g. matched URLs, distances, ratios

class SubScore(BaseModel):
    name: Literal["metadata","image","video","audio","text","consistency"]
    value: float | None       # 0..100, None unless status=="ok"
    status: Literal["ok","unavailable","not_applicable"]
    findings: list[Finding]
    provider: str | None      # "in_house_pixel_v1", "resemble", ...
    components: dict[str, float] = {}   # e.g. {"ela": 34.2, "jpeg_dq": 82.0, ...}

class ScoreBreakdown(BaseModel):
    claim_id: str; version: int; config_version: str
    subscores: list[SubScore]
    weights_used: dict[str, float]      # post re-normalization
    base_score: float; final_score: float
    escalated: bool; escalation_source: str | None
    routing_band: Literal["AUTO_APPROVE","HUMAN_REVIEW","SIU_INVESTIGATION"]
    forced_review_reason: str | None
    payout_cap: float | None
    created_at: datetime
```

**Tables (SQLAlchemy, append-only):**
- `claim_scores(id PK, claim_id, version, config_version, base_score, final_score, escalated, escalation_source, routing_band, forced_review_reason, payout_cap, breakdown_json, created_at)` — unique (claim_id, version). No UPDATE/DELETE statements anywhere; enforce with a SQLAlchemy event listener that raises on update/delete for these models.
- `score_findings(id PK, claim_score_id FK, rule_id, severity, points, file_id, human_readable, extra_json)`
- `evidence_hashes(id PK, claim_id, file_id, sha256, phash, media_type, created_at)` — written for every image/keyframe at analysis time; consulted by §5.3 step 1.

---

## 8. Configuration (`scoring_config.yaml`)

Ship this exact default file; every number referenced above appears here. Top-level keys: `config_version: "0.1.0-design"`, `fusion:{weights, escalation_threshold: 90, escalation_discount: 5, routing:{auto_approve_below: 15, siu_above: 85}}`, `metadata:{high: 35, medium: 20, low: 8, credits:{c2pa: -25, intact_exif: -8}, gps_radius_km: 25, phash_threshold: 6, modify_gap_hours: 1}`, `image_pixel:{component_weights:{ela: 0.20, jpeg_dq: 0.35, noise: 0.25, freq: 0.20}, ela:{r0: 2.0, r1: 8.0, quality: 92}, dq:{p0: 2.5, p1: 10.0}, noise:{n0: 4.0, n1: 12.0}, freq:{f0: 0.15, f1: 0.45}}`, `video_pixel:{fps_sample: 1, max_frames: 60, min_anomalous_frames: 3}`, `providers:{timeout_s: 30, retries: 2}`, `text:{min_chars: 300, disagreement_gap: 25}`, `consistency:{weather_window_h: 6, temporal_gap_h: 2, external_reverse_search: "suspicious_only"}`, `pricing:{cache_days: 7, labor_buffer: 0.35, min_price_points: 3}`.

Validation at startup: weights sum to 1.0 ± 1e-9; thresholds ordered (0 ≤ auto < siu ≤ 100); all penalties ≥ 0 except credits.

> **IMPORTANT:** These weights, penalties, and thresholds are DESIGN-STAGE values pending calibration on labeled historical claims. Do not hard-code them anywhere outside the config file, and store `config_version` with every score.

---

## 9. Provider Pattern (swappable integrations)

Every external call goes through an ABC selected by env var:
```
AUDIO_DETECTOR_PROVIDER=resemble        # ResembleAudioProvider
TEXT_DETECTOR_PRIMARY=gptzero
TEXT_DETECTOR_SECONDARY=pangram
REVERSE_SEARCH_PROVIDER=serpapi
PART_PRICING_PROVIDER=serpapi
WEATHER_PROVIDER=openweather            # historical endpoint
```
Each provider implements `health()` and its `detect/search/lookup` method; unknown provider name → startup error. Include a `MockProvider` for each ABC (deterministic canned responses) used by tests and demo mode (`SCORING_DEMO_MODE=1`).

---

## 10. Testing Requirements (must all pass)

1. **Determinism:** scoring the same fixture claim 5× yields byte-identical `breakdown_json` (excluding `created_at`).
2. **Worked Example A (clean claim):** fixture sub-scores metadata 6, image 4, video 5, audio 3, text 4, consistency 7 → Base = 4.84 → Final ≈ 5 → `AUTO_APPROVE`, `escalated=False`. (Feed sub-scores via mock analyzers; assert Base to 2 decimals.)
3. **Worked Example B (AI-generated photos):** metadata 85, image 96, video 20, audio 30, text 55, consistency 88 → Base = 61.42 → escalation via image (96 ≥ 90) → Final = 91 → `SIU_INVESTIGATION`, `escalation_source="image"`.
4. **Worked Example C (edited-but-plausible):** metadata 45, image 60, video 15, audio 12, text 20, consistency 25 → Base = 29.76 → Final ≈ 30 → `HUMAN_REVIEW`, no escalation.
5. **Re-normalization:** with video `not_applicable`, weights re-normalize (sum of used weights = 1.0) and example values recompute correctly.
6. **Fail-safe:** Resemble provider raising after retries → `S_audio.status="unavailable"`, pipeline completes, band computed from remaining signals; audio present but image analyzer throws → `forced_review_reason` set and band ≥ `HUMAN_REVIEW`.
7. **Escalation edge:** sub-score exactly 90 escalates; 89.99 does not. Final clamped ≤ 100.
8. **External-match escalation:** a `C-H3` finding with consistency sub-score 60 produces virtual signal 92 → Final = max(Base, 87) and band `SIU_INVESTIGATION`.
9. **Append-only:** attempting to update/delete a `claim_scores` row raises.
10. **No-denial invariant:** grep-level test that the module exposes no "deny/reject" routing value; routing enum has exactly the three bands.
11. **WhatsApp nuance:** image with stripped EXIF and nothing else → S_metadata = 8 (M-L1 only) → alone cannot exceed AUTO_APPROVE threshold (0.10 × 8 = 0.8 base contribution).
12. **Image component gating:** PNG input skips `jpeg_dq` and re-normalizes component weights.

---

## 11. Explicit Non-Goals / Guardrails for the Implementer

- **No LLM anywhere in this module.** Explanation-panel text generation is a separate downstream feature that consumes `ScoreBreakdown`; do not add it here.
- **Do not train or bundle ML deepfake models.** Image/video analysis is classical forensics per §4.1–4.2 only. (A vendor "second-opinion" tier for borderline images may come later behind the provider pattern — do not build it now unless asked.)
- **Do not implement denial, payout, or notification logic.**
- **Do not "tune" the numbers.** If a formula seems to produce odd results on fixtures, the fixtures/tests in §10 are the source of truth; raise the discrepancy instead of changing constants.
- **Privacy:** external reverse search and pricing lookups must never include claimant name, policy number, or claim ID in the query string. Media sent externally is limited to what §5.3 permits.
- Log every provider call (provider, latency, status) but never log media bytes or API keys.
