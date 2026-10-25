"""API contract, metrics and evaluation-benchmark tests."""

from __future__ import annotations

from app.benchmark import CASES


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["fail_closed"] is True
    assert body["policies_loaded"] >= 8


def test_agents_endpoint(client):
    res = client.get("/api/agents")
    assert res.status_code == 200
    body = res.json()
    ids = {a["id"] for a in body["items"]}
    assert {"report-agent", "support-agent", "ops-agent"} <= ids
    for agent in body["items"]:
        assert isinstance(agent["granted_tools"], list)
        assert agent["clearance"] in {"public", "internal", "confidential", "restricted"}


def test_policies_endpoint(client):
    res = client.get("/api/policies")
    assert res.status_code == 200
    body = res.json()
    ids = {p["id"] for p in body["items"]}
    assert {"P-TOOL-001", "P-RES-001", "P-CUM-001", "P-FAIL-001"} <= ids
    assert body["fail_closed"] is True
    assert body["thresholds"]["block_threshold"] == 80


def test_events_pagination_and_filters(client):
    client.post("/api/scenarios/scenario_a/run")
    client.post("/api/scenarios/scenario_b/run")

    page1 = client.get("/api/events", params={"limit": 3, "offset": 0}).json()
    page2 = client.get("/api/events", params={"limit": 3, "offset": 3}).json()
    assert page1["total"] == page2["total"] == 7
    assert {e["id"] for e in page1["items"]}.isdisjoint({e["id"] for e in page2["items"]})

    filtered = client.get(
        "/api/events", params={"scenario": "scenario_b", "decision": "BLOCK"}
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["tool"] == "transfer_external"

    # Invalid pagination -> validation error
    bad = client.get("/api/events", params={"limit": 0})
    assert bad.status_code == 422


def test_metrics_only_from_real_data(client):
    # Fresh database: no fabricated numbers.
    empty = client.get("/api/metrics").json()
    assert empty["actions_evaluated"] == 0
    assert empty["evaluation"]["available"] is False
    assert empty["evaluation"]["detection_rate"] is None

    client.post("/api/scenarios/scenario_a/run")
    client.post("/api/scenarios/scenario_b/run")
    client.post("/api/scenarios/scenario_c/run")

    metrics = client.get("/api/metrics").json()
    assert metrics["actions_evaluated"] == 3 + 4 + 2
    assert metrics["allowed"] == 3 + 3 + 1
    assert metrics["blocked"] == 1
    assert metrics["approval_required"] == 1
    assert metrics["prevented_side_effects"] == 1
    assert metrics["pending_approvals"] == 1
    assert metrics["open_incidents"] == 1
    assert metrics["side_effects_realized"] == 1  # only A's authorized save
    assert metrics["avg_decision_latency_ms"] >= 0
    assert metrics["by_scenario"]["scenario_b"]["BLOCK"] == 1


def test_evaluation_benchmark_computed_metrics(client):
    res = client.post("/api/evaluation/run")
    assert res.status_code == 200
    body = res.json()

    assert body["available"] is True
    assert body["total_cases"] == len(CASES)
    assert body["passed_cases"] == len(CASES)
    assert body["detection_rate"] == 1.0
    assert body["false_positive_rate"] == 0.0
    assert body["prevention_rate"] == 1.0
    assert body["decision_latency_avg_ms"] is not None
    assert len(body["rows"]) == len(CASES)

    metrics = client.get("/api/metrics").json()
    assert metrics["evaluation"]["available"] is True
    assert metrics["evaluation"]["detection_rate"] == 1.0
    assert metrics["evaluation"]["suite"] == body["suite"]

    # Results are persisted (recomputed from stored rows on next call).
    again = client.post("/api/evaluation/run")
    assert again.json()["total_cases"] == len(CASES)


def test_unknown_resources_return_404(client):
    assert client.get("/api/scenarios/run-nope").status_code == 404
    assert client.get("/api/incidents/inc-nope").status_code == 404
    assert (
        client.post("/api/scenarios/scenario_z/run").status_code == 404
    )


def test_invalid_approval_payload_returns_422(client):
    client.post("/api/scenarios/scenario_c/run")
    approval = client.get("/api/approvals", params={"status": "PENDING"}).json()[
        "items"
    ][0]
    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "maybe", "actor": "x"},
    )
    assert res.status_code == 422


def test_scenario_detail_contains_persisted_events(client):
    run = client.post("/api/scenarios/scenario_b/run").json()
    detail = client.get(f"/api/scenarios/{run['id']}").json()
    assert len(detail["events"]) == 4
    assert detail["incident"]["blocked_tool"] == "transfer_external"
    assert detail["summary"]


def test_scenario_reruns_are_reliable(client):
    first = client.post("/api/scenarios/scenario_b/run").json()
    second = client.post("/api/scenarios/scenario_b/run").json()
    assert first["id"] != second["id"]
    assert first["blocked_count"] == second["blocked_count"] == 1
    assert all(
        s1["decision"] == s2["decision"]
        for s1, s2 in zip(first["steps"], second["steps"])
    )
    incidents = client.get("/api/incidents").json()
    assert incidents["total"] == 2


# ---------------------------------------------------------------------------
# Deployment safety
# ---------------------------------------------------------------------------


def test_cors_rejects_unknown_origins(client):
    """Only the dashboard origins are allowed; '*' is not echoed back."""
    res = client.options(
        "/api/metrics",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code in {200, 400, 403}  # preflight handled
    assert res.headers.get("access-control-allow-origin") is None

    ok = client.options(
        "/api/metrics",
        headers={
            "Origin": "http://127.0.0.1:3010",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:3010"


def test_unhandled_errors_return_generic_500(clean_state):
    """Unexpected exceptions never leak a stack trace to the client."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail 12345")

    with TestClient(app, raise_server_exceptions=False) as client:
        with patch("app.main.run_benchmark", boom):
            res = client.post("/api/evaluation/run")

    assert res.status_code == 500
    body = res.json()
    assert body["error"] == "internal_error"
    assert "secret internal detail" not in res.text
    assert "Traceback" not in res.text


def test_whitespace_actor_rejected(client):
    client.post("/api/scenarios/scenario_c/run")
    approval = client.get("/api/approvals", params={"status": "PENDING"}).json()[
        "items"
    ][0]
    res = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve", "actor": "   "},
    )
    assert res.status_code == 422
