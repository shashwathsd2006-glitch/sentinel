#!/usr/bin/env python
"""SENTINEL-X demo driver — exercises the live API end to end.

Usage (backend must already be running):

    .venv/Scripts/python scripts/demo.py [http://127.0.0.1:8010]

Everything printed below comes from real API responses.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"


def call(path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode())


def heading(text: str) -> None:
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


def main() -> None:
    heading("0. HEALTH")
    health = call("/health")
    print(json.dumps(health, indent=2))

    heading("SCENARIO A — legitimate workflow (expect: all ALLOW)")
    run_a = call("/api/scenarios/scenario_a/run", "POST")
    for step in run_a["steps"]:
        print(
            f"  {step['step_index'] + 1}. {step['tool']:<24} "
            f"{step['decision']:<18} executed={step['executed']} "
            f"risk={step['risk_score']}"
        )
        print(f"     {step['explanation']}")
    print(f"  run status: {run_a['status']} | {run_a['summary']}")

    heading("SCENARIO B — cumulative data exposure (expect: BLOCK pre-execution)")
    run_b = call("/api/scenarios/scenario_b/run", "POST")
    for step in run_b["steps"]:
        print(
            f"  {step['step_index'] + 1}. {step['tool']:<24} "
            f"{step['decision']:<18} executed={step['executed']} "
            f"risk={step['risk_score']}"
        )
        print(f"     {step['explanation']}")
        if step["policies"]:
            print(f"     policies: {', '.join(step['policies'])}")

    incident = call(f"/api/incidents/{run_b['incident_id']}")
    print("\n  INCIDENT EVIDENCE")
    print(f"    title          : {incident['incident']['title']}")
    print(f"    trigger policy : {incident['incident']['trigger_policy']}")
    print(f"    blocked tool   : {incident['incident']['blocked_tool']}")
    print(
        "    tool executed  : "
        f"{incident['incident']['protected_tool_executed']} "
        "(False = no side effect)"
    )
    for item in incident["timeline"]:
        print(
            f"    timeline #{item['index']}: {item['tool']:<24} "
            f"{item['decision']:<10} executed={item['executed']}"
        )

    heading("SCENARIO C — human approval (expect: pause -> approve -> execute)")
    run_c = call("/api/scenarios/scenario_c/run", "POST")
    for step in run_c["steps"]:
        print(
            f"  {step['step_index'] + 1}. {step['tool']:<28} "
            f"{step['decision']:<18} executed={step['executed']}"
        )
    print(f"  run status: {run_c['status']}")

    pending = call("/api/approvals?status=PENDING")["items"]
    approval = next(a for a in pending if a["run_id"] == run_c["id"])
    print(f"  pending approval: {approval['id']}")
    print(f"    operation : {approval['tool']} -> {json.dumps(approval['params'])}")
    print(f"    risk      : {approval['risk_score']} ({approval['risk_level']})")
    print(f"    reason    : {approval['explanation']}")

    decision = call(
        f"/api/approvals/{approval['id']}/decision",
        "POST",
        {
            "decision": "approve",
            "actor": "demo-reviewer",
            "fingerprint": approval["fingerprint"],
        },
    )
    print(f"  decision result: {decision['result']['decision']}")
    print(f"    executed     : {decision['result']['executed']}")
    print(f"    explanation  : {decision['result']['explanation']}")

    replay = None
    try:
        replay = call(
            f"/api/approvals/{approval['id']}/decision",
            "POST",
            {"decision": "approve", "actor": "attacker"},
        )
    except urllib.error.HTTPError as err:
        replay = {"http_status": err.code, "body": err.read().decode()[:200]}
    print(f"  replay attempt : {replay}")

    heading("METRICS (computed from persisted records)")
    metrics = call("/api/metrics")
    for key in (
        "actions_evaluated",
        "allowed",
        "blocked",
        "approval_required",
        "approved_executed",
        "rejected",
        "prevented_side_effects",
        "side_effects_realized",
        "pending_approvals",
        "open_incidents",
        "avg_decision_latency_ms",
    ):
        print(f"  {key:<26}: {metrics[key]}")

    heading("EVALUATION BENCHMARK (real recorded test outcomes)")
    evaluation = call("/api/evaluation/run", "POST")
    print(f"  cases            : {evaluation['passed_cases']}/{evaluation['total_cases']} passed")
    print(f"  detection rate   : {evaluation['detection_rate']}")
    print(f"  prevention rate  : {evaluation['prevention_rate']}")
    print(f"  false positives  : {evaluation['false_positive_rate']}")
    print(f"  avg latency (ms) : {evaluation['decision_latency_avg_ms']}")
    for row in evaluation["rows"]:
        flag = "PASS" if row["passed"] else "FAIL"
        print(f"    [{flag}] {row['kind']:<7} {row['case']}: {row['expected']} -> {row['actual']}")

    heading("DEMO COMPLETE")


if __name__ == "__main__":
    main()
