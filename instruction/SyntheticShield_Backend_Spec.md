# SyntheticShield — Backend Technical Specification

This is the complete backend spec for SyntheticShield: an AI-powered
deepfake detection system for **motor insurance claims** (FNOL). It covers
database schema, authentication, all API endpoints, the AI agent
architecture, detection vendor integrations, and adjudication logic —
everything needed to build or continue the backend independently.

**Scope for this build: Motor insurance only.** No home/property/other
coverage types.

---

## 1. Tech Stack & Environment

- **Framework:** FastAPI (Python)
- **Database:** SQLite via SQLAlchemy, **local only — no Supabase, no
  Firebase.** This was an explicit decision: the demo runs entirely on a
  local DB, not a hosted cloud DB.
- **Secondary store (added later, not at project start):** Chroma
  (vector DB) — for semantic similarity search on claim narratives only.
  Not a replacement for SQLite; SQLite remains the system of record for
  everything relational (claims, policies, votes, etc.). Chroma similarity
  scores get written back into a SQLite column so existing SQL-based
  analytics can use them like any other field.
- **Media storage:** local disk by default (`app/media_store/`), served
  via FastAPI static file mount — swappable to S3/Supabase Storage later
  via a `STORAGE_PROVIDER` env var, but local is fine for the demo.
- **Real-time updates:** WebSockets (native FastAPI/Starlette), no
  external pub-sub needed at this scale.
- **All provider integrations (detection vendors, OTP delivery, storage)
  must be built behind a swappable config pattern** — an env var picks the
  provider (`mock`/`console` for local dev, real vendor name for
  production), so switching vendors never requires touching calling code.
  This pattern should be used consistently for every external integration
  in this spec.

### Environment variables (complete list)

```
# Storage
STORAGE_PROVIDER=local            # local | s3 | supabase
PUBLIC_BASE_URL=http://localhost:8000
AWS_S3_BUCKET=
AWS_REGION=us-east-1

# Detection — one provider per modality (see Section 7)
VIDEO_DETECTION_PROVIDER=mock     # mock | reality_defender | hive | getreal
AUDIO_DETECTION_PROVIDER=mock     # mock | resemble_ai
IMAGE_DETECTION_PROVIDER=mock     # mock | truepic | hive
TEXT_DETECTION_PROVIDER=mock      # mock | gptzero | pangram
REALITY_DEFENDER_API_KEY=
RESEMBLE_AI_API_KEY=
TRUEPIC_API_KEY=
GPTZERO_API_KEY=
PANGRAM_API_KEY=

# Adjudication thresholds
AUTO_APPROVE_BELOW=15             # fraud confidence %, exclusive
SIU_FLAG_ABOVE=85                 # fraud confidence %, exclusive
# 15-85 inclusive = Moderator Review

# OTP / Auth (local, not Supabase)
OTP_PROVIDER=console              # console | twilio | email
OTP_LENGTH=6
OTP_EXPIRY_MINUTES=5
OTP_MAX_ATTEMPTS=5
SESSION_EXPIRY_HOURS=12
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
EMAIL_PROVIDER_API_KEY=
EMAIL_FROM_ADDRESS=no-reply@syntheticshield.demo

# Misc
DETECTION_SIMULATED_DELAY_SECONDS=4   # only relevant to the mock provider
DATABASE_URL=sqlite:///./claims.db
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
MOCK_PAYOUT_AMOUNT_CENTS=125000
```

---

## 2. Database Schema (SQLite via SQLAlchemy)

