"""
Reality Defender video/image deepfake detection provider.
API docs: https://docs.realitydefender.com
"""
import httpx
from app.config import settings

API_BASE = "https://api.realitydefender.com/v2"


async def analyze_video(filename: str, content: bytes) -> dict:
    """Submit video to Reality Defender for deepfake analysis."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {"Authorization": f"Bearer {settings.REALITY_DEFENDER_API_KEY}"}

        # Upload media for analysis
        files = {"file": (filename, content, "video/mp4")}
        resp = await client.post(
            f"{API_BASE}/detect/video",
            headers=headers,
            files=files,
        )
        resp.raise_for_status()
        data = resp.json()

        # Normalize to our standard format
        score = data.get("score", data.get("fake_probability", 0)) * 100
        findings = []
        for detail in data.get("detections", data.get("findings", [])):
            if isinstance(detail, dict):
                findings.append({
                    "detail": detail.get("description", detail.get("message", str(detail))),
                    "timestamp_or_location": detail.get("timestamp", detail.get("location", None)),
                })
            elif isinstance(detail, str):
                findings.append({"detail": detail, "timestamp_or_location": None})

        return {"raw_score": round(score, 1), "findings": findings}


async def analyze_image(filename: str, content: bytes) -> dict:
    """Submit image to Reality Defender for deepfake analysis."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {settings.REALITY_DEFENDER_API_KEY}"}

        content_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
        files = {"file": (filename, content, content_type)}
        resp = await client.post(
            f"{API_BASE}/detect/image",
            headers=headers,
            files=files,
        )
        resp.raise_for_status()
        data = resp.json()

        score = data.get("score", data.get("fake_probability", 0)) * 100
        findings = []
        for detail in data.get("detections", data.get("findings", [])):
            if isinstance(detail, dict):
                findings.append({
                    "detail": detail.get("description", detail.get("message", str(detail))),
                    "timestamp_or_location": detail.get("region", None),
                })
            elif isinstance(detail, str):
                findings.append({"detail": detail, "timestamp_or_location": None})

        return {"raw_score": round(score, 1), "findings": findings}
