"""Pydantic request schemas (input validation)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    actor: str = Field(
        min_length=1,
        max_length=120,
        description="Human reviewer ID",
    )
    fingerprint: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Optional SHA-256 fingerprint of the pending action. When supplied "
            "it must match the stored fingerprint or the request is rejected "
            "as an altered action."
        ),
    )

    @field_validator("actor")
    @classmethod
    def actor_must_be_meaningful(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("actor must not be empty or whitespace-only")
        return cleaned

    @field_validator("fingerprint")
    @classmethod
    def fingerprint_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        if len(cleaned) > 64:
            raise ValueError("fingerprint too long")
        return cleaned
