"""Security-engine tests: authorization, cumulative exposure, enforcement."""

from __future__ import annotations

import pytest

import app.policy as policy
from app.gateway import Gateway, ToolCall
from app.models import Agent, Event
from app.tools import (
    GatewayBypassError,
    OPERATIONAL_RECORD,
    OUTBOUND_LOG,
    WRITE_LOG,
    execute_tool,
    issue_ticket,
)
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Legitimate execution
# ---------------------------------------------------------------------------


def test_legitimate_workflow_allowed_and_audited(client, db):
    res = client.post("/api/scenarios/scenario_a/run")
    assert res.status_code == 201
    data = res.json()

    assert data["status"] == "completed"
    assert data["blocked_count"] == 0
    assert all(s["decision"] == "ALLOW" for s in data["steps"])
    assert all(s["executed"] for s in data["steps"])
    # The authorized internal save really happened (simulated side effect).
    assert any(w["destination"] == "internal://team-reports" for w in WRITE_LOG)

    events = db.scalars(select(Event).where(Event.run_id == data["id"])).all()
    assert len(events) == 3
    assert all(e.executed for e in events)
    assert all(e.explanation for e in events)
    assert all(e.risk_score >= 0 for e in events)


# ---------------------------------------------------------------------------
# Unauthorized operations
# ---------------------------------------------------------------------------


def test_unauthorized_tool_grant_blocked(db):
    gateway = Gateway(db)
    result = gateway.act(
        ToolCall(
            agent_id="report-agent",
            session_id="sess-unauth",
            tool="read_customer_records",
            params={"record_ids": ["cust-001"]},
        )
    )
    assert result.decision == "BLOCK"
    assert result.policies == ["P-TOOL-001"]
    assert result.executed is False


def test_resource_clearance_enforced(db):
    # Agent has the tool grant but not the clearance for restricted data.
    db.add(
        Agent(
            id="low-clearance",
            name="Low Clearance Agent",
            role="intern",
            clearance="internal",
            granted_tools='["read_customer_records"]',
            description="",
        )
    )
    db.commit()

    gateway = Gateway(db)
    result = gateway.act(
        ToolCall(
            agent_id="low-clearance",
            session_id="sess-clearance",
            tool="read_customer_records",
            params={"record_ids": ["cust-001"]},
        )
    )
    assert result.decision == "BLOCK"
    assert result.policies == ["P-RES-001"]
    assert result.executed is False


def test_fail_closed_on_policy_error(db, monkeypatch):
    def exploding_rule(ctx):  # noqa: ANN001
        raise RuntimeError("policy store unavailable")

    monkeypatch.setattr(policy, "DENY_RULES", [exploding_rule])

    gateway = Gateway(db)
    result = gateway.act(
        ToolCall(
            agent_id="report-agent",
            session_id="sess-fail",
            tool="read_document",
            params={"path": "kb/onboarding-guide.md"},
        )
    )
    assert result.decision == "BLOCK"
    assert result.policies == ["P-FAIL-001"]
    assert "Fail-closed" in result.explanation
    assert result.executed is False


# ---------------------------------------------------------------------------
# Cumulative multi-step data exposure
# ---------------------------------------------------------------------------


def test_cumulative_sequence_blocks_transfer(client, db):
    res = client.post("/api/scenarios/scenario_b/run")
    assert res.status_code == 201
    data = res.json()

    steps = data["steps"]
    assert len(steps) == 4
    # First three steps are individually permitted...
    assert [s["decision"] for s in steps[:3]] == ["ALLOW", "ALLOW", "ALLOW"]
    # ...the final transfer of the derived summary is not.
    assert steps[3]["decision"] == "BLOCK"
    assert "P-CUM-001" in steps[3]["policies"]
    assert steps[3]["executed"] is False
    assert data["blocked_count"] == 1

    # Attempt tracked separately from side effects: nothing left the gateway.
    assert OUTBOUND_LOG == []
    transfer_event = db.get(Event, steps[3]["event_id"])
    assert transfer_event.executed is False
    assert transfer_event.side_effect is False
    assert transfer_event.decision == "BLOCK"


