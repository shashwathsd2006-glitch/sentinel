# SENTINEL-X — Threat Model, Assumptions and Limitations

## 1. What we defend against

| # | Threat | Mitigation (implemented & tested) |
|---|---|---|
| T1 | **Multi-step data exposure**: an agent chains individually permitted reads/aggregations into an external transfer | `P-CUM-001` inspects the *session's persisted action history* (sensitive reads) combined with destination trust and payload sensitivity → `BLOCK` before `transfer_external` runs. Test: `test_cumulative_sequence_blocks_transfer`, benchmark case "cumulative customer-data exfiltration". |
| T2 | **PII relay** to partner/untrusted endpoints | `P-CUM-002` (payload flagged PII + non-internal destination) and `P-CUM-001`. Test: benchmark "PII relay to partner endpoint". |
| T3 | **Unauthorized tool use** by an agent without the grant | `P-TOOL-001` evaluated first. Tests: `test_unauthorized_tool_grant_blocked`, benchmark "unauthorized external transfer capability". |
| T4 | **Over-privileged reads** (resource sensitivity above agent clearance) | `P-RES-001`. Test: `test_resource_clearance_enforced`. |
| T5 | **Writes to unauthorized destinations** | `P-DEST-001` per-tool destination allow-list (`save_to_destination` → internal only). |
| T6 | **Gateway bypass**: agent/tooling calls a protected tool directly, forges or replays an execution ticket | `tools.execute_tool()` requires an HMAC-SHA256 ticket bound to agent+session+tool+params-hash; mismatch → `GatewayBypassError`. No public endpoint executes tools (`POST /api/tools/execute` → 404). Tests: `test_direct_tool_invocation_is_rejected`, `test_forged_ticket_rejected`, `test_ticket_is_parameter_bound`, `test_no_raw_execution_endpoint`. |
| T7 | **Approval abuse**: replay a used approval, approve altered parameters, use an expired approval | `status != PENDING`/`consumed` → 409; fingerprint mismatch → 409 `approval_params_mismatch`; TTL → status `EXPIRED`, never executed. Tests: `test_approval_replay_rejected`, `test_altered_parameters_rejected`, `test_expired_approval_not_executable`. |
| T8 | **TOCTOU**: policy/privileges change between approval and execution | Immediate re-evaluation of the action against current policy + history right before execution; on `BLOCK` the approval ends `FAILED` and nothing runs. Test: `test_revalidation_revokes_before_execution`. |
| T9 | **Policy engine failure** (exception, missing rules) | Fail-closed: any evaluation exception → `BLOCK` with `P-FAIL-001`. Test: `test_fail_closed_on_policy_error`. |
| T10 | **Silent/missing audit trail** | Every evaluated action writes an `Event` row (decision, explanation, policies, risk, latency, executed/side-effect) committed before returning. Tests: `test_audit_events_persisted_with_decisions`, `test_api_metrics...`. |
| T11 | **Unprotected modification before human consent** | `modify_operational_record` requires approval (`P-TOOL-APPROVAL-001`); side effect only after an approved decision. Test: `test_approval_required_before_protected_modification`. |

## 2. Trust boundaries

```
[AI agent intent] → (scenario runner / API) → ★ GATEWAY ★ → [simulated tools & data stores]
                                                        ↘ [audit DB]
[human reviewer]  → approval decision API ─── revalidate ──┘
```

- Everything **left of the gateway** is untrusted input (agent, session, params).
- The gateway is the only component that can mint execution tickets.
- The simulated tools are the only components that produce side effects, and they
  verify tickets themselves (defence in depth even if a future endpoint forgets to
  route through the gateway).
- The dashboard is a *read/decide* client: it cannot invoke tools, only list data and
  submit approval decisions that the gateway revalidates.

## 3. Assumptions

1. **Simulated environment.** All "customer records", documents, emails, transfers and
   operational data are local fakes. No real data, no outbound network calls.
2. **Deterministic agents.** Scenarios are scripted for repeatable demos; an LLM agent
   would sit upstream of the gateway and is *never* consulted for authorization.
3. **Single-process deployment.** One uvicorn worker + SQLite file; no concurrent
   multi-writer contention. Approval single-use is enforced within the request
   transaction (sufficient for a single worker; use `SELECT ... FOR UPDATE` on
   PostgreSQL for multi-node deployments).
4. **Clock trust.** Approval expiry uses the server's clock.
5. **Operator identity.** The `actor` field on approval decisions is self-asserted;
   a production deployment must put authentication (OIDC/SSO) in front of it.
6. **Ticket secret.** `SENTINEL_TICKET_SECRET` is process-local by default; a random
   secret is generated per process. In production it must be a managed secret.

## 4. Limitations (honest scope)

- **No authentication/authorization on the HTTP API itself.** The gateway protects
  *tool execution*; the dashboard/API is open on localhost. Bind to 127.0.0.1 (default)
  and add auth before any network exposure.
- **Policy engine is Python, not OPA/Rego.** Rules are modular, stable-ID'd and sit
  behind a single `evaluate()` seam so OPA can be swapped in; Rego translation was not
  implemented because `opa` is unavailable in this environment.
- **SQLite, not PostgreSQL.** Chosen via the mandated fallback (no `psql`/Docker here);
  models are portable SQLAlchemy 2.x and the DB URL is a one-line change.
- **Polling, not SSE.** The dashboard refreshes every 2.5–6 s; sub-second push updates
  would need an SSE endpoint (easy follow-up: events are append-only).
- **Risk thresholds are heuristics** (approval 65, block 80) tuned for the demo
  scenarios; they are configurable by env var and every decision is explained.
- **No adversarial red-team coverage beyond the 9 benchmark cases** (5 attack,
  4 benign); extend `backend/app/benchmark.py::CASES` to broaden it.
- **Approval actor is not audited cryptographically** (no signature/MFA).
- Rate limiting, IP allow-listing, TLS and DB encryption are out of scope for the MVP.

## 5. Security properties claimed (and where proven)

| Claim | Proof |
|---|---|
| "Blocked actions never execute" | `Event.executed=false` + `side_effect=false` for every BLOCK; `OUTBOUND_LOG` empty after Scenario B (`test_cumulative_sequence_blocks_transfer`); incident `protected_tool_executed=false`. |
| "No protected write before approval" | Scenario C step 2 has `executed=false` until an approved decision; `OPERATIONAL_RECORD.version` unchanged (`test_approval_required_before_protected_modification`). |
| "Approvals are single-use, expiring, bound" | Fingerprint + TTL + `consumed` checks; tests T7 above. |
| "Fail-closed" | `test_fail_closed_on_policy_error`; `P-FAIL-001` row in the events table on such an event. |
| "Bypass is not possible via the public API" | `test_no_raw_execution_endpoint` + ticket verification inside `tools.execute_tool`. |
