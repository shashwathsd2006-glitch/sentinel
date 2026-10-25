"""Central configuration for the SENTINEL-X backend.

All values can be overridden with environment variables (see .env.example).
No external services, API keys or network access are required at runtime.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    """Read an env var, treating empty values as unset."""
    value = os.environ.get(name, "")
    return value if value else default


@dataclass(frozen=True)
class Settings:
    """Runtime settings."""

    db_path: str = field(
        default_factory=lambda: _env(
            "SENTINEL_DB_PATH", str(BACKEND_DIR / "sentinel.db")
        )
    )
    # Risk thresholds used by the deterministic risk engine.
    approval_threshold: float = field(
        default_factory=lambda: float(_env("SENTINEL_APPROVAL_THRESHOLD", "65"))
    )
    block_threshold: float = field(
        default_factory=lambda: float(_env("SENTINEL_BLOCK_THRESHOLD", "80"))
    )
    # Single-use approvals expire after this many minutes.
    approval_ttl_minutes: int = field(
        default_factory=lambda: int(_env("SENTINEL_APPROVAL_TTL_MINUTES", "15"))
    )
    # Signing secret for execution tickets (gateway bypass protection).
    ticket_secret: str = field(
        default_factory=lambda: _env("SENTINEL_TICKET_SECRET", "")
    )

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


def get_settings() -> Settings:
    return Settings()


def get_ticket_secret() -> str:
    """Return the ticket signing secret.

    A random per-process secret is generated when none is configured. The
    secret is never exposed through the API.
    """
    secret = get_settings().ticket_secret
    if not secret:
        secret = secrets.token_hex(32)
        os.environ["SENTINEL_TICKET_SECRET"] = secret
    return secret