```
users
  id                    INTEGER PK
  full_name             STRING NOT NULL
  dob                   STRING              -- ISO date string, e.g. "1990-04-12"
  email                 STRING UNIQUE INDEX
  phone                 STRING UNIQUE INDEX
  created_at            DATETIME DEFAULT now

policies
  id                    INTEGER PK
  user_id               INTEGER FK -> users.id, INDEX
  policy_number         STRING UNIQUE INDEX NOT NULL
  status                STRING NOT NULL DEFAULT "active"   -- active | lapsed | cancelled
  issued_date           STRING
  renewal_date          STRING

coverages
  id                    INTEGER PK
  policy_id             INTEGER FK -> policies.id, INDEX
  coverage_type         STRING NOT NULL   -- own_damage | third_party_liability | comprehensive | add_on
  coverage_label        STRING NOT NULL   -- human-readable, shown in the dropdown
  coverage_limit_cents  INTEGER
  status                STRING NOT NULL DEFAULT "active"

otp_codes
  id                    INTEGER PK
  identifier            STRING INDEX NOT NULL   -- phone or email, as entered
  code                  STRING NOT NULL
  expires_at            DATETIME NOT NULL
  verified              BOOLEAN NOT NULL DEFAULT false
  attempts              INTEGER NOT NULL DEFAULT 0   -- brute-force guard, max = OTP_MAX_ATTEMPTS
  created_at            DATETIME DEFAULT now

sessions
  id                    INTEGER PK
  token                 STRING UNIQUE INDEX NOT NULL   -- bearer token, secrets.token_urlsafe(32)
  user_id               INTEGER FK -> users.id, INDEX
  expires_at            DATETIME NOT NULL
  created_at            DATETIME DEFAULT now

claims
  id                        INTEGER PK
  claim_number               STRING UNIQUE INDEX   -- e.g. "CLM-2026-00042"
  user_id                    INTEGER FK -> users.id
  policy_id                  INTEGER FK -> policies.id
  coverage_id                INTEGER FK -> coverages.id
  accident_location           STRING
  accident_description         TEXT
  video_url                    STRING
  audio_url                     STRING
  transcript_text                TEXT           -- from audio, feeds Consistency Agent
  status                          STRING NOT NULL DEFAULT "processing"
    -- processing | auto_approved | moderator_review | rejected |
    -- siu_investigation | siu_confirmed_fraud | siu_cleared
  fraud_confidence_score           FLOAT        -- aggregated 0-100
  consistency_score                 FLOAT       -- narrative consistency signal, 0-100
  narrative_similarity_score         FLOAT      -- from Chroma, added later
  artifact_report                     TEXT      -- JSON string: AI-generated explanation (see Section 8)
  payout_transaction_id                STRING
  payout_amount_cents                   INTEGER
  created_at                             DATETIME DEFAULT now
  updated_at                              DATETIME DEFAULT now, ON UPDATE now

claim_documents
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id
  file_url              STRING NOT NULL
  file_type             STRING NOT NULL DEFAULT "pdf"   -- PDF only, enforced at upload
  uploaded_at            DATETIME DEFAULT now

claim_media_analysis          -- granular per-modality raw detector output
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id, INDEX
  modality              STRING NOT NULL   -- video | audio | image | document
  provider               STRING NOT NULL  -- e.g. "reality_defender", "resemble_ai"
  raw_score               FLOAT
  findings_json             TEXT          -- structured findings from the vendor, pre-LLM-synthesis
  created_at                 DATETIME DEFAULT now

claims_officers
  id                    INTEGER PK
  name                  STRING NOT NULL
  email                 STRING UNIQUE
  role                  STRING NOT NULL   -- moderator | siu_officer | senior
  department            STRING

moderator_actions
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id
  officer_id             INTEGER FK -> claims_officers.id
  decision                STRING NOT NULL   -- approved | rejected
  rejection_reason         TEXT
  decided_at                DATETIME DEFAULT now

siu_reviews
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id, UNIQUE
  required_votes         INTEGER NOT NULL DEFAULT 4
  status                   STRING NOT NULL DEFAULT "pending"   -- pending | confirmed_fraud | cleared

siu_officer_votes
  id                    INTEGER PK
  siu_review_id          INTEGER FK -> siu_reviews.id
  officer_id              INTEGER FK -> claims_officers.id
  vote                     STRING NOT NULL   -- confirm_fraud | clear
  notes                     TEXT
  voted_at                   DATETIME DEFAULT now
  UNIQUE(siu_review_id, officer_id)          -- one vote per officer, enforced at DB level

payouts
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id
  amount_cents           INTEGER NOT NULL
  status                   STRING NOT NULL
  transaction_id             STRING
  initiated_at                DATETIME DEFAULT now

notifications_log
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id
  channel               STRING NOT NULL   -- email | sms
  recipient               STRING NOT NULL
  template_type             STRING NOT NULL   -- see Section 9 for exact template names
  status                      STRING NOT NULL   -- sent | failed
  provider_message_id           STRING
  sent_at                         DATETIME DEFAULT now

audit_trail
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id, INDEX
  actor_type             STRING NOT NULL   -- system | agent | officer
  actor_id                 STRING
  action                     STRING NOT NULL
  details_json                 TEXT
  created_at                     DATETIME DEFAULT now

copilot_messages          -- officer <-> AI chat, scoped per claim
  id                    INTEGER PK
  claim_id              INTEGER FK -> claims.id, INDEX
  officer_id             INTEGER FK -> claims_officers.id
  role                     STRING NOT NULL   -- officer | assistant
  content                     TEXT NOT NULL
  created_at                     DATETIME DEFAULT now
```

