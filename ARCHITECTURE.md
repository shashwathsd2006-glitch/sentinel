# SENTINEL-X — Architecture

## 1. High-level picture

```
┌────────────────────────────── Browser (Next.js dashboard) ──────────────────────────────┐
│  Overview · Live Stream · Incidents · Approvals · Scenario Lab · Evaluation             │
│                        typed fetch client (src/lib/api.ts, polling every 2–6 s)          │
└───────────────────────────────────────┬──────────────────────────────────────────────────┘
                                        │ HTTP/JSON  (CORS allow-list for the local
                                        │            dashboard origins; NO auth)
┌───────────────────────────────────────▼──────────────────────────────────────────────────┐
│ FastAPI (backend/app/main.py)                                                            │
│   /health /api/agents /api/policies /api/events /api/approvals /api/scenarios           │
│   /api/incidents /api/metrics /api/evaluation/run                                        │
│                                    │                                                      │
│                          ┌─────────▼──────────┐   issues decisions + explanations        │
│                          │  GATEWAY (gateway.py) │  ◀── THE single chokepoint            │
│                          └─────────┬──────────┘                                          │
│             1 context │ 2 evaluate│ 3 enforce │ 4 ticket │ 5 audit                       │
│                          ┌─────────▼──────────┐                                          │
│                          │ PolicyEngine (policy.py)                                      │
│                          │ deny rules → approval rules → risk gates                      │
│                          │ fail-closed: any exception ⇒ BLOCK (P-FAIL-001)               │
│                          └─────────┬──────────┘                                          │
│                          ┌─────────▼──────────┐                                          │
│                          │ tools.py (simulated protected tools)                          │
│                          │ execute_tool() verifies an HMAC execution ticket              │
│                          └─────────┬──────────┘                                          │
│                                    │ SQLAlchemy                                           │
│                          ┌─────────▼──────────┐                                          │
│                          │ SQLite (sentinel.db)                                          │
│                          │ events · approvals · runs · steps · incidents · test_results  │
│                          └────────────────────┘                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## 2. The enforcement path (one action)

1. **Context construction** (`Gateway.build_context`) — agent + clearance + granted tools,
   session id, tool, params, derived `resource`, `destination`, `sensitivity`, and the
   **full action history of the session** (loaded from persisted audit events).
2. **Policy evaluation** (`PolicyEngine.evaluate`, timed with `perf_counter`):
   - *Deny rules* first: `P-TOOL-001` tool grant, `P-RES-001` clearance,
     `P-DEST-001` destination allow-list, `P-CUM-001` cumulative exposure sequence,
     `P-CUM-002` exfiltration content.
   - *Approval rules*: `P-TOOL-APPROVAL-001` protected operation,
     `P-RISK-001` score ≥ approval threshold (65).
   - *Risk block gate*: score ≥ block threshold (80) → `P-RISK-002`.
   - Any exception inside rule evaluation → **fail-closed** `BLOCK` with `P-FAIL-001`.
3. **Enforcement**:
   - `BLOCK` → tool is never invoked, an audit event is written with
     `executed=false, side_effect=false`.
   - `REQUIRE_APPROVAL` → a pending `Approval` row is created (single-use, TTL,
     SHA-256 parameter fingerprint); the tool does not run.
   - `ALLOW` → a **signed execution ticket** (HMAC-SHA256 over agent|session|tool|
     params-hash|nonce) is issued and `tools.execute_tool()` runs the tool.
4. **Ticket verification** — the simulated tool refuses to run without a valid ticket,
   so a bypass attempt (direct call, forged ticket, replay with altered params or a
   different session) raises `GatewayBypassError`. There is **no API endpoint that
   executes tools directly**; `POST /api/tools/execute` returns 404.
5. **Audit persistence** — every evaluation is persisted (`Event` row) including
   explanation, policy IDs, risk score, latency, executed/side-effect flags.

## 3. Approval lifecycle

```
REQUIRE_APPROVAL ─► PENDING ─approve─► revalidate (fresh evaluation, approval_context)
                         │                    ├─ ALLOW / REQUIRE_APPROVAL ⇒ execute
         │               │                    └─ BLOCK ⇒ status FAILED, nothing runs
         │               ├reject─► REJECTED (never executed)
         │               ├TTL passed► EXPIRED (never executed)
         └───────────────┴─second decision / consumed► HTTP 409 (replay rejected)
