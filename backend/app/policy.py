"""Deterministic policy + risk engine.

Design notes
------------
* Policies are plain Python rules with stable IDs so the same decision
  logic can later be mirrored in OPA/Rego (see ARCHITECTURE.md §Policy
  engine swap). The gateway only talks to `PolicyEngine.evaluate`.
* Evaluation is **fail-closed**: any exception inside rule evaluation
  results in a BLOCK decision with the `P-FAIL-001` policy.
* Risk scoring is deterministic and derived from the action itself plus
  the *cumulative* session history (data already touched), which is what
  makes individually-permitted sequences detectable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

SENSITIVITY_LEVELS = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}

DESTINATION_TRUST = {
    "internal": 0,
    "partner": 1,
    "external_untrusted": 2,
    "unknown": 3,
}

SENSITIVITY_WEIGHT = {"public": 0, "internal": 2, "confidential": 8, "restricted": 15}
DESTINATION_WEIGHT = {
    "internal": 0,
    "partner": 8,
    "external_untrusted": 20,
    "unknown": 30,
}

TOOL_BASE_RISK = {
    "read_document": 5,
    "generate_report": 10,
    "save_to_destination": 8,
    "read_customer_records": 12,
    "aggregate_customer_data": 15,
    "create_summary": 18,
    "transfer_external": 20,
    "propose_record_modification": 10,
    "modify_operational_record": 25,
}

# Tools that always stop for a human decision before any side effect.
APPROVAL_REQUIRED_TOOLS = {"modify_operational_record"}

# Tool-specific destination constraints (legitimate transfer capability,
# but only for approved internal endpoints).
TOOL_ALLOWED_DESTINATIONS = {
    "save_to_destination": {"internal"},
    "transfer_external": {"partner", "external_untrusted", "unknown"},
}


@dataclass(frozen=True)
class Policy:
    id: str
    name: str
    category: str
    severity: str
    description: str
    effect: str  # "deny" | "require_approval" | "permit"


POLICIES: list[Policy] = [
    Policy(
        id="P-TOOL-001",
        name="Tool grant enforcement",
        category="tool",
        severity="high",
        description="An agent may only invoke tools explicitly granted to its role.",
        effect="deny",
    ),
    Policy(
        id="P-RES-001",
        name="Resource clearance enforcement",
        category="resource",
        severity="high",
        description="Resources above the agent's data clearance must not be read.",
        effect="deny",
    ),
    Policy(
        id="P-DEST-001",
        name="Destination allow-list",
        category="destination",
        severity="high",
        description="A tool may only write to destinations of an allowed trust class.",
        effect="deny",
    ),
    Policy(
        id="P-CUM-001",
        name="Cumulative data-exposure sequence rule",
        category="sequence",
        severity="critical",
        description=(
            "Sensitive data (confidential/restricted) read during the session "
            "must not be relayed to an untrusted external destination."
        ),
        effect="deny",
    ),
    Policy(
        id="P-CUM-002",
        name="Exfiltration content rule",
        category="sequence",
        severity="critical",
        description=(
            "Payloads flagged as containing PII or restricted content cannot be "
            "sent to non-internal destinations."
        ),
        effect="deny",
    ),
    Policy(
        id="P-TOOL-APPROVAL-001",
        name="Protected operation approval",
        category="approval",
        severity="high",
        description="Protected operational modifications require human approval.",
        effect="require_approval",
    ),
    Policy(
        id="P-RISK-001",
        name="Cumulative risk approval gate",
        category="risk",
        severity="medium",
        description="Actions with cumulative risk score >= approval threshold pause.",
        effect="require_approval",
    ),
    Policy(
        id="P-RISK-002",
        name="Cumulative risk block gate",
        category="risk",
        severity="high",
        description="Actions with cumulative risk score >= block threshold are denied.",
        effect="deny",
    ),
    Policy(
        id="P-FAIL-001",
        name="Fail-closed evaluation",
        category="system",
        severity="critical",
        description="If policy evaluation fails the action is denied by default.",
        effect="deny",
    ),
]

POLICY_INDEX = {p.id: p for p in POLICIES}


def risk_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Evaluation inputs / outputs
# ---------------------------------------------------------------------------


@dataclass
class EvalContext:
    """Everything the rules need to decide one action."""

    agent_id: str
    clearance: str
    granted_tools: list[str]
    session_id: str
    tool: str
    params: dict[str, Any]
    resource: str | None
    destination: str | None
    sensitivity: str
    # Prior persisted audit events of this session (oldest first).
    history: list[dict[str, Any]] = field(default_factory=list)
    # Set when this evaluation revalidates an approval decision.
    approval_context: bool = False


@dataclass
class Decision:
    decision: str  # ALLOW | BLOCK | REQUIRE_APPROVAL
    risk_score: float
    risk_level: str
    policies: list[str]
    explanation: str
    reasons: list[str] = field(default_factory=list)


def _sens_rank(level: str) -> int:
    return SENSITIVITY_LEVELS.get(level, 0)


def compute_risk(ctx: EvalContext) -> float:
    """Deterministic cumulative risk score in [0, 100]."""
    score = TOOL_BASE_RISK.get(ctx.tool, 25)
    score += SENSITIVITY_WEIGHT.get(ctx.sensitivity, 0)
    score += DESTINATION_WEIGHT.get(ctx.destination or "internal", 0)

    restricted_reads = {
        h.get("resource")
        for h in ctx.history
        if h.get("executed")
        and h.get("sensitivity") in {"confidential", "restricted"}
        and str(h.get("tool", "")).startswith("read_")
    }
    sensitive_writes = [
        h
        for h in ctx.history
        if h.get("executed")
        and h.get("side_effect")
        and h.get("sensitivity") in {"confidential", "restricted"}
    ]
    score += min(30.0, len(restricted_reads) * 10.0 + len(sensitive_writes) * 8.0)

    if ctx.params.get("contains_pii") or ctx.params.get("includes_pii"):
        score += 12.0
    if ctx.params.get("irreversible"):
        score += 8.0

    return round(min(100.0, score), 1)


def _touched_sensitive_data(ctx: EvalContext) -> list[dict[str, Any]]:
    return [
        h
        for h in ctx.history
        if h.get("executed")
        and h.get("sensitivity") in {"confidential", "restricted"}
        and str(h.get("tool", "")).startswith("read_")
    ]


# ---------------------------------------------------------------------------
# Rules: each returns (policy_id, explanation) when it fires.
# ---------------------------------------------------------------------------


def rule_tool_grant(ctx: EvalContext) -> tuple[str, str] | None:
    if ctx.tool not in ctx.granted_tools:
        return (
            "P-TOOL-001",
            f"Agent '{ctx.agent_id}' has no grant for tool '{ctx.tool}'. "
            f"Granted tools: {', '.join(ctx.granted_tools) or 'none'}.",
        )
    return None


def rule_resource_clearance(ctx: EvalContext) -> tuple[str, str] | None:
    if _sens_rank(ctx.sensitivity) > _sens_rank(ctx.clearance):
        return (
            "P-RES-001",
            f"Resource sensitivity '{ctx.sensitivity}' exceeds the clearance "
            f"'{ctx.clearance}' of agent '{ctx.agent_id}'.",
        )
    return None


def rule_destination_allowlist(ctx: EvalContext) -> tuple[str, str] | None:
    allowed = TOOL_ALLOWED_DESTINATIONS.get(ctx.tool)
    if not allowed or not ctx.destination:
        return None
    dest_class = ctx.destination.split("://", 1)[0]
    if dest_class in ("internal", "partner", "external_untrusted", "unknown"):
        if dest_class not in allowed:
            return (
                "P-DEST-001",
                f"Tool '{ctx.tool}' may only write to {sorted(allowed)} "
                f"destinations; requested '{ctx.destination}' is class "
                f"'{dest_class}'.",
            )
    else:
        return (
            "P-DEST-001",
            f"Unrecognised destination class for '{ctx.destination}'.",
        )
    return None


def rule_cumulative_exposure(ctx: EvalContext) -> tuple[str, str] | None:
    """The core differentiator: block sequences, not just single actions."""
    if not ctx.destination:
        return None
    dest_class = ctx.destination.split("://", 1)[0]
    if dest_class not in {"external_untrusted", "unknown", "partner"}:
        return None
    sensitive = _touched_sensitive_data(ctx)
    if not sensitive:
        return None
    if _sens_rank(ctx.sensitivity) < _sens_rank("confidential"):
        return None
    touched = ", ".join(sorted({str(h.get("resource")) for h in sensitive}))
    return (
        "P-CUM-001",
        f"Blocked sequence: this session read sensitive data ({touched}) and "
        f"now attempts to relay it to '{ctx.destination}'. Individually "
        f"permitted steps combine into a data-exposure path.",
    )


def rule_exfiltration_content(ctx: EvalContext) -> tuple[str, str] | None:
    if not ctx.destination:
        return None
    dest_class = ctx.destination.split("://", 1)[0]
    if dest_class in {"internal"}:
        return None
    if ctx.params.get("contains_pii") or ctx.params.get("includes_pii"):
        return (
            "P-CUM-002",
            f"Payload is flagged as containing PII/restricted content and the "
            f"destination '{ctx.destination}' is not an internal system.",
        )
    return None


def rule_protected_operation(ctx: EvalContext) -> tuple[str, str] | None:
    if ctx.tool in APPROVAL_REQUIRED_TOOLS:
        return (
            "P-TOOL-APPROVAL-001",
            f"'{ctx.tool}' is a protected operational write; human approval is "
            "required before execution.",
        )
    return None


# Order matters: denials are evaluated before approval gates.
DENY_RULES: list[Callable[[EvalContext], tuple[str, str] | None]] = [
    rule_tool_grant,
    rule_resource_clearance,
    rule_destination_allowlist,
    rule_cumulative_exposure,
    rule_exfiltration_content,
]

APPROVAL_RULES: list[Callable[[EvalContext], tuple[str, str] | None]] = [
    rule_protected_operation,
]


class PolicyEngine:
    """Deterministic authorization decisions (fail-closed)."""

    def __init__(
        self,
        approval_threshold: float = 65.0,
        block_threshold: float = 80.0,
    ) -> None:
        self.approval_threshold = approval_threshold
        self.block_threshold = block_threshold

    def evaluate(self, ctx: EvalContext) -> Decision:
        try:
            return self._evaluate(ctx)
        except Exception as exc:  # noqa: BLE001 - deliberate fail-closed path
            score = 100.0
            return Decision(
                decision="BLOCK",
                risk_score=score,
                risk_level="critical",
                policies=["P-FAIL-001"],
                explanation=(
                    "Fail-closed: policy evaluation raised "
                    f"{type(exc).__name__} ({exc}); the action was denied "
                    "because the policy state could not be established."
                ),
                reasons=["policy evaluation error"],
            )

    def _evaluate(self, ctx: EvalContext) -> Decision:
        score = compute_risk(ctx)
        level = risk_level(score)
        reasons: list[str] = []

        # 1) Deny rules (static + cumulative-sequence).
        for rule in DENY_RULES:
            hit = rule(ctx)
            if hit:
                pid, why = hit
                return Decision(
                    decision="BLOCK",
                    risk_score=score,
                    risk_level=level,
                    policies=[pid],
                    explanation=why,
                    reasons=[why],
                )

        # 2) Approval-required rules.
        if not ctx.approval_context:
            for rule in APPROVAL_RULES:
                hit = rule(ctx)
                if hit:
                    pid, why = hit
                    reasons.append(why)
                    return Decision(
                        decision="REQUIRE_APPROVAL",
                        risk_score=score,
                        risk_level=level,
                        policies=[pid],
                        explanation=why,
                        reasons=reasons,
                    )

            if score >= self.block_threshold:
                why = (
                    f"Cumulative risk score {score} exceeds the block threshold "
                    f"{self.block_threshold} after reviewing this session's "
                    "action history."
                )
                return Decision(
                    decision="BLOCK",
                    risk_score=score,
                    risk_level=level,
                    policies=["P-RISK-002"],
                    explanation=why,
                    reasons=[why],
                )

            if score >= self.approval_threshold:
                why = (
                    f"Cumulative risk score {score} reaches the approval "
                    f"threshold {self.approval_threshold}; a human must "
                    "authorize this action."
                )
                return Decision(
                    decision="REQUIRE_APPROVAL",
                    risk_score=score,
                    risk_level=level,
                    policies=["P-RISK-001"],
                    explanation=why,
                    reasons=[why],
                )

        why = (
            f"Action permitted: risk score {score} ({level}) is below the "
            "approval threshold, the tool is granted, and resource/destination "
            "checks passed."
        )
        return Decision(
            decision="ALLOW",
            risk_score=score,
            risk_level=level,
            policies=[],
            explanation=why,
            reasons=[why],
        )


def policies_as_dicts() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "severity": p.severity,
            "description": p.description,
            "effect": p.effect,
            "enabled": True,
        }
        for p in POLICIES
    ]


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)
