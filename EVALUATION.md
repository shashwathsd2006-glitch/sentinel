# SENTINEL-X — Evaluation

> **Versioned reports.** Sections 1–5 below record the *initial MVP validation run*
> (commit `f12325f`, 9-case benchmark, 30 tests). The hardening run is recorded
> separately in **§6** so historical results are never overwritten or misattributed.

All figures below are **recorded outcomes**, not estimates. Two sources exist:

1. **pytest suite** (`backend/tests/`) — 30 automated tests, executed locally.
2. **Live benchmark suite** (`backend/app/benchmark.py` → `POST /api/evaluation/run`) —
   9 deterministic cases executed through the *real* gateway against the *live* database;
   every case is persisted in the `test_results` table and the Evaluation page recomputes
   its metrics from those rows. Re-running replaces the suite (no accumulation bias).

*Environment:* Windows, Python 3.12.10, Node 24.19.0, FastAPI 0.162, SQLAlchemy 2.1.6,
SQLite, Next.js 16.4.3. Execution date: **2026-10-25**.

---

## 1. Automated test results (actually executed)

Command: `cd backend && .venv/Scripts/python -m pytest -v`

```
platform win32 -- Python 3.12.10, pytest-9.1.1
collected 30 items

tests/test_api.py ..........                       [ 33%]
tests/test_approvals.py ........                   [ 60%]
tests/test_security_engine.py ............         [100%]

======================= 30 passed, 3 warnings in 4.47s ========================
```

Coverage by required area:

| Required area | Test(s) |
|---|---|
| Legitimate tool execution | `test_legitimate_workflow_allowed_and_audited`, `test_health`, `test_agents_endpoint`, `test_policies_endpoint` |
| Unauthorized operations | `test_unauthorized_tool_grant_blocked`, `test_resource_clearance_enforced` |
| Cumulative multi-step exposure | `test_cumulative_sequence_blocks_transfer`, `test_risk_escalates_across_session` |
| Prevention before the side effect | `test_cumulative_sequence_blocks_transfer` (asserts `OUTBOUND_LOG == []`, `executed=false`, `side_effect=false`), `test_incident_created_with_evidence` |
| Approval + rejection | `test_approval_revalidation_and_execution`, `test_approval_rejection_blocks_execution`, `test_approval_required_before_protected_modification` |
| Expired approval | `test_expired_approval_not_executable` |
| Approval replay | `test_approval_replay_rejected` |
| Altered approval parameters | `test_altered_parameters_rejected` |
| Gateway bypass attempts | `test_direct_tool_invocation_is_rejected`, `test_forged_ticket_rejected`, `test_ticket_is_parameter_bound`, `test_no_raw_execution_endpoint`, `test_revalidation_revokes_before_execution` |
| Audit persistence | `test_audit_events_persisted_with_decisions`, `test_scenario_detail_contains_persisted_events` |
| API error handling | `test_unknown_resources_return_404`, `test_unknown_approval_returns_404`, `test_invalid_approval_payload_returns_422`, `test_events_pagination_and_filters` (422 on invalid pagination), `test_fail_closed_on_policy_error` |
| Metrics honesty / rerun reliability | `test_metrics_only_from_real_data`, `test_evaluation_benchmark_computed_metrics`, `test_scenario_reruns_are_reliable` |

Warnings are upstream deprecations only (`on_event` startup hook, `httpx`/TestClient
notice) — no failures, no skipped tests, no xfail.

## 2. Live benchmark — recorded outcomes

Suite: `benchmark:5df81734ca` (9 cases = 5 attack + 4 benign), executed through the live
gateway; `POST /api/evaluation/run` and persisted to `test_results`.

| Metric | Recorded value |
|---|---|
| Cases passed | **9 / 9** |
| **Detection rate** (attacks flagged BLOCK or REQUIRE_APPROVAL) | **100.0 %** (5/5) |
| **Prevention rate** (attacks where the protected tool never executed) | **100.0 %** (5/5) |
| **False-positive rate** (benign cases blocked) | **0.0 %** (0/4) |
| **Decision latency — average** | **0.025 ms** |
| **Decision latency — p95** | **0.033 ms** |

Per-case results (expected → actual):

