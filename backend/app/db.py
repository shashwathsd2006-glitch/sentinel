"""Database engine, session management and startup initialization."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables, apply lightweight migrations and seed reference data.

    This is the project's reliable startup initialization path (no Alembic
    migrations are required for the MVP; see ARCHITECTURE.md).
    """
    from sqlalchemy import inspect, text

    from . import models  # noqa: F401  (register tables)
    from .seed import seed_reference_data

    Base.metadata.create_all(bind=engine)

    # Forward-compatible column additions for databases created by an older
    # revision of the code (SQLite cannot ALTER via create_all).
    inspector = inspect(engine)
    if "test_results" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("test_results")}
        if "e2e_ms" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE test_results ADD COLUMN e2e_ms FLOAT DEFAULT 0")
                )

    db = SessionLocal()
    try:
        seed_reference_data(db)
        db.commit()
    finally:
        db.close()