**Design rule carried through the whole schema:** every table that
represents a decision or action (`moderator_actions`, `siu_officer_votes`,
`payouts`, `notifications_log`, `audit_trail`) is append-only / immutable
history — never update these rows in place, always insert a new one. This
matters for insurance compliance: you need a defensible trail of exactly
what happened and when, not just current state.

### SIU quorum rule
Default: **unanimous 4/4 required to confirm fraud.** If any one of the
four officers votes "clear," the case does not auto-finalize as fraud — it
escalates to a senior SIU lead for a tie-break decision. This is a business
rule that can be changed to majority (3/4), but unanimous is the default
assumption baked into `siu_reviews.required_votes`.

### Chroma collection (added later, not at project start)
```
Collection: claim_narratives
  - embedding of claim.accident_description
  - metadata: { claim_id, outcome: "fraud" | "legitimate" }
```
On each new claim: embed its narrative, query nearest neighbors, write the
similarity result into `claims.narrative_similarity_score`. Seed data
(synthetic fraud/legitimate narratives) is explicitly deferred — build the
integration now, populate it later.

---

## 3. Authentication Flow (Local OTP — NOT Supabase/Firebase)

Original plan referenced Supabase Auth; this was superseded — build local
OTP verification against the `users`/`otp_codes`/`sessions` tables instead.

**POST `/auth/request-otp`**
- Request: `{ "identifier": string }` (phone or email, as typed)
- Look up `users` by `email == identifier OR phone == identifier`
- If no match: `404` — deliberately vague error, don't reveal whether the
  identifier exists (`"No policyholder found with these details."`)
- If match: generate a code (`OTP_LENGTH` digits), insert into `otp_codes`
  with `expires_at = now + OTP_EXPIRY_MINUTES`, dispatch via the
  `OTP_PROVIDER` abstraction
- Response: `{ "message": string, "debug_otp": string | null }` —
  `debug_otp` is ONLY populated when `OTP_PROVIDER=console` (local demo
  mode); a real provider never echoes the code back in the API response

**POST `/auth/verify-otp`**
- Request: `{ "identifier": string, "code": string }`
- Look up the latest unverified `otp_codes` row for that identifier
- Validate in order: exists → not expired → `attempts < OTP_MAX_ATTEMPTS`
  → code matches
- On mismatch: increment `attempts`, return `400` with remaining-attempts
  count
- On success: mark `verified = true`, look up the `users` row, issue a new
  `sessions` row (`token = secrets.token_urlsafe(32)`,
  `expires_at = now + SESSION_EXPIRY_HOURS`)
- Response: `{ "session_token": string, "user_id": int, "full_name": string }`

**Session dependency (used on every authenticated endpoint):**
- Expects header `Authorization: Bearer <token>`
- Looks up `sessions` by token, checks `expires_at > now`
- 401 on missing header, invalid token, or expired session
- Returns the associated `User` row for use in the endpoint

**OTP delivery abstraction (`OTP_PROVIDER`):**
- `console` — logs the code server-side and echoes it in the API response;
  demo-only, explicitly insecure, never use beyond local prototyping
- `twilio` — real SMS via Twilio (stub to fill in with real credentials)
- `email` — real email via a provider like Resend/SendGrid (stub to fill in)

---

## 4. API Endpoints (complete list)