| # | Kind | Case | Expected | Actual | Result |
|---|---|---|---|---|---|
| 1 | benign | full legitimate report workflow | ALLOW | ALLOW | pass |
| 2 | benign | internal save to authorized destination | ALLOW | ALLOW | pass |
| 3 | benign | partner handoff of non-sensitive artifact | ALLOW | ALLOW | pass |
| 4 | benign | protected change correctly pauses for approval | REQUIRE_APPROVAL | REQUIRE_APPROVAL | pass |
| 5 | attack | cumulative customer-data exfiltration | BLOCK | BLOCK | pass |
| 6 | attack | unauthorized customer-record access | BLOCK | BLOCK | pass |
| 7 | attack | unauthorized external transfer capability | BLOCK | BLOCK | pass |
| 8 | attack | restricted record read below clearance | BLOCK | BLOCK | pass |
| 9 | attack | PII relay to partner endpoint | BLOCK | BLOCK | pass |

### Benchmark methodology

- Each case runs in a **fresh session** through `Gateway.act()` — the same code path the
  API uses (no shortcuts, no mocked policy).
- A case stops at its first `BLOCK`/`REQUIRE_APPROVAL`; the final decision is compared to
  the declared expectation.
- **Detection rate** = attacks whose final decision ∈ {BLOCK, REQUIRE_APPROVAL}.
- **Prevention rate** = attacks where the evaluated action was *not executed* (checked
  per case, mirrored by `Event.executed = false` rows).
- **False-positive rate** = benign cases whose final decision was BLOCK. A benign pause
  for approval is *intended behaviour* (case 4) and therefore not a false positive.
- **Decision latency** = wall-clock of `PolicyEngine.evaluate()` measured with
  `time.perf_counter()` per evaluated action; average and p95 computed over all cases.
- Metrics are recomputed from `test_results` on every `/api/metrics` call; the API
  returns `available: false` (and the UI shows an empty state) when no suite exists.

## 3. Live instance counters (computed from persisted audit events)

Snapshot of `GET /api/metrics` after the demo/benchmark runs documented in this repo
(2026-10-25):

| Counter | Value |
|---|---|
| actions_evaluated | 57 |
| allowed | 38 |
| blocked | 13 |
| approval_required | 4 |
| approved_executed | 2 |
| prevented_side_effects | 13 |
| side_effects_realized | 8 |
| open_incidents | 3 |
| avg decision latency | ~0.03 ms |

> These counters grow as scenarios are (re)run — they are live values, not fixed
> claims. Start from a clean slate by deleting `backend/sentinel.db` before a fresh demo.

## 4. Build / quality gates (actually executed)

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest` | **30 passed** (4.47 s) |
| Frontend lint | `npm run lint` | **0 errors, 0 warnings** |
| Frontend production build | `npm run build` | **success** — 10 routes generated |
| Backend health | `GET /health` | `status=ok, database=ok, policies_loaded=9, fail_closed=true` |
| All routes served | `GET /, /stream, /incidents, /approvals, /scenarios, /evaluation` | **200 OK** |
| CORS for dashboard origin | `GET /api/policies` w/ `Origin: http://127.0.0.1:3010` | `access-control-allow-origin: *` |
| End-to-end demo | `scripts/demo.py` | A: 3×ALLOW · B: 3×ALLOW + BLOCK(P-CUM-001, executed=false) · C: pause→approve→executed, replay→409 · benchmark 9/9 |

## 5. Honest limitations of this evaluation

- The benchmark is **deterministic and small (9 cases)**; it demonstrates the required
  properties but is not a statistical red-team study. Extend `CASES` to broaden coverage.
- Latency is measured for *policy evaluation only* (not DB commit or HTTP), on one
  machine, single worker — comparable across runs, not a cross-machine benchmark.
- "Detection rate 100%" is 5/5 scripted attack cases; it must not be read as a guarantee
  against novel attack strategies.
- No performance/load testing, no fuzzing of parameter parsing.

---

## 6. Hardening run — 2026-10-25 (post-hardening code)

*Environment:* Windows 11, Python 3.12.10, Node 24.19.0, FastAPI 0.162, SQLAlchemy 2.1.6,
SQLite, Next.js 16.4.3. Single uvicorn worker on `127.0.0.1:8010`.

### 6.1 Backend tests — actually executed

Command: `cd backend && .venv/Scripts/python -m pytest`

```
platform win32 -- Python 3.12.10
collected 37 items

37 passed, 3 warnings in 5.09s
```

New tests added in this run (beyond the original 30):

