"""SQLAlchemy models: agents, audit events, approvals, runs, incidents, tests."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Agent(Base):
    """Registered AI agent with a clearance level and granted tools."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(60))
    clearance: Mapped[str] = mapped_column(String(30))  # data-sensitivity level
    granted_tools: Mapped[str] = mapped_column(Text)  # JSON list of tool names
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Event(Base):
    """Immutable audit event produced by the security gateway.

    Every evaluated action gets one row, whether it was allowed, blocked or
    paused for approval. `executed` records whether the protected tool
    actually ran (attempted vs. actual side effect).
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scenario_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool: Mapped[str] = mapped_column(String(80), index=True)
    resource: Mapped[str | None] = mapped_column(String(240), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(240), nullable=True)
    sensitivity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action_summary: Mapped[str] = mapped_column(Text, default="")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    decision: Mapped[str] = mapped_column(String(30), index=True)
    policy_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    explanation: Mapped[str] = mapped_column(Text, default="")
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    side_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[str] = mapped_column(Text, default="")  # JSON payload


class Approval(Base):
    """Single-use, expiring approval bound to one exact pending action."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(80))
    params_json: Mapped[str] = mapped_column(Text)
    resource: Mapped[str | None] = mapped_column(String(240), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(240), nullable=True)
    sensitivity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    explanation: Mapped[str] = mapped_column(Text, default="")
    policy_ids: Mapped[str] = mapped_column(Text, default="[]")
    # SHA-256 fingerprint over tool + canonical params + agent + session.
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScenarioRun(Base):
    """One execution of a demonstration scenario."""

    __tablename__ = "scenario_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    session_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allowed_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    approval_count: Mapped[int] = mapped_column(Integer, default=0)
    executed_count: Mapped[int] = mapped_column(Integer, default=0)

    steps: Mapped[list["ScenarioStep"]] = relationship(
        back_populates="run",
        order_by="ScenarioStep.step_index",
        cascade="all, delete-orphan",
    )


class ScenarioStep(Base):
    """Individual step result inside a scenario run."""

    __tablename__ = "scenario_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scenario_runs.id"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200))
    tool: Mapped[str] = mapped_column(String(80))
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    explanation: Mapped[str] = mapped_column(Text, default="")
    policy_ids: Mapped[str] = mapped_column(Text, default="[]")
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[ScenarioRun] = relationship(back_populates="steps")


class Incident(Base):
    """Security incident: a dangerous sequence stopped by the gateway."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    severity: Mapped[str] = mapped_column(String(20), default="high")
    title: Mapped[str] = mapped_column(String(200))
    trigger_policy: Mapped[str] = mapped_column(String(60))
    blocked_tool: Mapped[str] = mapped_column(String(80))
    blocked_resource: Mapped[str | None] = mapped_column(String(240), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(240), nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    sequence_summary: Mapped[str] = mapped_column(Text, default="")
    # Evidence: did the protected tool actually run? Always False for blocks.
    protected_tool_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")


class TestResult(Base):
    """Recorded outcome of an automated test / benchmark case."""

    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite: Mapped[str] = mapped_column(String(80), index=True)
    case: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))  # "attack" | "benign"
    expected: Mapped[str] = mapped_column(String(60))
    actual: Mapped[str] = mapped_column(String(60))
    passed: Mapped[bool] = mapped_column(Boolean)
    detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    prevented: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    false_positive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    # Full case wall time (evaluation + persistence + tool execution),
    # deliberately kept separate from policy-evaluation latency.
    e2e_ms: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