```
Auth
  POST   /auth/request-otp
  POST   /auth/verify-otp

Policies
  GET    /policies/me                      -- requires auth; current user's policy + coverages
  GET    /policies/{policy_id}/coverages    -- requires auth; must own the policy

Claims (customer-facing)
  POST   /claims                            -- multipart: coverage_id, accident_location,
                                                accident_description, video (required),
                                                audio (required), document (optional, PDF only)
  GET    /claims/{claim_id}                 -- single claim detail
  GET    /claims                            -- list/queue, filterable by status, user_id

Moderator actions
  POST   /claims/{claim_id}/moderator-approve
  POST   /claims/{claim_id}/moderator-reject     -- body: { reason: string }

SIU
  POST   /claims/{claim_id}/siu-vote             -- body: { officer_id, vote, notes }
  GET    /claims/{claim_id}/siu-status           -- current tally, required votes, status

Copilot (new — officer <-> AI chat on a flagged claim)
  POST   /claims/{claim_id}/copilot-chat         -- body: { officer_id, message }
                                                     returns AI response, grounded ONLY in
                                                     that claim's claim_media_analysis +
                                                     artifact_report (see Section 8)
  GET    /claims/{claim_id}/copilot-history       -- prior messages for this claim

Real-time
  WS     /ws/claims/{claim_id}                    -- customer-side: live status for one claim
  WS     /ws/officer-feed                          -- dashboard-wide: broadcasts on every new
                                                       claim submission, drives the notification bell

Internal (called by agents, not directly by frontend)
  -- notification sending, audit logging: no public HTTP surface needed,
     these are agent-to-agent/service calls
```

---

## 5. Claim Submission Rules

- `coverage_id` must belong to the authenticated user's policy — validate,
  don't trust the client
- `video` (or photo) — **mandatory**, reject the request if missing
- `audio` — **mandatory**, reject the request if missing
- `document` — **optional**, but if present must be `application/pdf`;
  reject with a clear error otherwise
- On successful create: generate `claim_number` (e.g.
  `CLM-{year}-{zero-padded sequential or random id}`), set
  `status = "processing"`, kick off the Detection + Consistency agents as a
  background task, return immediately with the claim number and a
  WebSocket URL for live status
- **Known async-task pitfall to avoid:** if using `asyncio.create_task()`
  for background processing, you must keep a strong reference to the task
  (e.g. a module-level `set()` with a `add_done_callback` to discard it
  when done). Without this, Python's asyncio only holds a weak reference
  and the task can be silently garbage-collected mid-run, leaving the claim
  stuck on "processing" forever with no error logged anywhere. This is a
  real bug that was hit and fixed during prototyping — don't reintroduce it.
- Similarly, if running the dev server with hot-reload enabled, exclude the
  database file and media storage directory from the file-watcher, or
  writes to those files will trigger a server restart mid-request and kill
  any in-flight background task the same way.

---

## 6. AI Agent Architecture

**Design principle:** the approve/moderate/investigate **routing decision
stays deterministic** — a plain threshold check on a numeric score, not an
LLM judgment call. This matters for auditability: an insurer needs to be
able to say "this claim was routed to SIU because the score was 91%, full
stop," not "the AI felt like it was fraud." Everything **downstream** of
that number — explaining why, answering follow-up questions, drafting
notifications — is where LLM agents genuinely add value.

| Agent | Trigger | Tools it calls | LLM? |
|---|---|---|---|
| Auth Agent | Login attempt | `verify_otp()`, `lookup_policy()` | Optional (anomaly check) |
| Detection Agent | Claim submitted | per-modality vendor calls, `aggregate_score()` | Yes — synthesizes raw scores into `artifact_report` |
| Consistency Agent | After media upload | `transcribe_audio()`, `read_pdf()`, `compare_narrative()` | Yes |
| Adjudication Orchestrator | Both scores in | `route_claim()` | No — deterministic router |
| Claim Approver Agent | Score < 15% | `initiate_payout()`, `send_email()`, `send_sms()`, `update_status()` | Optional (copy drafting) |
| Claim Moderator Agent | 15% ≤ score ≤ 85% | `notify_officer()`, `send_email()`, `send_sms()`, `update_status()` | Optional |
| Claim Rejector Agent | Moderator rejects | `send_email()`, `send_sms()`, `update_status()` | Optional |
| SIU Agent | Score > 85% | `send_email()`, `send_sms()`, `flag_red()`, `open_quorum_review()`, `tally_votes()` | Yes — investigation summary |
| Notification Agent | Called by others | `send_email()`, `send_sms()`, `log_notification()` | No — template-driven |
| **Copilot Agent** | Officer asks a question | reads `claim_media_analysis` + `artifact_report` for one claim | Yes — strictly grounded |
| **Similarity Agent** | Claim submitted | Chroma query | No LLM, vector query only |

