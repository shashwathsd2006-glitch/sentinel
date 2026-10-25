"""The SENTINEL-X runtime security gateway.

All protected tool execution flows through :class:`Gateway`. The gateway:

1. builds an authorization context (agent, session, tool, resource,
   destination, sensitivity, action history),
2. asks the deterministic :class:`~app.policy.PolicyEngine` for a decision,
3. enforces ALLOW / BLOCK / REQUIRE_APPROVAL,
4. issues single-use signed execution tickets for allowed actions,
5. persists an audit event for every evaluated action (attempted vs.
   executed), and
6. revalidates authorization immediately before an approved action runs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Agent, Approval, Event, ScenarioRun, ScenarioStep, utcnow
from .policy import (
    EvalContext,
    PolicyEngine,
    dumps,
)
from .tools import (
    ARTIFACTS,
    DOCUMENTS,
    GatewayBypassError,
    TOOLS,
    execute_tool,
    issue_ticket,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GatewayError(Exception):
    status_code = 400
    code = "gateway_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AgentNotFound(GatewayError):
    status_code = 404
    code = "agent_not_found"


class ToolNotFound(GatewayError):
    status_code = 404
    code = "tool_not_found"


class ApprovalNotFound(GatewayError):
    status_code = 404
    code = "approval_not_found"


class ApprovalConflict(GatewayError):
    status_code = 409
    code = "approval_conflict"


class ApprovalExpiredError(ApprovalConflict):
    code = "approval_expired"


class ApprovalTampered(ApprovalConflict):
    code = "approval_params_mismatch"


# ---------------------------------------------------------------------------
# Request / result objects
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    agent_id: str
    session_id: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    step_index: int | None = None
    scenario_id: str | None = None
    resource: str | None = None
    destination: str | None = None
    sensitivity: str | None = None
    label: str | None = None


@dataclass
class GatewayResult:
    decision: str
    event_id: int | None
    risk_score: float
    risk_level: str
    policies: list[str]
    explanation: str
    executed: bool
    side_effect: bool
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    latency_ms: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "event_id": self.event_id,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "policies": self.policies,
            "explanation": self.explanation,
            "executed": self.executed,
            "side_effect": self.side_effect,
            "approval_id": self.approval_id,
            "result": self.result,
            "latency_ms": round(self.latency_ms, 3),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Context derivation (params -> authorization attributes)
# ---------------------------------------------------------------------------

_PII_KEYS = {"email", "balance", "balance_eur", "name", "support_notes", "ssn"}


def derive_resource(tool: str, params: dict[str, Any]) -> str | None:
    if tool == "read_document":
        return str(params.get("path") or "unknown-document")
    if tool in {"read_customer_records", "aggregate_customer_data"}:
        ids = params.get("record_ids")
        if ids:
            return "customer_records:" + ",".join(str(i) for i in ids)
        return "customer_records"
    if tool == "create_summary":
        return str(params.get("title") or "customer-summary")
    if tool == "generate_report":
        return str(params.get("title") or "report")
    if tool in {"save_to_destination", "transfer_external"}:
        return str(params.get("artifact_id") or "artifact")
    if tool in {"propose_record_modification", "modify_operational_record"}:
        return str(params.get("record_id") or "operational-record")
    return params.get("resource")


def derive_destination(tool: str, params: dict[str, Any]) -> str | None:
    dest = params.get("destination")
    if dest:
        return str(dest)
    if tool == "transfer_external":
        return "external_untrusted://unknown"
    return None


def derive_sensitivity(tool: str, params: dict[str, Any]) -> str:
    if tool == "read_document":
        doc = DOCUMENTS.get(str(params.get("path")), {})
        return str(doc.get("classification", "internal"))
    if tool in {"read_customer_records", "aggregate_customer_data"}:
        return "restricted"
    if tool == "create_summary":
        includes = set(params.get("includes") or [])
        if params.get("contains_pii") or (includes & _PII_KEYS):
            return "restricted"
        return "confidential"
    if tool == "generate_report":
        return str(params.get("classification", "internal"))
    if tool == "save_to_destination":
        artifact = ARTIFACTS.get(str(params.get("artifact_id")))
        return str(artifact["classification"]) if artifact else "internal"
    if tool == "transfer_external":
        artifact = ARTIFACTS.get(str(params.get("artifact_id")))
        return str(artifact["classification"]) if artifact else "internal"
    if tool in {"propose_record_modification", "modify_operational_record"}:
        return "confidential"
    return str(params.get("sensitivity", "internal"))


def action_summary(call: ToolCall, resource: str | None, destination: str | None) -> str:
    bits = [f"{call.tool}("]
    detail = []
    if resource:
        detail.append(f"resource={resource}")
    if destination:
        detail.append(f"destination={destination}")
    if not detail:
        detail.append(json.dumps(call.params, sort_keys=True, default=str)[:160])
    bits.append(", ".join(detail))
    bits.append(")")
    return "".join(bits)


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------


class Gateway:
    """Central authorization and execution chokepoint."""

    def __init__(self, db: Session, engine: PolicyEngine | None = None) -> None:
        settings = get_settings()
        self.db = db
        self.engine = engine or PolicyEngine(
            approval_threshold=settings.approval_threshold,
            block_threshold=settings.block_threshold,
        )
        self.settings = settings

    # -- helpers ------------------------------------------------------------

    def _agent(self, agent_id: str) -> Agent:
        agent = self.db.get(Agent, agent_id)
        if agent is None:
            raise AgentNotFound(f"unknown agent: {agent_id}")
        return agent

    def _history_dicts(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(Event).where(Event.session_id == session_id).order_by(Event.id)
        ).all()
        return [
            {
                "id": r.id,
                "tool": r.tool,
                "resource": r.resource,
                "destination": r.destination,
                "sensitivity": r.sensitivity,
                "decision": r.decision,
                "executed": r.executed,
                "side_effect": r.side_effect,
            }
            for r in rows
        ]

    def build_context(
        self,
        agent: Agent,
        call: ToolCall,
        *,
        approval_context: bool = False,
        resource: str | None = None,
        destination: str | None = None,
        sensitivity: str | None = None,
    ) -> EvalContext:
        return EvalContext(
            agent_id=agent.id,
            clearance=agent.clearance,
            granted_tools=json.loads(agent.granted_tools),
            session_id=call.session_id,
            tool=call.tool,
            params=call.params,
            resource=resource,
            destination=destination,
            sensitivity=sensitivity,
            history=self._history_dicts(call.session_id),
            approval_context=approval_context,
        )

    def _persist_event(
        self,
        call: ToolCall,
        *,
        decision: str,
        risk_score: float,
        level: str,
        policies: list[str],
        explanation: str,
        executed: bool,
        side_effect: bool,
        resource: str | None,
        destination: str | None,
        sensitivity: str,
        latency_ms: float,
        approval_id: str | None = None,
        result: Any = None,
        action: str | None = None,
    ) -> Event:
        event = Event(
            run_id=call.run_id,
            scenario_id=call.scenario_id,
            session_id=call.session_id,
            agent_id=call.agent_id,
            step_index=call.step_index,
            tool=call.tool,
            resource=resource,
            destination=destination,
            sensitivity=sensitivity,
            action_summary=action or action_summary(call, resource, destination),
            risk_score=risk_score,
            risk_level=level,
            decision=decision,
            policy_ids=dumps(policies),
            explanation=explanation,
            executed=executed,
            side_effect=side_effect,
            approval_id=approval_id,
            latency_ms=latency_ms,
            result=dumps(result) if result is not None else "",
        )
        self.db.add(event)
        self.db.flush()
        return event

    # -- main entry points --------------------------------------------------

    def act(self, call: ToolCall) -> GatewayResult:
        """Evaluate one tool call and, when allowed, execute it."""
        if call.tool not in TOOLS:
            raise ToolNotFound(f"unknown tool: {call.tool}")
        agent = self._agent(call.agent_id)

        resource = call.resource or derive_resource(call.tool, call.params)
        destination = call.destination or derive_destination(call.tool, call.params)
        sensitivity = call.sensitivity or derive_sensitivity(call.tool, call.params)

        ctx = self.build_context(
            agent, call, resource=resource, destination=destination,
            sensitivity=sensitivity,
        )

        started = time.perf_counter()
        decision = self.engine.evaluate(ctx)
        latency_ms = (time.perf_counter() - started) * 1000.0

        common = dict(
            decision=decision.decision,
            risk_score=decision.risk_score,
            level=decision.risk_level,
            policies=decision.policies,
            explanation=decision.explanation,
            resource=resource,
            destination=destination,
            sensitivity=sensitivity,
            latency_ms=latency_ms,
        )

        if decision.decision == "BLOCK":
            event = self._persist_event(call, executed=False, side_effect=False, **common)
            self.db.commit()
            return GatewayResult(
                decision="BLOCK",
                event_id=event.id,
                policies=decision.policies,
                explanation=decision.explanation,
                risk_score=decision.risk_score,
                risk_level=decision.risk_level,
                executed=False,
                side_effect=False,
                latency_ms=latency_ms,
            )

        if decision.decision == "REQUIRE_APPROVAL":
            approval = self._create_approval(call, agent, decision, common)
            event = self._persist_event(
                call, executed=False, side_effect=False, approval_id=approval.id, **common
            )
            self.db.commit()
            return GatewayResult(
                decision="REQUIRE_APPROVAL",
                event_id=event.id,
                approval_id=approval.id,
                policies=decision.policies,
                explanation=decision.explanation,
                risk_score=decision.risk_score,
                risk_level=decision.risk_level,
                executed=False,
                side_effect=False,
                latency_ms=latency_ms,
            )

        # ALLOW -> signed ticket -> execution
        return self._execute_allowed(call, agent, common, decision, latency_ms)

    def _execute_allowed(
        self,
        call: ToolCall,
        agent: Agent,
        common: dict[str, Any],
        decision: Any,
        latency_ms: float,
    ) -> GatewayResult:
        ticket = issue_ticket(call.agent_id, call.session_id, call.tool, call.params)
        try:
            outcome = execute_tool(
                call.tool,
                call.params,
                agent_id=call.agent_id,
                session_id=call.session_id,
                ticket=ticket,
            )
            error = None
        except GatewayBypassError as exc:
            # Should be unreachable: the gateway issues the ticket itself.
            event = self._persist_event(
                call,
                executed=False,
                side_effect=False,
                policies=["P-FAIL-001"],
                explanation=f"Gateway bypass attempt blocked: {exc}",
                decision="BLOCK",
                risk_score=100.0,
                level="critical",
                resource=common.get("resource"),
                destination=common.get("destination"),
                sensitivity=common.get("sensitivity"),
                latency_ms=latency_ms,
            )
            self.db.commit()
            return GatewayResult(
                decision="BLOCK",
                event_id=event.id,
                policies=["P-FAIL-001"],
                explanation=f"Gateway bypass attempt blocked: {exc}",
                risk_score=100.0,
                risk_level="critical",
                executed=False,
                side_effect=False,
                latency_ms=latency_ms,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - tool-level failures are data
            outcome = {"tool": call.tool, "error": str(exc)}
            error = str(exc)

        event = self._persist_event(
            call,
            executed=error is None,
            side_effect=bool(outcome.get("side_effect", False)) if error is None else False,
            result=outcome,
            **{
                k: v
                for k, v in common.items()
                if k in {"decision", "risk_score", "level", "policies", "explanation",
                         "resource", "destination", "sensitivity", "latency_ms"}
            },
        )
        self.db.commit()
        return GatewayResult(
            decision="ALLOW",
            event_id=event.id,
            policies=decision.policies,
            explanation=decision.explanation,
            risk_score=decision.risk_score,
            risk_level=decision.risk_level,
            executed=error is None,
            side_effect=bool(outcome.get("side_effect", False)) if error is None else False,
            result=outcome if error is None else {"error": error},
            latency_ms=latency_ms,
            error=error,
        )

    # -- approvals ----------------------------------------------------------

    @staticmethod
    def fingerprint(
        agent_id: str, session_id: str, tool: str, params: dict[str, Any]
    ) -> str:
        canonical = json.dumps(params, sort_keys=True, default=str)
        payload = f"{agent_id}|{session_id}|{tool}|{canonical}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _create_approval(
        self, call: ToolCall, agent: Agent, decision: Any, common: dict[str, Any]
    ) -> Approval:
        settings = self.settings
        approval = Approval(
            id=f"apr-{uuid.uuid4().hex[:12]}",
            run_id=call.run_id,
            step_index=call.step_index,
            session_id=call.session_id,
            agent_id=call.agent_id,
            tool=call.tool,
            params_json=dumps(call.params),
            resource=common.get("resource"),
            destination=common.get("destination"),
            sensitivity=common.get("sensitivity"),
            risk_score=decision.risk_score,
            risk_level=decision.risk_level,
            explanation=decision.explanation,
            policy_ids=dumps(decision.policies),
            fingerprint=self.fingerprint(call.agent_id, call.session_id, call.tool, call.params),
            status="PENDING",
            expires_at=utcnow() + dt.timedelta(minutes=settings.approval_ttl_minutes),
        )
        self.db.add(approval)
        self.db.flush()
        return approval

    def decide_approval(
        self,
        approval_id: str,
        approve: bool,
        actor: str,
        fingerprint: str | None = None,
    ) -> GatewayResult:
        """Record a human decision on one pending approval.

        Approving triggers immediate revalidation of the exact action
        against the *current* policy and action history before execution.
        Approvals are single-use and bound to the original parameters.
        """
        approval = self.db.get(Approval, approval_id)
        if approval is None:
            raise ApprovalNotFound(f"unknown approval: {approval_id}")

        if approval.consumed or approval.status not in {"PENDING"}:
            raise ApprovalConflict(
                f"approval {approval_id} already resolved with status "
                f"{approval.status} (replay rejected)"
            )

        if fingerprint and fingerprint != approval.fingerprint:
            raise ApprovalTampered(
                "approval is bound to different action parameters; "
                "altered requests are rejected"
            )

        now = utcnow()
        if now > approval.expires_at:
            approval.status = "EXPIRED"
            approval.decided_at = now
            approval.decision = "expired"
            approval.decided_by = actor
            call = self._call_from_approval(approval)
            event = self._persist_event(
                call,
                decision="EXPIRED",
                risk_score=approval.risk_score,
                level=approval.risk_level,
                policies=json.loads(approval.policy_ids),
                explanation=(
                    "Approval expired before a human decision was recorded; "
                    "the action was not executed."
                ),
                executed=False,
                side_effect=False,
                resource=approval.resource,
                destination=approval.destination,
                sensitivity=approval.sensitivity or "internal",
                latency_ms=0.0,
                approval_id=approval.id,
            )
            approval.execution_event_id = event.id
            self._sync_step(approval, status="expired", event_id=event.id)
            self._maybe_finish_run(approval.run_id)
            self.db.commit()
            raise ApprovalExpiredError(
                f"approval {approval_id} expired at {approval.expires_at.isoformat()}"
            )

        call = self._call_from_approval(approval)

        if not approve:
            approval.status = "REJECTED"
            approval.decision = "rejected"
            approval.decided_at = now
            approval.decided_by = actor
            explanation = (
                f"Human reviewer '{actor}' rejected the pending action; the "
                "protected tool was never invoked."
            )
            event = self._persist_event(
                call,
                decision="REJECTED",
                risk_score=approval.risk_score,
                level=approval.risk_level,
                policies=json.loads(approval.policy_ids),
                explanation=explanation,
                executed=False,
                side_effect=False,
                resource=approval.resource,
                destination=approval.destination,
                sensitivity=approval.sensitivity or "internal",
                latency_ms=0.0,
                approval_id=approval.id,
            )
            approval.execution_event_id = event.id
            approval.outcome = explanation
            self._sync_step(approval, status="rejected", event_id=event.id)
            self._maybe_finish_run(approval.run_id)
            self.db.commit()
            return GatewayResult(
                decision="REJECTED",
                event_id=event.id,
                approval_id=approval.id,
                policies=json.loads(approval.policy_ids),
                explanation=explanation,
                risk_score=approval.risk_score,
                risk_level=approval.risk_level,
                executed=False,
                side_effect=False,
            )

        # ---- APPROVE: consume first (single-use), then revalidate, then run.
        approval.consumed = True
        approval.decision = "approved"
        approval.decided_at = now
        approval.decided_by = actor
        self.db.flush()

        agent = self._agent(approval.agent_id)
        ctx = self.build_context(agent, call, approval_context=True)

        started = time.perf_counter()
        decision = self.engine.evaluate(ctx)
        latency_ms = (time.perf_counter() - started) * 1000.0

        if decision.decision == "BLOCK":
            approval.status = "FAILED"
            explanation = (
                "Revalidation failed: current policy denies this action "
                f"({decision.explanation})"
            )
            event = self._persist_event(
                call,
                decision="BLOCK",
                risk_score=decision.risk_score,
                level=decision.risk_level,
                policies=decision.policies,
                explanation=explanation,
                executed=False,
                side_effect=False,
                resource=approval.resource,
                destination=approval.destination,
                sensitivity=approval.sensitivity or "internal",
                latency_ms=latency_ms,
                approval_id=approval.id,
            )
            approval.execution_event_id = event.id
            approval.outcome = explanation
            self._sync_step(approval, status="blocked", event_id=event.id)
            self._maybe_finish_run(approval.run_id)
            self.db.commit()
            return GatewayResult(
                decision="BLOCK",
                event_id=event.id,
                approval_id=approval.id,
                policies=decision.policies,
                explanation=explanation,
                risk_score=decision.risk_score,
                risk_level=decision.risk_level,
                executed=False,
                side_effect=False,
                latency_ms=latency_ms,
            )

        ticket = issue_ticket(approval.agent_id, approval.session_id, approval.tool, call.params)
        try:
            outcome = execute_tool(
                approval.tool,
                call.params,
                agent_id=approval.agent_id,
                session_id=approval.session_id,
                ticket=ticket,
            )
            error = None
        except Exception as exc:  # noqa: BLE001
            outcome = {"error": str(exc)}
            error = str(exc)

        approval.status = "APPROVED" if error is None else "EXECUTION_FAILED"
        explanation = (
            f"Approved by '{actor}'; authorization revalidated immediately "
            f"before execution ({decision.decision} on recheck). "
            + (outcome.get("summary", "") if error is None else f"Error: {error}")
        )
        event = self._persist_event(
            call,
            decision="APPROVED",
            risk_score=decision.risk_score,
            level=decision.risk_level,
            policies=decision.policies,
            explanation=explanation,
            executed=error is None,
            side_effect=bool(outcome.get("side_effect", False)) if error is None else False,
            resource=approval.resource,
            destination=approval.destination,
            sensitivity=approval.sensitivity or "internal",
            latency_ms=latency_ms,
            approval_id=approval.id,
            result=outcome,
        )
        approval.execution_event_id = event.id
        approval.outcome = explanation
        self._sync_step(approval, status="executed" if error is None else "failed",
                        event_id=event.id)
        self._maybe_finish_run(approval.run_id)
        self.db.commit()
        return GatewayResult(
            decision="APPROVED",
            event_id=event.id,
            approval_id=approval.id,
            policies=decision.policies,
            explanation=explanation,
            risk_score=decision.risk_score,
            risk_level=decision.risk_level,
            executed=error is None,
            side_effect=bool(outcome.get("side_effect", False)) if error is None else False,
            result=outcome,
            latency_ms=latency_ms,
            error=error,
        )

    # -- run/step bookkeeping ---------------------------------------------

    def _call_from_approval(self, approval: Approval) -> ToolCall:
        return ToolCall(
            agent_id=approval.agent_id,
            session_id=approval.session_id,
            tool=approval.tool,
            params=json.loads(approval.params_json),
            run_id=approval.run_id,
            step_index=approval.step_index,
            resource=approval.resource,
            destination=approval.destination,
            sensitivity=approval.sensitivity,
        )

    def _sync_step(
        self, approval: Approval, *, status: str, event_id: int | None
    ) -> None:
        if not approval.run_id or approval.step_index is None:
            return
        step = self.db.scalar(
            select(ScenarioStep).where(
                ScenarioStep.run_id == approval.run_id,
                ScenarioStep.step_index == approval.step_index,
            )
        )
        if step is None:
            return
        step.status = status
        step.event_id = event_id
        step.decision = (
            "APPROVED" if status == "executed" else status.upper()
        )
        step.executed = status == "executed"

    def _maybe_finish_run(self, run_id: str | None) -> None:
        if not run_id:
            return
        run = self.db.get(ScenarioRun, run_id)
        if run is None or run.status != "awaiting_approval":
            return
        steps = list(run.steps)
        if any(s.status in {"pending", "pending_approval"} for s in steps):
            return
        run.status = "completed"
        run.finished_at = utcnow()
        executed = sum(1 for s in steps if s.executed)
        blocked = sum(1 for s in steps if s.status in {"blocked"})
        run.executed_count = executed
        run.blocked_count = blocked
        run.summary = _run_summary(run, steps)


def _run_summary(run: ScenarioRun, steps: list[ScenarioStep]) -> str:
    executed = [s for s in steps if s.executed]
    blocked = [s for s in steps if s.status == "blocked"]
    rejected = [s for s in steps if s.status == "rejected"]
    parts = [f"{len(steps)} step(s) evaluated."]
    if executed:
        parts.append(f"{len(executed)} executed: " + ", ".join(s.label for s in executed) + ".")
    if blocked:
        parts.append(
            "Blocked before execution: " + ", ".join(s.label for s in blocked) + "."
        )
    if rejected:
        parts.append("Rejected by human: " + ", ".join(s.label for s in rejected) + ".")
    return " ".join(parts)
