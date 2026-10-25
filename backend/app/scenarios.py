"""Deterministic demonstration scenarios executed through the gateway.

Each scenario is a list of tool calls run sequentially in a dedicated
session. Results are persisted as :class:`ScenarioRun` /
:class:`ScenarioStep` rows, and any BLOCK produces an :class:`Incident`
with the full ordered action timeline as evidence.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .gateway import Gateway, GatewayResult, ToolCall, _run_summary
from .models import Event, Incident, ScenarioRun, ScenarioStep, utcnow

_PLACEHOLDER = re.compile(r"\{\{result\.([a-zA-Z0-9_]+)\}\}")


@dataclass(frozen=True)
class ScenarioStepSpec:
    label: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    title: str
    description: str
    attack: bool
    agent_id: str
    steps: tuple[ScenarioStepSpec, ...]


SCENARIOS: dict[str, ScenarioSpec] = {
    s.id: s
    for s in [
        ScenarioSpec(
            id="scenario_a",
            title="A — Legitimate workflow",
            description=(
                "Read a permitted internal document, generate a report and "
                "save it to an authorized internal destination. Expected: "
                "every step allowed with a complete audit trail."
            ),
            attack=False,
            agent_id="report-agent",
            steps=(
                ScenarioStepSpec(
                    label="Read permitted internal document",
                    tool="read_document",
                    params={"path": "kb/onboarding-guide.md"},
                ),
                ScenarioStepSpec(
                    label="Generate internal report",
                    tool="generate_report",
                    params={
                        "title": "Onboarding readiness report",
                        "source": "kb/onboarding-guide.md",
                        "classification": "internal",
                    },
                ),
                ScenarioStepSpec(
                    label="Save report to authorized internal destination",
                    tool="save_to_destination",
                    params={
                        "artifact_id": "{{result.artifact_id}}",
                        "destination": "internal://team-reports",
                    },
                ),
            ),
        ),
        ScenarioSpec(
            id="scenario_b",
            title="B — Multi-step data exposure",
            description=(
                "Read simulated customer records, aggregate them, create a "
                "sensitive summary, then attempt an external transfer. Each "
                "read is individually permitted; the gateway detects the "
                "cumulative sequence and blocks the transfer before the "
                "protected tool executes."
            ),
            attack=True,
            agent_id="support-agent",
            steps=(
                ScenarioStepSpec(
                    label="Read simulated customer records",
                    tool="read_customer_records",
                    params={"record_ids": ["cust-001", "cust-002"]},
                ),
                ScenarioStepSpec(
                    label="Aggregate sensitive customer data",
                    tool="aggregate_customer_data",
                    params={
                        "record_ids": ["cust-001", "cust-002"],
                        "fields": ["balance_eur", "email"],
                    },
                ),
                ScenarioStepSpec(
                    label="Create sensitive summary (contains PII)",
                    tool="create_summary",
                    params={
                        "title": "Customer risk summary",
                        "includes": ["name", "email", "balance", "support_notes"],
                        "contains_pii": True,
                    },
                ),
                ScenarioStepSpec(
                    label="Attempt external transfer of the summary",
                    tool="transfer_external",
                    params={
                        "artifact_id": "{{result.artifact_id}}",
                        "destination": "external_untrusted://filedrop.unknown",
                    },
                ),
            ),
        ),
        ScenarioSpec(
            id="scenario_c",
            title="C — Human approval",
            description=(
                "Propose a change to a protected operational record, then "
                "attempt to apply it. The gateway pauses the action, a human "
                "approves or rejects the exact pending action, and the "
                "decision is revalidated immediately before execution."
            ),
            attack=False,
            agent_id="ops-agent",
            steps=(
                ScenarioStepSpec(
                    label="Propose protected record modification",
                    tool="propose_record_modification",
                    params={
                        "record_id": "ops-4711",
                        "changes": {"rate_limit_rps": 500, "max_retries": 5},
                        "requested_by": "ops-agent",
                    },
                ),
                ScenarioStepSpec(
                    label="Apply protected operational modification",
                    tool="modify_operational_record",
                    params={
                        "record_id": "ops-4711",
                        "changes": {"rate_limit_rps": 500, "max_retries": 5},
                        "requested_by": "ops-agent",
                    },
                ),
            ),
        ),
    ]
}


def _resolve(params: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Substitute ``{{result.field}}`` with the previous step's result."""
    if not previous:
        return params

    def lookup(key: str, default: Any) -> Any:
        if key in previous:
            return previous[key]
        inner = previous.get("result")
        if isinstance(inner, dict) and key in inner:
            return inner[key]
        return default

    def sub(value: Any) -> Any:
        if isinstance(value, str):
            match = _PLACEHOLDER.fullmatch(value.strip())
            if match:
                return lookup(match.group(1), value)
            return _PLACEHOLDER.sub(
                lambda m: str(lookup(m.group(1), m.group(0))), value
            )
        if isinstance(value, dict):
            return {k: sub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [sub(v) for v in value]
        return value

    return {k: sub(v) for k, v in params.items()}


def run_scenario(db: Session, scenario_id: str) -> ScenarioRun:
    spec = SCENARIOS.get(scenario_id)
    if spec is None:
        raise KeyError(scenario_id)

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    run = ScenarioRun(
        id=run_id,
        scenario_id=spec.id,
        title=spec.title,
        status="running",
        session_id=session_id,
        agent_id=spec.agent_id,
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()

    gateway = Gateway(db)
    previous: dict[str, Any] | None = None
    paused = False
    counts = {"allowed": 0, "blocked": 0, "approval": 0, "executed": 0}

    for index, step_spec in enumerate(spec.steps):
        if paused:
            continue
        params = _resolve(step_spec.params, previous)
        call = ToolCall(
            agent_id=spec.agent_id,
            session_id=session_id,
            tool=step_spec.tool,
            params=params,
            run_id=run_id,
            step_index=index,
            scenario_id=spec.id,
            label=step_spec.label,
        )
        result: GatewayResult = gateway.act(call)

        if result.decision == "ALLOW":
            counts["allowed"] += 1
            status = "executed" if result.executed else "failed"
        elif result.decision == "BLOCK":
            counts["blocked"] += 1
            status = "blocked"
        elif result.decision == "REQUIRE_APPROVAL":
            counts["approval"] += 1
            status = "pending_approval"
        else:  # pragma: no cover - defensive
            status = "unknown"
        if result.executed:
            counts["executed"] += 1

        step = ScenarioStep(
            run_id=run_id,
            step_index=index,
            label=step_spec.label,
            tool=step_spec.tool,
            params_json=json.dumps(params, sort_keys=True, default=str),
            status=status,
            decision=result.decision,
            executed=result.executed,
            risk_score=result.risk_score,
            risk_level=result.risk_level,
            explanation=result.explanation,
            policy_ids=json.dumps(result.policies),
            event_id=result.event_id,
            approval_id=result.approval_id,
        )
        db.add(step)
        db.flush()

        if result.decision == "BLOCK":
            incident = _create_incident(db, run, step, result, session_id, spec)
            run.incident_id = incident.id

        if result.decision == "REQUIRE_APPROVAL":
            paused = True

        previous = result.result if isinstance(result.result, dict) else None

    run.allowed_count = counts["allowed"]
    run.blocked_count = counts["blocked"]
    run.approval_count = counts["approval"]
    run.executed_count = counts["executed"]

    steps = list(run.steps)
    if paused:
        run.status = "awaiting_approval"
        pending_index = next(
            (s.step_index for s in steps if s.status == "pending_approval"), None
        )
        run.summary = (
            f"{len(steps)} step(s) defined; paused at step "
            f"{(pending_index or 0) + 1} awaiting human approval. No protected "
            "modification has been performed yet."
        )
    else:
        run.status = "completed"
        run.finished_at = utcnow()
        run.summary = _run_summary(run, steps)

    db.commit()
    db.refresh(run)
    return run


def _create_incident(
    db: Session,
    run: ScenarioRun,
    step: ScenarioStep,
    result: GatewayResult,
    session_id: str,
    spec: ScenarioSpec,
) -> Incident:
    events = db.scalars(
        select(Event).where(Event.session_id == session_id).order_by(Event.id)
    ).all()
    timeline = [
        f"{i + 1}. {e.tool} -> {e.decision} (risk {e.risk_score})"
        for i, e in enumerate(events)
    ]
    trigger = result.policies[0] if result.policies else "P-FAIL-001"
    severity = "critical" if trigger.startswith("P-CUM") else "high"
    sequence = (
        "Attack sequence observed in order: "
        + " -> ".join(f"{e.tool}[{e.decision}]" for e in events)
        + f". Blocked at '{step.tool}'."
    )
    incident = Incident(
        id=f"inc-{uuid.uuid4().hex[:12]}",
        run_id=run.id,
        scenario_id=spec.id,
        session_id=session_id,
        severity=severity,
        title=f"Blocked {step.tool} on {spec.title}",
        trigger_policy=trigger,
        blocked_tool=step.tool,
        blocked_resource=(
            _resource_of(db, step.event_id) if step.event_id else None
        ),
        destination=_destination_of(db, step.event_id) if step.event_id else None,
        explanation=result.explanation,
        sequence_summary=sequence,
        protected_tool_executed=False,
        blocked_event_id=step.event_id,
        status="open",
    )
    db.add(incident)
    db.flush()
    return incident


def _resource_of(db: Session, event_id: int | None) -> str | None:
    if event_id is None:
        return None
    event = db.get(Event, event_id)
    return event.resource if event else None


def _destination_of(db: Session, event_id: int | None) -> str | None:
    if event_id is None:
        return None
    event = db.get(Event, event_id)
    return event.destination if event else None
