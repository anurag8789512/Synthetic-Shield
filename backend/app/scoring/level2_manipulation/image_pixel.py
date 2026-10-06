"""ImagePixelAnalyzer — in-house pixel-level forensics (spec §4.1). NO vendor API.

Two groups, each 0-100; S_image = max(editing, synthesis):
- editing: ELA, JPEG double-quantization, noise consistency — localized
  manipulation of a real photo (not-applicable components re-normalize);
- synthesis: flat-region micro-texture, tonal clipping, saturation — fully
  AI-generated / AI-upscaled imagery. A C2PA manifest declaring AI generation
  forces synthesis to 100.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np

from app.scoring.config import ScoringConfig
from app.scoring.models import Finding, SubScore
from app.scoring.provenance import read_c2pa

EPS = 1e-9
SYNTH_LONG_SIDE = 1280
IMMERKAER_KERNEL = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
LABELS = {
    "ela": "error-level analysis", "jpeg_dq": "double-quantization periodicity",
    "noise": "noise inconsistency", "texture": "synthetic micro-texture in flat regions",
    "clipping": "generative tonal clipping", "saturation": "boosted saturation",
}


def _ramp(x: float, lo: float, hi: float) -> float:
    """Linear ramp: 0 at lo, 100 at hi, clamped."""
    if hi <= lo:
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0)) * 100.0


def _load_gray(path: Path) -> np.ndarray:
    import cv2
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"cannot decode image: {path.name}")
    return img.astype(np.float64)


def _block_means(arr: np.ndarray, block: int = 8) -> np.ndarray:
    h, w = arr.shape[:2]
    h8, w8 = h - h % block, w - w % block
    if h8 == 0 or w8 == 0:
        return arr.reshape(1, -1).mean(axis=1)
    trimmed = arr[:h8, :w8]
    blocks = trimmed.reshape(h8 // block, block, w8 // block, block)
    return blocks.mean(axis=(1, 3)).ravel()


class ImagePixelAnalyzer:
    def __init__(self, config: ScoringConfig):
        self.cfg = config.image_pixel

    # ── Editing group ──────────────────────────────────────────────────────────
    # Component 1 — Error Level Analysis (suggestive only; lowest weight)
    def _ela(self, path: Path) -> float:
        from PIL import Image
        cfg = self.cfg.ela
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            buf = BytesIO()
            rgb.save(buf, format="JPEG", quality=int(cfg.quality or 92))
            buf.seek(0)
            resaved = Image.open(buf).convert("RGB")
            diff = np.abs(np.asarray(rgb, dtype=np.float64) - np.asarray(resaved, dtype=np.float64))
        diff_gray = diff.mean(axis=2)
        maxv = diff_gray.max()
        if maxv > 0:
            diff_gray = diff_gray * (255.0 / maxv)
        means = _block_means(diff_gray)
        p95 = float(np.percentile(means, 95))
        med = float(np.median(means))
        r = p95 / (med + EPS)
        return _ramp(r, cfg.r0 or 2.0, cfg.r1 or 8.0)

    # Component 2 — JPEG double-quantization detection (strongest signal)
    def _jpeg_dq(self, path: Path, is_jpeg: bool) -> float | None:
        if not is_jpeg:
            return None  # not_applicable → weights re-normalize
        cfg = self.cfg.dq
        coeffs = self._dct_histograms(path)
        if coeffs is None:
            return None
        peak_ratios = []
        for hist in coeffs:
            if hist.sum() < 100:
                continue
            spectrum = np.abs(np.fft.rfft(hist.astype(np.float64)))[1:]  # drop DC
            if spectrum.size == 0 or spectrum.mean() < EPS:
                continue
            peak_ratios.append(float(spectrum.max() / (spectrum.mean() + EPS)))
        if not peak_ratios:
            return None
        peak_ratio = float(np.median(peak_ratios))
        return _ramp(peak_ratio, cfg.p0 or 2.5, cfg.p1 or 10.0)

    def _dct_histograms(self, path: Path) -> list[np.ndarray] | None:
        """Luminance DCT-coefficient histograms per low frequency.

        Prefers true quantized coefficients via jpegio; falls back to
        re-computed 8x8 DCT on the Y channel via cv2 (weaker but published).
        """
        try:
            import jpegio  # type: ignore
            jpg = jpegio.read(str(path))
            dct = jpg.coef_arrays[0]
            hists = []
            for (r, c) in [(0, 1), (1, 0), (1, 1), (0, 2), (2, 0)]:
                coefs = dct[r::8, c::8].ravel()
                hist, _ = np.histogram(coefs, bins=np.arange(-64, 65))
                hists.append(hist)
            return hists
        except Exception:
            pass
        try:
            import cv2
            img = cv2.imread(str(path))
            if img is None:
                return None
            y = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float64) - 128.0
            h, w = y.shape
            h8, w8 = h - h % 8, w - w % 8
            if h8 < 8 or w8 < 8:
                return None
            y = y[:h8, :w8]
            blocks = y.reshape(h8 // 8, 8, w8 // 8, 8).transpose(0, 2, 1, 3).reshape(-1, 8, 8)
            if blocks.shape[0] > 4096:  # deterministic stride subsample for speed
                blocks = blocks[:: blocks.shape[0] // 4096 + 1]
            dct_blocks = np.array([cv2.dct(b) for b in blocks])
            hists = []
            for (r, c) in [(0, 1), (1, 0), (1, 1), (0, 2), (2, 0)]:
                coefs = np.round(dct_blocks[:, r, c])
                hist, _ = np.histogram(coefs, bins=np.arange(-64, 65))
                hists.append(hist)
            return hists
        except Exception:
            return None

    # Component 3 — noise-consistency (PRNU-style); intra-image only,
    # never claims device fingerprinting
    def _noise_consistency(self, path: Path) -> float:
        import cv2
        cfg = self.cfg.noise
        gray = _load_gray(path)
        denoised = cv2.bilateralFilter(gray.astype(np.float32), d=5, sigmaColor=50, sigmaSpace=50)
        residual = gray - denoised.astype(np.float64)
        h, w = residual.shape
        cells = []
        for i in range(4):
            for j in range(4):
                cell = residual[i * h // 4:(i + 1) * h // 4, j * w // 4:(j + 1) * w // 4]
                if cell.size:
                    cells.append(float(cell.var()))
        if len(cells) < 4:
            return 0.0
        ratio = max(cells) / (float(np.median(cells)) + EPS)
        return _ramp(ratio, cfg.n0 or 4.0, cfg.n1 or 12.0)

    # ── Synthesis group: fully AI-generated / AI-upscaled imagery ──────────────
    # Generators render "detail" everywhere — flat regions (sky, paint, road) carry
    # micro-texture a phone ISP would have denoised — and tone-map aggressively
    # (crushed blacks/whites, boosted saturation). Measured at a fixed scale so
    # resolution doesn't shift the statistics.
    def _synthesis_features(self, path: Path) -> dict[str, float]:
        import cv2
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"cannot decode image: {path.name}")
        h, w = bgr.shape[:2]
        scale = SYNTH_LONG_SIDE / max(h, w)
        if scale < 1.0:
            bgr = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)

        # flat-region texture: Immerkaer noise estimate over the 20% lowest-gradient pixels
        lap = cv2.filter2D(gray, -1, IMMERKAER_KERNEL)
        grad = np.hypot(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3),
                        cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3))
        flat = grad < np.percentile(grad, 20)
        texture = float(np.sqrt(np.pi / 2) * np.abs(lap[flat]).mean() / 6.0) if flat.any() else 0.0

        clipping = float(100.0 * ((gray <= 2) | (gray >= 253)).mean())
        saturation = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 1].mean())
        return {"texture": texture, "clipping": clipping, "saturation": saturation}

    def _synthesis(self, path: Path) -> tuple[float, dict[str, float]]:
        raw = self._synthesis_features(path)
        scores = {k: _ramp(raw[k], getattr(self.cfg, k).lo, getattr(self.cfg, k).hi) for k in raw}
        total = sum(self.cfg.synthesis_weights[k] * v for k, v in scores.items())
        return total, scores

    @staticmethod
    def _blocking_absent(gray: np.ndarray) -> bool:
        """Cameras always leave 8x8 blocking; measure boundary vs interior gradients."""
        gx = np.abs(np.diff(gray, axis=1))
        if gx.shape[1] < 16:
            return False
        boundary = gx[:, 7::8].mean()
        interior = np.delete(gx, np.s_[7::8], axis=1).mean()
        return bool(boundary <= interior * 1.02)  # no measurable blocking signature

    def analyze(self, path: str | Path, claimed_camera_original: bool = False) -> SubScore:
        path = Path(path)
        is_jpeg = path.suffix.lower() in (".jpg", ".jpeg")
        findings: list[Finding] = []

        # editing group (weights re-normalize over applicable components)
        editing_parts: dict[str, float | None] = {
            "ela": self._ela(path),
            "jpeg_dq": self._jpeg_dq(path, is_jpeg),
            "noise": self._noise_consistency(path),
        }
        applicable = {k: v for k, v in editing_parts.items() if v is not None}
        weights = self.cfg.component_weights
        total_w = sum(weights[k] for k in applicable)
        editing = sum(weights[k] / total_w * v for k, v in applicable.items()) if total_w else 0.0
        # a camera-original JPEG always carries 8x8 blocking; none at all means re-rendered
        if is_jpeg and claimed_camera_original and self._blocking_absent(_load_gray(path)):
            editing = max(editing, 60.0)
            findings.append(Finding(
                rule_id="I-NOBLOCK", severity="medium", points=0.0, file_id=path.name,
                human_readable=(f"Photo {path.name} carries camera EXIF but no JPEG 8x8 blocking "
                                f"signature, inconsistent with an original camera capture."),
            ))

        synthesis, synth_parts = self._synthesis(path)
        c2pa_info = read_c2pa(path)
        if c2pa_info and c2pa_info.ai_generated:
            synthesis = 100.0
            findings.append(Finding(
                rule_id="I-C2PA-AI", severity="high", points=0.0, file_id=path.name,
                human_readable=(f"Photo {path.name} carries C2PA content credentials declaring it "
                                f"AI-generated" + (f" ({c2pa_info.generator})." if c2pa_info.generator else ".")),
                extra={"generator": c2pa_info.generator},
            ))

        value = float(np.clip(max(editing, synthesis), 0.0, 100.0))
        components = {**{k: round(v, 1) for k, v in applicable.items()},
                      **{k: round(v, 1) for k, v in synth_parts.items()},
                      "editing": round(editing, 1), "synthesis": round(synthesis, 1)}

        if synthesis >= 50 and synthesis >= editing:
            fired = ", ".join(LABELS[k] for k, v in synth_parts.items() if v >= 50) or "provenance data"
            desc = (f"Photo {path.name}: synthesis indicators {synthesis:.0f}/100 ({fired}) — "
                    f"consistent with AI-generated or AI-upscaled imagery.")
        elif editing >= 50:
            fired = ", ".join(LABELS[k] for k, v in applicable.items() if v >= 50) or "re-rendering"
            desc = (f"Photo {path.name}: editing indicators {editing:.0f}/100 ({fired}) — "
                    f"consistent with localized manipulation.")
        else:
            desc = (f"Photo {path.name}: no significant pixel-level manipulation or synthesis "
                    f"indicators (editing {editing:.0f}, synthesis {synthesis:.0f}).")
        findings.insert(0, Finding(
            rule_id="I-PIXEL", severity="info", points=0.0, file_id=path.name,
            human_readable=desc, extra={"components": components,
                                        "not_applicable": [k for k, v in editing_parts.items() if v is None]},
        ))
        return SubScore(name="image", value=value, status="ok", provider="in_house_pixel_v2",
                        components=components, findings=findings)
