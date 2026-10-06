import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings

MEDIA_ROOT = Path("app/media_store")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

_BROWSER_CODECS = {"h264", "vp8", "vp9", "av1"}


def save_file(claim_number: str, filename: str, content: bytes) -> str:
    """Save a file to local storage and return its public URL."""
    claim_dir = MEDIA_ROOT / claim_number
    claim_dir.mkdir(parents=True, exist_ok=True)

    file_path = claim_dir / filename
    file_path.write_bytes(content)

    return f"{settings.PUBLIC_BASE_URL}/media/{claim_number}/{filename}"


def ensure_browser_playable_video(claim_number: str, filename: str) -> None:
    """Re-encode an uploaded video to H.264 in place when the browser can't
    play its codec (e.g. MPEG-4 Part 2). Keeps the same filename/URL. No-op
    when ffmpeg is unavailable or the codec is already playable."""
    path = MEDIA_ROOT / claim_number / filename
    if not path.exists():
        return
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        codec = probe.stdout.strip().splitlines()[0] if probe.stdout.strip() else ""
        if codec in _BROWSER_CODECS:
            return
        tmp = path.with_name(path.stem + ".transcoding.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-c:v", "libx264", "-preset", "fast",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(tmp)],
            capture_output=True, timeout=600, check=True,
        )
        tmp.replace(path)
        print(f"[MEDIA] {claim_number}/{filename}: transcoded {codec or 'unknown'} -> h264 for browser playback")
    except Exception as e:
        print(f"[MEDIA] transcode skipped for {claim_number}/{filename}: {type(e).__name__}: {e}")
