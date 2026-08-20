"""
Reality Defender deepfake detection provider (video / image / audio / text).
Real API flow (docs.realitydefender.com):
  1. POST /api/files/aws-presigned  -> signedUrl + requestId
  2. PUT  file bytes to signedUrl
  3. GET  /api/media/users/{requestId}  -> poll until analysis completes
Scores are normalized to our 0-100 fraud-confidence scale.
"""
import asyncio

import httpx

from app.config import settings

API_BASE = "https://api.prd.realitydefender.xyz"
POLL_INTERVAL_SECONDS = 3
POLL_MAX_ATTEMPTS = 60  # ~3 minutes


class RealityDefenderError(Exception):
    pass


def _headers() -> dict:
    return {"X-API-KEY": settings.REALITY_DEFENDER_API_KEY}


async def _upload(client: httpx.AsyncClient, filename: str, content: bytes) -> str:
    """Request a presigned URL, upload the file, return the requestId."""
    resp = await client.post(
        f"{API_BASE}/api/files/aws-presigned",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"fileName": filename},
    )
    if resp.status_code != 200:
        raise RealityDefenderError(f"presigned request failed ({resp.status_code}): {resp.text[:200]}")
    body = resp.json()
    payload = body.get("response", body)
    signed_url = payload.get("signedUrl")
    request_id = payload.get("requestId") or body.get("requestId") or payload.get("mediaId")
    if not signed_url or not request_id:
        raise RealityDefenderError(f"unexpected presigned response: {str(body)[:300]}")

    put_resp = await client.put(signed_url, content=content)
    if put_resp.status_code not in (200, 201, 204):
        raise RealityDefenderError(f"file upload failed ({put_resp.status_code})")

    return request_id


async def _poll_result(client: httpx.AsyncClient, request_id: str) -> dict:
    """Poll media detail until analysis finishes; return the raw result payload."""
    pending_statuses = {"ANALYZING", "PROCESSING", "QUEUED", ""}
    for _ in range(POLL_MAX_ATTEMPTS):
        resp = await client.get(f"{API_BASE}/api/media/users/{request_id}", headers=_headers())
        if resp.status_code == 200:
            data = resp.json()
            status = (data.get("overallStatus") or "").upper()
            if status and status not in pending_statuses:
                return data
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise RealityDefenderError(f"analysis timed out for request {request_id}")


def _normalize(data: dict) -> dict:
    """Convert a Reality Defender media-detail payload to our standard result format."""
    status = (data.get("overallStatus") or "").upper()
    summary = data.get("resultsSummary") or {}
    metadata = summary.get("metadata") or {}

    # Prefer ensemble finalScore (0-100); fall back to status-based estimate
    score = metadata.get("finalScore")
    if score is None:
        model_scores = [m.get("finalScore") for m in data.get("models", []) if m.get("finalScore") is not None]
        if model_scores:
            score = max(model_scores)
    if score is None:
        score = {"FAKE": 95.0, "SUSPICIOUS": 60.0, "AUTHENTIC": 5.0}.get(status, 50.0)

    findings = []
    if status == "FAKE":
        findings.append({
            "detail": "Reality Defender ensemble verdict: FAKE — synthetic manipulation detected",
            "timestamp_or_location": None,
        })
    elif status == "SUSPICIOUS":
        findings.append({
            "detail": "Reality Defender ensemble verdict: SUSPICIOUS — possible manipulation, manual review advised",
            "timestamp_or_location": None,
        })

    for model in data.get("models", []):
        m_status = (model.get("status") or "").upper()
        if m_status in ("FAKE", "SUSPICIOUS"):
            m_score = model.get("finalScore")
            findings.append({
                "detail": f"Model {model.get('name', 'unknown')}: {m_status}"
                          + (f" (score {m_score:.0f}%)" if m_score is not None else ""),
                "timestamp_or_location": None,
            })

    for reason in metadata.get("reasons", []):
        findings.append({
            "detail": f"Not applicable: {reason.get('message', reason.get('code', ''))}",
            "timestamp_or_location": None,
        })

    return {
        "raw_score": round(float(score), 1),
        "findings": findings,
        "vendor_status": status,
        "vendor_request_id": data.get("requestId"),
    }


async def _analyze(filename: str, content: bytes) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        request_id = await _upload(client, filename, content)
        data = await _poll_result(client, request_id)
        return _normalize(data)


async def analyze_video(filename: str, content: bytes) -> dict:
    return await _analyze(filename, content)


async def analyze_image(filename: str, content: bytes) -> dict:
    return await _analyze(filename, content)


async def analyze_audio(filename: str, content: bytes) -> dict:
    return await _analyze(filename, content)


async def analyze_text(text: str) -> dict:
    return await _analyze("claim_narrative.txt", text.encode("utf-8"))
