"""VideoPixelAnalyzer — in-house frame-level forensics (spec §4.2). NO vendor API.

Samples frames, runs the §4.1 image battery per frame, plus temporal checks
(noise-profile discontinuity, optical-flow discontinuity).
S_video = 0.7 * p95(per-frame scores) + 0.3 * temporal_component.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from app.scoring.config import ScoringConfig
from app.scoring.models import Finding, SubScore
from app.scoring.level2_manipulation.image_pixel import ImagePixelAnalyzer, _ramp

EPS = 1e-9


def probe_is_video(path: Path) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True, timeout=30,
        )
        data = json.loads(out.stdout or b"{}")
        return any(s.get("codec_type") == "video" for s in data.get("streams", []))
    except Exception:
        return False


class VideoPixelAnalyzer:
    def __init__(self, config: ScoringConfig):
        self.config = config
        self.cfg = config.video_pixel
        self.image_analyzer = ImagePixelAnalyzer(config)

    def _sample_frames(self, path: Path) -> list[np.ndarray]:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"cannot open video: {path.name}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(int(round(fps / self.cfg.fps_sample)), 1)
        frames: list[np.ndarray] = []
        idx = 0
        while len(frames) < self.cfg.max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                frames.append(frame)
            idx += 1
        cap.release()
        return frames

    def _frame_score(self, frame: np.ndarray) -> float:
        """Run the image component battery on one frame (via a temp PNG)."""
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            cv2.imwrite(str(tmp_path), frame)
            sub = self.image_analyzer.analyze(tmp_path)
            return sub.value if sub.value is not None else 0.0
        finally:
            tmp_path.unlink(missing_ok=True)

    def _residual_variance(self, frame: np.ndarray) -> float:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        denoised = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
        return float((gray - denoised).var())

    def _temporal_component(self, frames: list[np.ndarray]) -> tuple[float, dict]:
        import cv2
        details: dict = {}
        if len(frames) < 3:
            return 0.0, details

        # Noise-profile discontinuity: z-score spikes in residual-variance sequence
        variances = np.array([self._residual_variance(f) for f in frames])
        mu, sigma = float(variances.mean()), float(variances.std())
        anomalous = int(np.sum(np.abs(variances - mu) > 3 * sigma)) if sigma > EPS else 0
        min_frames = self.cfg.min_anomalous_frames
        noise_score = _ramp(float(anomalous), float(min_frames), 10.0) if anomalous >= min_frames else 0.0
        details["anomalous_noise_frames"] = anomalous

        # Optical-flow discontinuity: implausible global-flow reversals/jumps
        flows = []
        prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        for f in frames[1:]:
            gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None,
                                                0.5, 3, 15, 3, 5, 1.2, 0)
            flows.append((float(flow[..., 0].mean()), float(flow[..., 1].mean())))
            prev_gray = gray
        jumps = 0
        for (x1, y1), (x2, y2) in zip(flows, flows[1:]):
            m1, m2 = np.hypot(x1, y1), np.hypot(x2, y2)
            dot = x1 * x2 + y1 * y2
            reversal = m1 > 0.5 and m2 > 0.5 and dot < -0.5 * m1 * m2
            jump = m2 > 5.0 * max(m1, 0.5)
            if reversal or jump:
                jumps += 1
        flow_score = _ramp(float(jumps), 1.0, 6.0) if jumps >= 1 else 0.0
        details["flow_discontinuities"] = jumps

        return max(noise_score, flow_score), details

    def analyze(self, path: str | Path) -> SubScore:
        path = Path(path)
        if not probe_is_video(path):
            # non-video container is a metadata-style finding, not a crash
            return SubScore(
                name="video", status="unavailable", provider="in_house_pixel_v1",
                findings=[Finding(rule_id="V-CONTAINER", severity="info", points=0.0,
                                  file_id=path.name,
                                  human_readable=f"Uploaded file {path.name} is not a decodable video container.")],
            )
        frames = self._sample_frames(path)
        if not frames:
            return SubScore(name="video", status="unavailable", provider="in_house_pixel_v1")

        per_frame = np.array([self._frame_score(f) for f in frames])
        p95 = float(np.percentile(per_frame, 95))
        temporal, details = self._temporal_component(frames)
        value = float(np.clip(0.7 * p95 + 0.3 * temporal, 0.0, 100.0))

        desc = (f"Video {path.name}: {len(frames)} sampled frames, 95th-percentile frame score "
                f"{p95:.0f}/100, temporal component {temporal:.0f}/100"
                + (f" ({details.get('anomalous_noise_frames', 0)} noise-discontinuity frames, "
                   f"{details.get('flow_discontinuities', 0)} optical-flow discontinuities)." if details else "."))
        return SubScore(
            name="video", value=value, status="ok", provider="in_house_pixel_v1",
            components={"frame_p95": round(p95, 1), "temporal": round(temporal, 1)},
            findings=[Finding(rule_id="V-PIXEL", severity="info", points=0.0,
                              file_id=path.name, human_readable=desc, extra=details)],
        )
