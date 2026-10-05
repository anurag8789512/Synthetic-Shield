"""ImagePixelAnalyzer — in-house pixel-level forensics (spec §4.1). NO vendor API.

Four published classical-forensics checks, each 0-100, combined as a weighted
mean with config component weights. Not-applicable components re-normalize.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np

from app.scoring.config import ScoringConfig
from app.scoring.models import SubScore

EPS = 1e-9


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

    # Component 4 — generative-artifact frequency analysis
    def _freq_artifacts(self, path: Path, is_jpeg: bool, claimed_camera_original: bool) -> float:
        cfg = self.cfg.freq
        gray = _load_gray(path)
        # Hann window kills boundary spectral leakage (axis streaks) before the FFT
        h, w = gray.shape
        window = np.outer(np.hanning(h), np.hanning(w))
        f = np.fft.fftshift(np.fft.fft2((gray - gray.mean()) * window))
        power = np.abs(f) ** 2
        cy, cx = h // 2, w // 2
        yy, xx = np.ogrid[:h, :w]
        # mask the central axes — residual leakage lives there, not in real artifacts
        axis_mask = (np.abs(yy - cy) > 2) & (np.abs(xx - cx) > 2)
        radius = np.hypot(yy - cy, xx - cx).astype(np.int64)
        max_r = min(cy, cx)
        flat_r = radius[axis_mask].ravel()
        flat_p = power[axis_mask].ravel()
        radial = np.bincount(flat_r, weights=flat_p, minlength=max_r)[:max_r]
        counts = np.bincount(flat_r, minlength=max_r)[:max_r]
        profile = radial / np.maximum(counts, 1)
        if profile.size < 16:
            return 0.0
        log_prof = np.log10(profile + EPS)

        # (a) high-frequency roll-off flatness (top third of radii).
        # Log-log slope is scale-invariant: natural images decay ~1/f^2 (slope <= -2),
        # synthetic/upsampled content flattens toward 0.
        start = 2 * profile.size // 3
        hi = log_prof[start:]
        log_r = np.log10(np.arange(start, profile.size, dtype=np.float64) + 1.0)
        slope = float(np.polyfit(log_r, hi, 1)[0]) if hi.size >= 2 else -2.0
        flatness = float(np.clip(1.0 - abs(slope) / 2.0, 0.0, 1.0))

        # (b) periodic spectral spikes (upsampling artifacts): peak height in decades
        # above the smoothed profile. JPEG 8-px blocking creates benign harmonics at
        # multiples of dim/8 — mask those radii so real photos don't false-positive.
        smooth = np.convolve(log_prof, np.ones(9) / 9.0, mode="same")
        resid = log_prof - smooth
        harmonic_mask = np.zeros(profile.size, dtype=bool)
        for dim in (h, w):
            step = dim / 8.0
            k = 1
            while k * step < profile.size:
                center = int(round(k * step))
                lo_b, hi_b = max(center - 4, 0), min(center + 5, profile.size)
                harmonic_mask[lo_b:hi_b] = True
                k += 1
        resid[harmonic_mask] = 0.0
        hi_resid = resid[profile.size // 3:]
        peak_decades = float(hi_resid.max()) if hi_resid.size else 0.0
        spike_energy = float(np.clip((peak_decades - 0.8) / 1.2, 0.0, 1.0))

        metric = max(flatness, spike_energy)
        score = _ramp(metric, cfg.f0 or 0.15, cfg.f1 or 0.45)

        # camera-original .jpg with NO JPEG blocking at all → floor at 60
        if is_jpeg and claimed_camera_original and self._blocking_absent(gray):
            score = max(score, 60.0)
        return score

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
        weights = dict(self.cfg.component_weights)
        components: dict[str, float | None] = {
            "ela": self._ela(path),
            "jpeg_dq": self._jpeg_dq(path, is_jpeg),
            "noise": self._noise_consistency(path),
            "freq": self._freq_artifacts(path, is_jpeg, claimed_camera_original),
        }
        applicable = {k: v for k, v in components.items() if v is not None}
        if not applicable:
            return SubScore(name="image", status="unavailable", provider="in_house_pixel_v1")
        total_w = sum(weights[k] for k in applicable)
        value = sum(weights[k] / total_w * v for k, v in applicable.items())

        fired = [f"{k.replace('jpeg_dq', 'double-quantization periodicity').replace('ela', 'error-level analysis').replace('noise', 'noise inconsistency').replace('freq', 'generative frequency artifacts')} ({v:.0f}/100)"
                 for k, v in applicable.items() if v >= 50]
        desc = (f"Photo {path.name}: " + (" and ".join(fired) + " indicate localized editing or synthesis."
                if fired else "no significant pixel-level manipulation indicators."))
        sub = SubScore(name="image", value=float(np.clip(value, 0, 100)), status="ok",
                       provider="in_house_pixel_v1",
                       components={k: round(v, 1) for k, v in applicable.items()})
        sub.findings = []
        from app.scoring.models import Finding
        sub.findings.append(Finding(
            rule_id="I-PIXEL", severity="info", points=0.0, file_id=path.name,
            human_readable=desc, extra={"components": sub.components,
                                        "not_applicable": [k for k, v in components.items() if v is None]},
        ))
        return sub
