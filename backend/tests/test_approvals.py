"""Human-approval tests: pause, decision, replay, expiry, tampering, revalidation."""

from __future__ import annotations

import datetime as dt

from app.models import Approval, Event, utcnow
from app.tools import OPERATIONAL_RECORD
from sqlalchemy import select


def _start_scenario_c(client) -> dict:
    res = client.post("/api/scenarios/scenario_c/run")
    assert res.status_code == 201
    return res.json()


def _pending_approval(client, run: dict) -> dict:
    res = client.get("/api/approvals", params={"status": "PENDING"})
    items = res.json()["items"]
    assert items, "expected a pending approval"
    return next(a for a in items if a["run_id"] == run["id"])


def test_approval_required_before_protected_modification(client):
    run = _start_scenario_c(client)

    assert run["status"] == "awaiting_approval"
    assert run["steps"][0]["executed"] is True  # proposal has no side effect
    assert run["steps"][1]["decision"] == "REQUIRE_APPROVAL"
    assert run["steps"][1]["executed"] is False
    # Nothing protected changed before a human decision.
    assert OPERATIONAL_RECORD["version"] == 1
    assert OPERATIONAL_RECORD["rate_limit_rps"] == 100

    approval = _pending_approval(client, run)
    assert approval["tool"] == "modify_operational_record"
    assert approval["params"]["changes"] == {"rate_limit_rps": 500, "max_retries": 5}
    assert approval["fingerprint"]


def test_approval_revalidation_and_execution(client):
    run = _start_scenario_c(client)
    approval = _pending_approval(client, run)

    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={
            "decision": "approve",
            "actor": "reviewer-1",
            "fingerprint": approval["fingerprint"],
        },
    )
    assert res.status_code == 200
    payload = res.json()

    assert payload["result"]["decision"] == "APPROVED"
    assert payload["result"]["executed"] is True
    assert payload["approval"]["status"] == "APPROVED"
    assert payload["approval"]["consumed"] is True
    assert "revalidated" in payload["result"]["explanation"].lower()

    # Protected side effect only now.
    assert OPERATIONAL_RECORD["version"] == 2
    assert OPERATIONAL_RECORD["rate_limit_rps"] == 500

    run_res = client.get(f"/api/scenarios/{run['id']}").json()
    assert run_res["status"] == "completed"
    assert run_res["steps"][1]["executed"] is True

    approved_events = [
        e for e in run_res["events"] if e["decision"] == "APPROVED"
    ]
    assert len(approved_events) == 1
    assert approved_events[0]["executed"] is True


def test_approval_rejection_blocks_execution(client):
    run = _start_scenario_c(client)
    approval = _pending_approval(client, run)

    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "reject", "actor": "reviewer-2"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["result"]["decision"] == "REJECTED"
    assert payload["approval"]["status"] == "REJECTED"

    assert OPERATIONAL_RECORD["version"] == 1  # never modified

    run_res = client.get(f"/api/scenarios/{run['id']}").json()
    assert run_res["status"] == "completed"
    assert run_res["steps"][1]["executed"] is False
    assert run_res["steps"][1]["status"] == "rejected"


def test_approval_replay_rejected(client):
    run = _start_scenario_c(client)
    approval = _pending_approval(client, run)

    first = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve", "actor": "reviewer-1"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve", "actor": "attacker"},
    )
    assert second.status_code == 409
    assert second.json()["error"] == "approval_conflict"
    # Replay executed nothing extra.
    assert OPERATIONAL_RECORD["version"] == 2


def test_altered_parameters_rejected(client):
    run = _start_scenario_c(client)
    approval = _pending_approval(client, run)

    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={
            "decision": "approve",
            "actor": "reviewer-1",
            "fingerprint": "0" * 64,  # fingerprint of a different action
        },
    )
    assert res.status_code == 409
    assert res.json()["error"] == "approval_params_mismatch"
    assert OPERATIONAL_RECORD["version"] == 1

    # Still pending and usable with the correct fingerprint.
    check = client.get("/api/approvals", params={"status": "PENDING"}).json()
    assert any(a["id"] == approval["id"] for a in check["items"])


def test_expired_approval_not_executable(client, db):
    run = _start_scenario_c(client)
    approval = _pending_approval(client, run)

    row = db.get(Approval, approval["id"])
    row.expires_at = utcnow() - dt.timedelta(minutes=1)
    db.commit()

    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve", "actor": "reviewer-1"},
    )
    assert res.status_code == 409
    assert res.json()["error"] == "approval_expired"
    assert OPERATIONAL_RECORD["version"] == 1

    db.expire_all()
    row = db.get(Approval, approval["id"])
    assert row.status == "EXPIRED"
    assert row.consumed is False

    events = db.scalars(
        select(Event).where(Event.approval_id == approval["id"])
    ).all()
    assert any(e.decision == "EXPIRED" and not e.executed for e in events)


def test_revalidation_revokes_before_execution(client, db):
    """If privileges change between request and approval, nothing runs."""
    run = _start_scenario_c(client)
    approval = _pending_approval(client, run)

    # Revoke the protected tool from the agent after the request.
    from app.models import Agent
    import json

    agent = db.get(Agent, "ops-agent")
    granted = json.loads(agent.granted_tools)
    granted.remove("modify_operational_record")
    agent.granted_tools = json.dumps(granted)
    db.commit()

    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve", "actor": "reviewer-1"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["result"]["decision"] == "BLOCK"
    assert payload["approval"]["status"] == "FAILED"
    assert payload["result"]["executed"] is False
    assert OPERATIONAL_RECORD["version"] == 1  # protected write never happened


def test_unknown_approval_returns_404(client):
    res = client.post(
        "/api/approvals/apr-does-not-exist/decision",
        json={"decision": "approve", "actor": "x"},
    )
    assert res.status_code == 404
    assert res.json()["error"] == "approval_not_found"
