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


# ---------------------------------------------------------------------------
# CORS regression tests (browser cross-origin policy — NOT authentication)
# ---------------------------------------------------------------------------

APPROVED_ORIGINS = [
    "http://127.0.0.1:3010",
    "http://localhost:3010",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]


def test_cors_grants_approved_origins_on_simple_get(client):
    for origin in APPROVED_ORIGINS:
        res = client.get("/api/metrics", headers={"Origin": origin})
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == origin
        # Credentials are intentionally disabled: never pair grants with cookies.
        assert res.headers.get("access-control-allow-credentials") is None


def test_cors_preflight_allows_frontend_method_and_headers(client):
    res = client.options(
        "/api/evaluation/run",
        headers={
            "Origin": "http://127.0.0.1:3010",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:3010"
    methods = res.headers.get("access-control-allow-methods", "")
    assert "GET" in methods and "POST" in methods and "*" not in methods
    headers = res.headers.get("access-control-allow-headers", "")
    assert "Content-Type" in headers
    assert res.headers.get("access-control-allow-credentials") is None


def test_cors_unapproved_origin_gets_no_grant(client):
    origin = "https://untrusted.example"

    # Simple request: the server still answers (CORS is enforced by browsers,
    # it is not server-side authentication), but NO CORS grant is returned,
    # so a browser on that origin could not read the response.
    res = client.get("/api/metrics", headers={"Origin": origin})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") is None

    # Preflight for the mutating approval endpoint is not granted either.
    pre = client.options(
        "/api/approvals/apr-test/decision",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert pre.headers.get("access-control-allow-origin") is None


def test_cors_configuration_has_no_wildcard():
    from app.main import ALLOWED_ORIGINS, app
    from fastapi.middleware.cors import CORSMiddleware

    assert "*" not in ALLOWED_ORIGINS
    assert all(o.startswith("http://") for o in ALLOWED_ORIGINS)

    cors_middleware = [
        m for m in app.user_middleware if m.cls is CORSMiddleware
    ]
    assert cors_middleware, "CORS middleware must be installed"
    kwargs = cors_middleware[0].kwargs
    assert kwargs["allow_credentials"] is False
    assert "*" not in kwargs["allow_methods"]


def test_api_still_works_without_origin_header(client):
    """CORS changes must not affect non-browser clients."""
    res = client.get("/api/metrics")
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") is None
    assert res.json()["actions_evaluated"] == 0


# ---------------------------------------------------------------------------
# Benchmark accounting (denominators, failures, completeness)
# ---------------------------------------------------------------------------


def test_benchmark_case_list_is_complete_and_unique():
    from collections import Counter

    names = [c.name for c in CASES]
    assert len(names) == len(set(names)), "duplicate benchmark case names"
    # Pinned so an accidental case removal fails loudly and docs stay honest.
    assert len(CASES) == 17
    kinds = Counter(c.kind for c in CASES)
    assert set(kinds) <= {"attack", "benign", "approval", "invalid"}
    assert kinds["attack"] == 5 and kinds["benign"] == 4


def test_benchmark_executes_every_defined_case_once(client):
    res = client.post("/api/evaluation/run")
    assert res.status_code == 200
    body = res.json()

    # Runner must neither skip nor duplicate: rows == cases == executed.
    assert body["total_cases"] == len(CASES) == 17
    assert len(body["rows"]) == len(CASES)
    row_names = [r["case"] for r in body["rows"]]
    assert len(row_names) == len(set(row_names))
    assert set(row_names) == {c.name for c in CASES}
    # passed_cases counts only actual==expected; failures are listed explicitly.
    assert body["passed_cases"] + len(body["failed_cases"]) == body["total_cases"]
    assert body["failed_cases"] == [
        r["case"] for r in body["rows"] if not r["passed"]
    ]
    assert sum(body["by_kind"].values()) == body["total_cases"]


def test_benchmark_rerun_replaces_previous_suite(client):
    first = client.post("/api/evaluation/run").json()
    second = client.post("/api/evaluation/run").json()
    assert first["suite"] != second["suite"]
    # No accumulation across runs.
    assert second["total_cases"] == first["total_cases"] == 17


def test_benchmark_accounting_denominators_and_separate_rates(db):
    """Rates use per-kind denominators; detection != prevention != passing."""
    from app.benchmark import compute_benchmark_metrics
    from app.models import TestResult

    def row(**kw):
        base = dict(
            suite="benchmark:acct",
            latency_ms=1.0,
            e2e_ms=2.0,
            detail="",
            detected=None,
            prevented=None,
            false_positive=None,
        )
        base.update(kw)
        return TestResult(**base)

    db.add_all(
        [
            # Attack: blocked AND no side effect -> detected + prevented.
            row(case="a1", kind="attack", expected="BLOCK", actual="BLOCK",
                passed=True, detected=True, prevented=True),
            # Attack: missed entirely -> not detected, not prevented, FAILED.
            row(case="a2", kind="attack", expected="BLOCK", actual="ALLOW",
                passed=False, detected=False, prevented=False),
            # Attack: label said BLOCK but a side effect still happened ->
            # detected but NOT prevented (the two rates must not be conflated),
            # yet "passed" because actual == expected.
            row(case="a3", kind="attack", expected="BLOCK", actual="BLOCK",
                passed=True, detected=True, prevented=False),
            # Benign: blocked -> false positive, FAILED.
            row(case="b1", kind="benign", expected="ALLOW", actual="BLOCK",
                passed=False, false_positive=True),
            row(case="b2", kind="benign", expected="ALLOW", actual="ALLOW",
                passed=True, false_positive=False),
            row(case="c1", kind="approval", expected="PENDING_NO_EXECUTION",
                actual="PENDING_NO_EXECUTION", passed=True),
            # Crashing case: ERROR must never count as a pass.
            row(case="e1", kind="invalid", expected="SAFE_NO_SIDE_EFFECT",
                actual="ERROR", passed=False),
        ]
    )
    db.commit()

    m = compute_benchmark_metrics(db)
    assert m["total_cases"] == 7
    assert m["passed_cases"] == 4
    assert m["failed_cases"] == ["a2", "b1", "e1"]
    assert m["attacks"] == 3 and m["benign"] == 2
    # Denominators are per kind, not total cases.
    assert m["detection_rate"] == 0.6667   # 2/3 attacks detected
    assert m["prevention_rate"] == 0.3333  # 1/3 attacks with no side effect
    assert m["false_positive_rate"] == 0.5  # 1/2 benign blocked
    assert sum(m["by_kind"].values()) == m["total_cases"]


def test_benchmark_docs_match_actual_case_count():
    """README / IMPLEMENTATION_REPORT / DEMO_SCRIPT must describe the
    *current* benchmark, not a historical one (EVALUATION.md keeps its
    clearly-labelled history and is therefore excluded)."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    for doc in ("README.md", "IMPLEMENTATION_REPORT.md", "DEMO_SCRIPT.md"):
        text = (root / doc).read_text(encoding="utf-8")
        assert "9 cases" not in text, f"{doc} still claims a 9-case benchmark"
        assert "9/9" not in text, f"{doc} still claims 9/9 results"
        assert "9 recorded cases" not in text, f"{doc} still claims 9 recorded cases"
        # Stale pre-hardening test counts must not survive either.
        assert "30 passed" not in text, f"{doc} still claims the old 30-test result"
        assert "37 tests" not in text, f"{doc} still claims the intermediate 37-test count"
        assert "(17 cases" in text or "17 recorded cases" in text or "17 cases)" in text, (
            f"{doc} does not state the current 17-case benchmark"
        )
