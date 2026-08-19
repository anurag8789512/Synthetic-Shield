from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, Base
from app.routers import auth, policies, claims, moderator, siu, ws, efficiency, downloads, copilot, similarity

# Create all tables on startup
Base.metadata.create_all(bind=engine)

# Ensure media directory exists
Path("app/media_store").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SyntheticShield API", version="0.1.0")

# CORS — allow all local dev origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:8443", "http://localhost:5173"],
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