```

- **Single-use:** `consumed` is set *before* execution.
- **Expiry:** `expires_at = now + SENTINEL_APPROVAL_TTL_MINUTES` (default 15).
- **Binding:** SHA-256 fingerprint over agent|session|tool|canonical params; if the
  decision request supplies a mismatching fingerprint it is rejected (HTTP 409,
  `approval_params_mismatch`) — altered action parameters cannot be approved.
- **Revalidation:** the approval executes only after a *fresh* policy evaluation against
  the current history (e.g. if the tool grant was revoked meanwhile, `P-TOOL-001` denies
  and the approval ends as `FAILED` with no side effect).

## 4. Data model

| Table | Purpose |
|---|---|
| `agents` | agent id, role, **clearance**, granted tools (JSON) |
| `events` | immutable audit log: action, resource/destination, sensitivity, risk, decision, policies, explanation, executed, side_effect, latency |
| `approvals` | pending/resolved human decisions: params, fingerprint, status, expiry, outcome |
| `scenario_runs` / `scenario_steps` | scenario execution + per-step results |
| `incidents` | blocked sequences: trigger policy, blocked tool, evidence `protected_tool_executed` |
| `test_results` | recorded benchmark/pytest outcomes feeding the Evaluation page |

**Initialization:** `init_db()` on FastAPI startup runs `create_all` + idempotent agent
seed — the project's reliable startup path (Alembic intentionally not required for the MVP).

## 5. Cumulative risk model (why sequences are caught)

`compute_risk()` is deterministic:

```
score = tool_base_risk
      + sensitivity_weight (public 0 / internal 2 / confidential 8 / restricted 15)
      + destination_weight (internal 0 / partner 8 / external 20 / unknown 30)
      + min(30, 10 × distinct sensitive reads + 8 × sensitive writes already performed)
      + 12 if payload flagged PII + 8 if marked irreversible          → capped at 100
thresholds: ≥65 REQUIRE_APPROVAL, ≥80 BLOCK (both after deny rules)
```

The score is only half the story: `P-CUM-001` is a **sequence rule** that inspects the
session history directly — sensitive reads + a non-internal destination + a sensitive
payload = block, regardless of score. That is what stops Scenario B.

## 6. Scenario runner

`scenarios.py` declares three deterministic scenarios and executes their steps through
the gateway in one session each, supporting `{{result.<field>}}` chaining (e.g. the
artifact created by `create_summary` becomes the transfer payload). A `BLOCK` step
creates an `Incident`; a `REQUIRE_APPROVAL` step pauses the run
(`awaiting_approval`) until a human decision finishes it.

## 7. Frontend

- Next.js App Router, all views are client components polling the REST API
  (`usePolling`, 2.5–6 s intervals; no SSE — polling was the more reliable choice
  within the deadline).
- Shared dark UI kit (`src/components/ui.tsx`): cards, decision/risk/status badges,
  tables, meters, empty and error states.
- No static mock data: every view renders API responses and shows a clear empty state
  when a table is empty (e.g. Evaluation before any benchmark ran).

## 8. Swap-in points for optional infrastructure

| Future piece | Where it plugs in |
|---|---|
| **OPA / Rego** | Replace `PolicyEngine.evaluate()` with an HTTP `data.sentinel[x].allow` query; deny/approval/block contract and policy IDs stay identical (`P-*` documented in `policy.py`). |
| **PostgreSQL** | Change `SENTINEL_DB_PATH` → SQLAlchemy URL in `config.py`/`db.py`; models are portable SQLAlchemy 2.x. |
| **Alembic** | Standard migrations over `Base.metadata`; current `create_all` path remains as fallback. |
| **SSE/WebSocket** | Replace polling in `usePolling` — event rows are already append-only and ordered. |
| **LLM planning** | Would sit *upstream* of the gateway as another client; authorization decisions remain deterministic (an LLM can never authorize an operation). |

## 9. Ports and configuration

Backend `127.0.0.1:8010`, dashboard `127.0.0.1:3010` (8000/3000 occupied by unrelated
processes on this machine). All configuration flows through environment variables
(see `.env.example`); `NEXT_PUBLIC_API_URL` is read at build/dev time by the API client.