def test_incident_created_with_evidence(client, db):
    data = client.post("/api/scenarios/scenario_b/run").json()
    assert data["incident_id"]

    res = client.get(f"/api/incidents/{data['incident_id']}")
    assert res.status_code == 200
    payload = res.json()

    incident = payload["incident"]
    assert incident["blocked_tool"] == "transfer_external"
    assert incident["trigger_policy"] == "P-CUM-001"
    assert incident["protected_tool_executed"] is False

    timeline = payload["timeline"]
    assert [t["tool"] for t in timeline] == [
        "read_customer_records",
        "aggregate_customer_data",
        "create_summary",
        "transfer_external",
    ]
    assert timeline[-1]["decision"] == "BLOCK"
    assert timeline[-1]["executed"] is False
    assert "did not execute" in payload["attack_explanation"]


def test_risk_escalates_across_session(db):
    gateway = Gateway(db)
    first = gateway.act(
        ToolCall(
            agent_id="support-agent",
            session_id="sess-escalate",
            tool="read_customer_records",
            params={"record_ids": ["cust-001"]},
        )
    )
    second = gateway.act(
        ToolCall(
            agent_id="support-agent",
            session_id="sess-escalate",
            tool="create_summary",
            params={"title": "s", "includes": ["email"], "contains_pii": True},
        )
    )
    assert first.decision == "ALLOW"
    assert second.decision == "ALLOW"
    assert second.risk_score > first.risk_score


# ---------------------------------------------------------------------------
# Gateway bypass protection
# ---------------------------------------------------------------------------


def test_direct_tool_invocation_is_rejected():
    params = {"record_ids": ["cust-001"]}
    with pytest.raises(GatewayBypassError):
        execute_tool(
            "read_customer_records",
            params,
            agent_id="attacker",
            session_id="sess-x",
            ticket="",
        )


def test_forged_ticket_rejected():
    params = {"record_ids": ["cust-001"]}
    with pytest.raises(GatewayBypassError):
        execute_tool(
            "read_customer_records",
            params,
            agent_id="attacker",
            session_id="sess-x",
            ticket="deadbeef." + "0" * 64,
        )


def test_ticket_is_parameter_bound(db):
    params = {"record_ids": ["cust-001"]}
    ticket = issue_ticket("support-agent", "sess-t", "read_customer_records", params)
    # Ticket valid for exact params...
    execute_tool(
        "read_customer_records",
        params,
        agent_id="support-agent",
        session_id="sess-t",
        ticket=ticket,
    )
    # ...but rejected for altered parameters or a different session.
    with pytest.raises(GatewayBypassError):
        execute_tool(
            "read_customer_records",
            {"record_ids": ["cust-001", "cust-002"]},
            agent_id="support-agent",
            session_id="sess-t",
            ticket=ticket,
        )
    with pytest.raises(GatewayBypassError):
        execute_tool(
            "read_customer_records",
            params,
            agent_id="support-agent",
            session_id="sess-other",
            ticket=ticket,
        )


def test_no_raw_execution_endpoint(client):
    """An agent cannot bypass the gateway through the public API."""
    res = client.post(
        "/api/tools/execute",
        json={"tool": "modify_operational_record", "params": {"record_id": "ops-4711", "changes": {"max_retries": 99}}},
    )
    assert res.status_code == 404
    assert OPERATIONAL_RECORD["version"] == 1


# ---------------------------------------------------------------------------
# Audit persistence
# ---------------------------------------------------------------------------


def test_audit_events_persisted_with_decisions(client, db):
    client.post("/api/scenarios/scenario_a/run")
    client.post("/api/scenarios/scenario_b/run")

    rows = db.scalars(select(Event).order_by(Event.id)).all()
    assert len(rows) >= 7
    decisions = {r.decision for r in rows}
    assert decisions == {"ALLOW", "BLOCK"}
    for row in rows:
        assert row.explanation
        assert row.ts is not None
        assert row.session_id

    # Read back through the API (pagination + filters).
    res = client.get("/api/events", params={"limit": 5, "decision": "BLOCK"})
    payload = res.json()
    assert payload["total"] >= 1
    assert len(payload["items"]) <= 5
    assert all(i["decision"] == "BLOCK" for i in payload["items"])
