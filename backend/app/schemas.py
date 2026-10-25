"""Pydantic request schemas (input validation)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    actor: str = Field(min_length=1, max_length=120, description="Human reviewer ID")
    fingerprint: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Optional SHA-256 fingerprint of the pending action. When supplied "
            "it must match the stored fingerprint or the request is rejected "
            "as an altered action."
        ),
    )
