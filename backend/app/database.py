from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite needs this
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """Lightweight in-place migration for existing SQLite files (no Alembic in this project)."""
    with engine.connect() as conn:
        session_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sessions)")]
        if session_cols and "owner_type" not in session_cols:
            conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN owner_type VARCHAR NOT NULL DEFAULT 'user'")
            conn.commit()

        claim_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(claims)")]
        if claim_cols and "claim_amount_cents" not in claim_cols:
            conn.exec_driver_sql("ALTER TABLE claims ADD COLUMN claim_amount_cents INTEGER")
            conn.commit()
        if claim_cols and "valuation_report" not in claim_cols:
            conn.exec_driver_sql("ALTER TABLE claims ADD COLUMN valuation_report TEXT")
            conn.commit()
        if claim_cols and "incident_at" not in claim_cols:
            conn.exec_driver_sql("ALTER TABLE claims ADD COLUMN incident_at DATETIME")
            conn.commit()
