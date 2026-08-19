import os
import shutil
from pathlib import Path

from app.config import settings

MEDIA_ROOT = Path("app/media_store")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


def save_file(claim_number: str, filename: str, content: bytes) -> str:
    """Save a file to local storage and return its public URL."""
    claim_dir = MEDIA_ROOT / claim_number
    claim_dir.mkdir(parents=True, exist_ok=True)

    file_path = claim_dir / filename
    file_path.write_bytes(content)

    return f"{settings.PUBLIC_BASE_URL}/media/{claim_number}/{filename}"
