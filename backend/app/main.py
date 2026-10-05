from pathlib import Path

import truststore

truststore.inject_into_ssl()  # use OS cert store so vendor API TLS verification works

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, Base, run_migrations
import app.models  # noqa: F401 — register core tables on Base
import app.scoring.persistence  # noqa: F401 — register append-only scoring tables
from app.scoring.config import get_config
from app.routers import auth, policies, claims, moderator, siu, ws, efficiency, downloads, copilot, similarity

# Validate scoring config at startup (raises on bad weights/thresholds)
get_config()

# Create all tables on startup
Base.metadata.create_all(bind=engine)
run_migrations()

# Ensure media directory exists
Path("app/media_store").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SyntheticShield API", version="0.1.0")

# CORS — allow configured local dev origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file mount for media
app.mount("/media", StaticFiles(directory="app/media_store"), name="media")

# Routers
app.include_router(auth.router)
app.include_router(policies.router)
app.include_router(claims.router)
app.include_router(moderator.router)
app.include_router(siu.router)
app.include_router(ws.router)
app.include_router(efficiency.router)
app.include_router(downloads.router)
app.include_router(copilot.router)
app.include_router(similarity.router)


@app.get("/health")
def health():
    return {"status": "ok"}