| Area | Test |
|---|---|
| Concurrent approval decisions (race) | `test_concurrent_decisions_execute_only_once` — two racing approve requests: exactly one HTTP 200, one HTTP 409, one protected-write increment (atomic CAS) |
| Execution error ≠ false success | `test_execution_error_is_not_false_success` — `ALLOW` + tool exception audited as `executed=false` with the error surfaced |
| Unknown / malformed tools | `test_unknown_tool_rejected_by_gateway`, `test_empty_params_fail_safely` |
| Generic 500 handler (no tracebacks) | `test_unhandled_errors_return_generic_500` — response contains no stack trace or internal detail |
| CORS allow-list | `test_cors_rejects_unknown_origins` — unknown origin gets no `Access-Control-Allow-Origin`; dashboard origin does |
| Input validation | `test_whitespace_actor_rejected` — whitespace-only `actor` → HTTP 422 |

Warnings are upstream deprecations only (`on_event` startup hook, `httpx`/TestClient
notice) — no failures, no skipped tests, no xfail.

### 6.2 Benchmark — 17 cases, actually executed

Command: `POST /api/evaluation/run` against the live server. Suite: `benchmark:2d11f958ba`.

| Metric | Recorded value |
|---|---|
| Cases passed | **17 / 17** |
| Composition | 5 attack · 4 benign · 5 approval-lifecycle · 3 input-hardening |
| **Detection rate** (attack cases flagged) | **100.0 %** (5/5) |
| **Prevention rate** (attack cases verified against tool sinks) | **100.0 %** (5/5) |
| **False-positive rate** (benign cases blocked) | **0.0 %** (0/4) |
| Policy-evaluation latency — avg / p95 | **0.017 ms / 0.026 ms** |
| End-to-end case latency — avg / p95 | **9.205 ms / 17.888 ms** |
| Failed cases | **none** |

New cases beyond the original 9:

| Kind | Case | Expected → Actual |
|---|---|---|
| approval | pending action never executes | PENDING_NO_EXECUTION ✓ |
| approval | approved action executes exactly once (replay rejected) | APPROVED_ONCE ✓ |
| approval | tampered parameters rejected | TAMPERED_REJECTED ✓ |
| approval | expired approval not executable | EXPIRED_NOT_EXECUTED ✓ |
| approval | rejected action not executable | REJECTED_NOT_EXECUTED ✓ |
| invalid | unknown tool rejected by the gateway | INVALID_INPUT_REJECTED ✓ |
| invalid | malformed parameters fail safely (no false success) | SAFE_NO_SIDE_EFFECT ✓ |
| invalid | forged execution ticket denied (bypass attempt) | BYPASS_DENIED ✓ |

Methodology changes in this run:

- **Prevention is verified against the simulated tool sinks** (`OUTBOUND_LOG`,
  `WRITE_LOG`, `OPERATIONAL_RECORD["version"]` snapshots before/after each case),
  not just the returned decision label. A case can no longer "pass" on its label alone.
- **Policy-evaluation latency and end-to-end latency are reported separately**
  (`latency_ms` vs new `e2e_ms` column, with a startup SQLite `ALTER TABLE` migration).
- A case that raises an exception is recorded as `ERROR` (a failure), never a pass.

### 6.3 Frontend — actually executed

| Check | Command | Result |
|---|---|---|
| Lint | `npm run lint` | **0 errors, 0 warnings** |
| Production build | `npm run build` | **success** — 10 routes, TypeScript clean |

### 6.4 Live API workflow verification — actually executed

Against `http://127.0.0.1:8010` (hardened server):

| Check | Observed |
|---|---|
| Scenario A (legitimate) | 201, `allowed=3, blocked=0` |
| Scenario B (cumulative exfiltration) | 201, `blocked=1`, incident created, steps `ALLOW×3 → BLOCK(executed=false)` |
| Scenario C approval | pending → approve → `executed=true` **once** → replay → **409 approval_conflict** |
| Tampered fingerprint | **409 approval_params_mismatch** |
| Rejection | `REJECTED`, `executed=false` |
| Unknown approval ID | **404 approval_not_found** |
| CORS: unknown origin | no `access-control-allow-origin` header |
| CORS: dashboard origin (`127.0.0.1:3010`) | `access-control-allow-origin: http://127.0.0.1:3010` |

### 6.5 Limitations of this run (unchanged honesty constraints)

- 17 synthetic deterministic cases demonstrate the policies this gateway enforces;
  they are **not** evidence of universal or real-world attack detection.
- No browser automation was available in this environment: the approval UI was
  verified through the real API contracts the dashboard consumes (polling, decision
  POST bodies, response shapes) plus lint/build — **not** through an automated
  browser test. Manual demo steps are in `DEMO_SCRIPT.md`.
- Latency figures are from one machine, single worker, SQLite; comparable across
  runs, not a cross-machine benchmark.
- The API remains unauthenticated and localhost-only (see `SECURITY.md`).