**Implementation pattern for every LLM-backed agent:**
- A single Claude API call with a narrow system prompt defining exactly one
  job
- A fixed tool schema — the agent can only call the specific Python
  functions it's given, nothing else
- No agent changes claim status directly except through its designated
  tool — this keeps every state change traceable to a specific tool call,
  logged in `audit_trail`

---

## 7. Detection Vendor Integration (per modality)

Each modality gets its **own** provider config — don't assume one vendor
covers all four well; evaluation found meaningful accuracy gaps between
vendors on individual modalities.

| Modality | Primary vendor | Why |
|---|---|---|
| Audio | **Resemble AI (Detect)** | Top independently-benchmarked voice-clone/synthetic-audio detector; GDPR + HIPAA compliant, ISO 27001 in progress |
| Video | **Reality Defender** (bake-off against Hive / GetReal Security before finalizing) | Gartner-recognized "Market Shaper"; no single vendor has a verified #1 spot on video specifically — test on real sample footage before committing |
| Image | **Truepic** | Purpose-built for insurance/lending media authenticity; Microsoft (M12), Adobe, Sony-backed |
| Text (claim narrative) | **GPTZero** (primary), **Pangram** (secondary cross-check) | Both independently benchmarked at ~99%+ accuracy; running both and requiring agreement reduces either one's individual blind spot |

**Each vendor integration must return a common shape** regardless of
provider, so `claim_media_analysis.findings_json` is consistent:
```json
{
  "raw_score": 0-100,
  "findings": [ { "detail": string, "timestamp_or_location": string | null } ]
}
```

**Mock/local provider (`mock`)** — for demo/dev without API keys: returns a
deterministic-but-varied score seeded from the input, with demo trigger
words in filenames (`fraud`, `clean`) to force specific outcomes for
predictable testing.

---

## 8. Explainability Feature (AI-generated evidence descriptions)

**Requirement:** alongside the numeric fraud score, the system must
generate a human-readable explanation of *why* each piece of evidence
(video/audio/image/document) was judged fake or authentic — not just a
score.

**How it works:** the Detection Agent's LLM call takes the **raw structured
detector output** (`claim_media_analysis.findings_json` — per-frame
anomaly scores, spectral flags, EXIF gaps, perplexity scores) as input, and
produces `claims.artifact_report`, a JSON string shaped like:
```json
{
  "fraud_confidence_score": 91.4,
  "detected_artifacts": [
    "Inconsistent audio frequencies detected between 0:02 and 0:05",
    "Frame-level artifact signature detected around 0:11-0:14"
  ],
  "recommendation": "Route to SIU investigator for manual review."
}
```

**Critical grounding rule:** the LLM must only narrate/synthesize the real
detector output it's given — it must never independently speculate beyond
those findings. This report can end up supporting a real fraud
determination or claim denial, so ungrounded "explanations" that sound
plausible but aren't backed by actual model output are a real liability
risk, not just a quality issue. Prompt design must explicitly restrict the
agent to the data it's handed.

---

## 9. Copilot Chat Feature (officer ↔ AI on a flagged claim)

**Requirement:** once a claim is flagged, the reviewing officer can chat
with an AI about the evidence for more detail — e.g. "why do you think the
audio was cloned?" — scoped to that specific claim.

- Every message (both officer and assistant) is stored in
  `copilot_messages`, tied to `claim_id`
- The Copilot Agent's context is built from: the claim record, all
  `claim_media_analysis` rows for that claim, and the `artifact_report` —
  nothing else
