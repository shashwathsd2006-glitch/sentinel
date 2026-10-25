"""FastAPI application: REST API for the SENTINEL-X security gateway."""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .benchmark import compute_benchmark_metrics, run_benchmark
from .config import get_settings
from .db import SessionLocal, get_db, init_db
from .gateway import Gateway, GatewayError
from .models import Agent, Approval, Event, Incident, ScenarioRun, utcnow
from .policy import POLICY_INDEX, policies_as_dicts
from .scenarios import SCENARIOS, run_scenario
from .schemas import ApprovalDecisionRequest
from .tools import list_tool_specs

settings = get_settings()

app = FastAPI(
    title="SENTINEL-X API",
    description="Runtime security gateway for autonomous AI agents",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.exception_handler(GatewayError)
def gateway_error_handler(request: Request, exc: GatewayError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _jloads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def agent_to_dict(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "clearance": agent.clearance,
        "granted_tools": _jloads(agent.granted_tools, []),
        "description": agent.description,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "ts": event.ts.isoformat() if event.ts else None,
        "run_id": event.run_id,
        "scenario_id": event.scenario_id,
        "session_id": event.session_id,
        "agent_id": event.agent_id,
        "step_index": event.step_index,
        "tool": event.tool,
        "resource": event.resource,
        "destination": event.destination,
        "sensitivity": event.sensitivity,
        "action_summary": event.action_summary,
        "risk_score": event.risk_score,
        "risk_level": event.risk_level,
        "decision": event.decision,
        "policies": _jloads(event.policy_ids, []),
        "explanation": event.explanation,
        "executed": event.executed,
        "side_effect": event.side_effect,
        "approval_id": event.approval_id,
        "latency_ms": event.latency_ms,
        "result": _jloads(event.result, None),
    }


def approval_to_dict(approval: Approval) -> dict[str, Any]:
    expired = (
        approval.status == "PENDING" and utcnow() > approval.expires_at
    )
    return {
        "id": approval.id,
        "run_id": approval.run_id,
        "step_index": approval.step_index,
        "session_id": approval.session_id,
        "agent_id": approval.agent_id,
        "tool": approval.tool,
        "params": _jloads(approval.params_json, {}),
        "resource": approval.resource,
        "destination": approval.destination,
        "sensitivity": approval.sensitivity,
        "risk_score": approval.risk_score,
        "risk_level": approval.risk_level,
        "explanation": approval.explanation,
        "policies": _jloads(approval.policy_ids, []),
        "fingerprint": approval.fingerprint,
        "status": "EXPIRED" if expired else approval.status,
        "requested_at": approval.requested_at.isoformat() if approval.requested_at else None,
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        "decision": approval.decision,
        "decided_by": approval.decided_by,
        "consumed": approval.consumed,
        "execution_event_id": approval.execution_event_id,
        "outcome": approval.outcome,
    }


def step_to_dict(step) -> dict[str, Any]:
    return {
        "step_index": step.step_index,
        "label": step.label,
        "tool": step.tool,
        "params": _jloads(step.params_json, {}),
        "status": step.status,
        "decision": step.decision,
        "executed": step.executed,
        "risk_score": step.risk_score,
        "risk_level": step.risk_level,
        "explanation": step.explanation,
        "policies": _jloads(step.policy_ids, []),
        "event_id": step.event_id,
        "approval_id": step.approval_id,
    }


def run_to_dict(run: ScenarioRun, include_steps: bool = True) -> dict[str, Any]:
    data = {
        "id": run.id,
        "scenario_id": run.scenario_id,
        "title": run.title,
        "status": run.status,
        "session_id": run.session_id,
        "agent_id": run.agent_id,
        "summary": run.summary,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "incident_id": run.incident_id,
        "allowed_count": run.allowed_count,
        "blocked_count": run.blocked_count,
        "approval_count": run.approval_count,
        "executed_count": run.executed_count,
    }
    if include_steps:
        data["steps"] = [step_to_dict(s) for s in run.steps]
        approval_ids = [s.approval_id for s in run.steps if s.approval_id]
        data["approvals"] = []
        if approval_ids:
            rows = (
                session_query_approvals(run, approval_ids)
            )
            data["approvals"] = rows
    return data


def session_query_approvals(run: ScenarioRun, approval_ids: list[str]) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.scalars(
                select(Approval).where(Approval.id.in_(approval_ids))
            ).all()
        )
        return [approval_to_dict(a) for a in rows]
    finally:
        db.close()


def incident_to_dict(incident: Incident) -> dict[str, Any]:
    return {
        "id": incident.id,
        "run_id": incident.run_id,
        "scenario_id": incident.scenario_id,
        "session_id": incident.session_id,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "severity": incident.severity,
        "title": incident.title,
        "trigger_policy": incident.trigger_policy,
        "trigger_policy_name": POLICY_INDEX.get(incident.trigger_policy).name
        if incident.trigger_policy in POLICY_INDEX
        else None,
        "trigger_policy_description": POLICY_INDEX.get(
            incident.trigger_policy
        ).description
        if incident.trigger_policy in POLICY_INDEX
        else None,
        "blocked_tool": incident.blocked_tool,
        "blocked_resource": incident.blocked_resource,
        "destination": incident.destination,
        "explanation": incident.explanation,
        "sequence_summary": incident.sequence_summary,
        "protected_tool_executed": incident.protected_tool_executed,
        "blocked_event_id": incident.blocked_event_id,
        "status": incident.status,
    }


# ---------------------------------------------------------------------------
# Health & reference data
# ---------------------------------------------------------------------------


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(select(func.count()).select_from(Event))
    return {
        "status": "ok",
        "service": "sentinel-x",
        "database": "ok",
        "database_url": settings.database_url.split("/")[-1],
        "time": utcnow().isoformat() + "Z",
        "policies_loaded": len(POLICY_INDEX),
        "fail_closed": True,
    }


@app.get("/api/agents")
def list_agents(db: Session = Depends(get_db)) -> dict[str, Any]:
    agents = db.scalars(select(Agent).order_by(Agent.id)).all()
    return {"items": [agent_to_dict(a) for a in agents], "total": len(agents)}


@app.get("/api/policies")
def list_policies() -> dict[str, Any]:
    s = get_settings()
    return {
        "items": policies_as_dicts(),
        "total": len(POLICY_INDEX),
        "engine": "deterministic-python (OPA/Rego-ready interface)",
        "thresholds": {
            "approval_threshold": s.approval_threshold,
            "block_threshold": s.block_threshold,
            "approval_ttl_minutes": s.approval_ttl_minutes,
        },
        "fail_closed": True,
    }


@app.get("/api/tools")
def list_tools() -> dict[str, Any]:
    items = list_tool_specs()
    return {"items": items, "total": len(items)}


@app.get("/api/scenarios")
def list_scenarios() -> dict[str, Any]:
    items = [
        {
            "id": spec.id,
            "title": spec.title,
            "description": spec.description,
            "attack": spec.attack,
            "agent_id": spec.agent_id,
            "steps": [
                {"index": i, "label": s.label, "tool": s.tool}
                for i, s in enumerate(spec.steps)
            ],
        }
        for spec in SCENARIOS.values()
    ]
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------


@app.get("/api/events")
def list_events(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scenario: str | None = Query(None, description="scenario_id or 'benchmark'"),
    decision: str | None = Query(None),
    agent: str | None = Query(None),
    session_id: str | None = Query(None),
    run_id: str | None = Query(None),
) -> dict[str, Any]:
    stmt = select(Event)
    count_stmt = select(func.count()).select_from(Event)
    if scenario:
        stmt = stmt.where(Event.scenario_id == scenario)
        count_stmt = count_stmt.where(Event.scenario_id == scenario)
    if decision:
        stmt = stmt.where(Event.decision == decision)
        count_stmt = count_stmt.where(Event.decision == decision)
    if agent:
        stmt = stmt.where(Event.agent_id == agent)
        count_stmt = count_stmt.where(Event.agent_id == agent)
    if session_id:
        stmt = stmt.where(Event.session_id == session_id)
        count_stmt = count_stmt.where(Event.session_id == session_id)
    if run_id:
        stmt = stmt.where(Event.run_id == run_id)
        count_stmt = count_stmt.where(Event.run_id == run_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Event.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [event_to_dict(e) for e in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------


@app.get("/api/approvals")
def list_approvals(
    db: Session = Depends(get_db),
    status: str | None = Query(None, description="PENDING | APPROVED | REJECTED | ..."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    stmt = select(Approval)
    count_stmt = select(func.count()).select_from(Approval)
    if status:
        stmt = stmt.where(Approval.status == status)
        count_stmt = count_stmt.where(Approval.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Approval.requested_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [approval_to_dict(a) for a in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    gateway = Gateway(db)
    result = gateway.decide_approval(
        approval_id,
        approve=body.decision == "approve",
        actor=body.actor,
        fingerprint=body.fingerprint,
    )
    approval = db.get(Approval, approval_id)
    return {
        "approval": approval_to_dict(approval),
        "result": result.as_dict(),
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@app.post("/api/scenarios/{scenario_id}/run", status_code=201)
def run_scenario_endpoint(scenario_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}")
    run = run_scenario(db, scenario_id)
    return run_to_dict(run)


@app.get("/api/scenarios/runs")
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(ScenarioRun)) or 0
    rows = db.scalars(
        select(ScenarioRun)
        .order_by(ScenarioRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [run_to_dict(r, include_steps=False) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/scenarios/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(ScenarioRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    data = run_to_dict(run)
    events = db.scalars(
        select(Event).where(Event.run_id == run_id).order_by(Event.id)
    ).all()
    data["events"] = [event_to_dict(e) for e in events]
    if run.incident_id:
        incident = db.get(Incident, run.incident_id)
        data["incident"] = incident_to_dict(incident) if incident else None
    return data


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


@app.get("/api/incidents")
def list_incidents(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
) -> dict[str, Any]:
    stmt = select(Incident)
    count_stmt = select(func.count()).select_from(Incident)
    if status:
        stmt = stmt.where(Incident.status == status)
        count_stmt = count_stmt.where(Incident.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [incident_to_dict(i) for i in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"unknown incident: {incident_id}")

    events = db.scalars(
        select(Event)
        .where(Event.session_id == incident.session_id)
        .order_by(Event.id)
    ).all()
    timeline = []
    for i, e in enumerate(events):
        entry = event_to_dict(e)
        entry["index"] = i + 1
        timeline.append(entry)

    steps = []
    run = db.get(ScenarioRun, incident.run_id) if incident.run_id else None
    if run:
        steps = [step_to_dict(s) for s in run.steps]

    return {
        "incident": incident_to_dict(incident),
        "timeline": timeline,
        "steps": steps,
        "run": run_to_dict(run, include_steps=False) if run else None,
        "attack_explanation": _attack_explanation(incident, timeline),
    }


def _attack_explanation(incident: Incident, timeline: list[dict]) -> str:
    allowed = [t for t in timeline if t["decision"] in {"ALLOW", "APPROVED"}]
    blocked = [t for t in timeline if t["decision"] == "BLOCK"]
    lines = [
        f"Sequence of {len(timeline)} evaluated action(s) in session "
        f"{incident.session_id}.",
        f"Individually permitted steps: "
        + (", ".join(t["tool"] for t in allowed) or "none")
        + ".",
        f"Blocked operation: {incident.blocked_tool}"
        + (f" -> {incident.destination}" if incident.destination else "")
        + f" (policy {incident.trigger_policy}).",
        incident.explanation,
        "Evidence: the protected tool did not execute "
        f"(protected_tool_executed={incident.protected_tool_executed}); no "
        "outbound side effect was recorded.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metrics & evaluation
# ---------------------------------------------------------------------------


@app.get("/api/metrics")
def metrics(db: Session = Depends(get_db)) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(Event)) or 0

    def count_decision(decision: str) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.decision == decision)
            )
            or 0
        )

    executed = (
        db.scalar(
            select(func.count()).select_from(Event).where(Event.executed.is_(True))
        )
        or 0
    )
    side_effects = (
        db.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.side_effect.is_(True))
        )
        or 0
    )
    avg_latency = (
        db.scalar(select(func.avg(Event.latency_ms)).select_from(Event)) or 0.0
    )
    pending = (
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(Approval.status == "PENDING")
        )
        or 0
    )
    incidents = (
        db.scalar(
            select(func.count()).select_from(Incident).where(Incident.status == "open")
        )
        or 0
    )

    by_scenario: dict[str, dict[str, int]] = {}
    rows = db.execute(
        select(Event.scenario_id, Event.decision, func.count()).group_by(
            Event.scenario_id, Event.decision
        )
    ).all()
    for scenario_id, decision, count in rows:
        key = scenario_id or "manual"
        by_scenario.setdefault(key, {})
        by_scenario[key][decision] = count

    allowed = count_decision("ALLOW")
    blocked = count_decision("BLOCK")
    approval_required = count_decision("REQUIRE_APPROVAL")
    approved = count_decision("APPROVED")
    rejected = count_decision("REJECTED")
    expired = count_decision("EXPIRED")
    prevented = blocked + rejected + expired
    stopped = prevented + approval_required

    return {
        "generated_at": utcnow().isoformat() + "Z",
        "actions_evaluated": total,
        "allowed": allowed,
        "blocked": blocked,
        "approval_required": approval_required,
        "approved_executed": approved,
        "rejected": rejected,
        "expired": expired,
        "executed_actions": executed,
        "side_effects_realized": side_effects,
        "prevented_side_effects": prevented,
        "pending_approvals": pending,
        "open_incidents": incidents,
        "avg_decision_latency_ms": round(float(avg_latency), 3),
        "by_scenario": by_scenario,
        "evaluation": compute_benchmark_metrics(db),
    }


@app.post("/api/evaluation/run")
def run_evaluation(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Run the deterministic benchmark suite through the live gateway."""
    return run_benchmark(db)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover - manual entrypoint
    import uvicorn

    host = os.environ.get("SENTINEL_HOST", "127.0.0.1")
    # 8010 avoids clashing with services commonly bound to 8000 on this machine.
    port = int(os.environ.get("SENTINEL_PORT", "8010"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