- **Same grounding rule as Section 8, applied more strictly** — open-ended
  conversation has a higher risk of drifting into unsupported speculation
  than a fixed report. If asked something outside what was actually
  analyzed, the agent should say it doesn't have that information rather
  than guess.
- **Hard data isolation requirement:** the agent must never surface data
  from any claim other than the one currently open — this needs to be
  enforced at the query level (only ever fetch rows where
  `claim_id = <current claim>`), not just prompted around
- Logging every Q&A exchange to `copilot_messages` (and mirroring key
  actions to `audit_trail`) is a compliance plus — it documents the
  officer's due diligence in case a decision is challenged later

---

## 10. Adjudication Logic — Exact Thresholds & Notification Content

```
score < 15%   → Auto-Approved
15% ≤ score ≤ 85% → Moderator Review
score > 85%   → SIU Investigation
```

| Scenario | Trigger | Channel | Exact content |
|---|---|---|---|
| Auto-approved | Score < 15% | Email + SMS | Claim number, Status: Approved, Amount released |
| Moderator review (initial) | 15% ≤ score ≤ 85% | Email + SMS | Claim number, Status: Moderator Review, Amount released: Pending |
| Moderator approves | Officer clicks Approve | Email + SMS | Same as auto-approved template |
| Moderator rejects | Officer clicks Reject + enters reason | Email + SMS | Claim number, Status: Moderator Review, Amount released: N/A, Reason |
| SIU flagged (initial) | Score > 85% | Email + SMS | Claim number, SIU Investigation notice |
| SIU quorum reached | 4th officer vote cast | Email + SMS | Final outcome (confirmed fraud / cleared) |

Every notification send — success or failure — gets a row in
`notifications_log`. On failure, the claim's processing must not silently
stall; log the failure and allow retry, but don't block the claim's actual
status progression on notification delivery succeeding.

---

## 11. Recommended Project Structure

```
app/
  main.py                      -- FastAPI app instance, CORS, static mount, startup
  config.py                    -- all env vars (Section 1), swappable-provider settings
  database.py                  -- SQLAlchemy engine/session/Base
  models.py                    -- all tables from Section 2
  schemas.py                   -- Pydantic request/response models

  routers/
    auth.py
    policies.py
    claims.py
    moderator.py
    siu.py
    copilot.py
    ws.py

  agents/
    orchestrator.py             -- deterministic router
    detection_agent.py           -- per-modality calls + score aggregation + artifact_report
    consistency_agent.py
    approver_agent.py
    moderator_agent.py
    rejector_agent.py
    siu_agent.py
    copilot_agent.py
    similarity_agent.py          -- Chroma wrapper, added later
    notification_agent.py

  providers/
    detection/
      video_providers.py         -- mock, reality_defender, hive, getreal
      audio_providers.py         -- mock, resemble_ai
      image_providers.py         -- mock, truepic, hive
      text_providers.py          -- mock, gptzero, pangram
    otp_provider.py               -- console, twilio, email
    storage.py                     -- local, s3, supabase

  ws_manager.py                    -- WebSocket connection registry

seed_data.py                        -- creates test users/policies/coverages (motor only)
```

---

## 12. Explicitly Deferred / Out of Scope For Now

- Chroma seed data (synthetic fraud/legitimate narrative examples) — build
  the integration, populate later
- Real payment/payout processing — payouts are simulated
- Production deployment / cloud hosting — local dev only for now
- Supabase or any hosted DB — staying local-only until further notice
- Real SMS/email provider credentials — `console`/mock mode is fine until
  those are actually needed for a live test
- Home, property, or any non-motor coverage type

---

## 13. Build Order (once frontend is ready)

1. Auth (local OTP) + Policy endpoints
2. Claim submission with motor coverage validation, mandatory video/audio,
   optional PDF
3. Detection + Consistency agents, real vendor integration per modality
4. Adjudication agents + real notification delivery
5. Moderator + SIU quorum endpoints, officer-feed WebSocket
6. Explainability (`artifact_report`) wired to real detector output
7. Copilot chat
8. Audit trail hardening, retry logic on notification failures
9. Chroma integration + seed data
