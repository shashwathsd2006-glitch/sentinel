# SENTINEL-X — Implementation Report (final)

Project root: `SENTINEL-X-OpenCode/` · DEVHOST 2026 · PS 2.1 (AI Agent Safety and Control)
Build date: **2026-10-25 (submission day)**

---

## 1. Delivered working software

| Component | Location | State |
|---|---|---|
| FastAPI backend (17 endpoints) | `backend/app/` | ✅ running & smoke-tested |
| Security gateway + deterministic policy/risk engine | `backend/app/gateway.py`, `backend/app/policy.py` | ✅ enforced, fail-closed |
| Simulated protected tools w/ signed execution tickets | `backend/app/tools.py` | ✅ bypass-proof (tested) |
| Persistence (SQLite + SQLAlchemy, startup init + seed) | `backend/app/db.py`, `models.py`, `seed.py` | ✅ audit rows persist across requests/restarts |
| Three demonstration scenarios + incident creation | `backend/app/scenarios.py` | ✅ A/B/C verified live |
| Approval lifecycle (single-use, TTL, fingerprint, revalidation) | `gateway.py` | ✅ verified live incl. 409 paths |
| Evaluation benchmark (17 cases) + metrics endpoints | `backend/app/benchmark.py`, `main.py` | ✅ 17/17 recorded (see EVALUATION.md §6–§7) |
| Dashboard (6 views) | `frontend/src/app/*` | ✅ builds, lints clean, all routes 200 |
| Tests (47) | `backend/tests/` | ✅ 47 passed |
| Scripts (start/run/demo, Windows + Git Bash) | `scripts/` | ✅ |
| Docs (README, ARCHITECTURE, SECURITY, DEMO_SCRIPT, EVALUATION) | root | ✅ |
| `.env.example`, `.gitignore`, `requirements.txt`, `package.json` + lockfile | root/backend/frontend | ✅ |

## 2. Priority checklist (per problem statement)

**P0**
- ✅ Runtime security gateway: every protected tool call goes through `Gateway.act()`;
  tools additionally verify an HMAC execution ticket issued only by the gateway.
- ✅ Three working scenarios: A (3×ALLOW + authorized side effect), B (3×ALLOW then
  **BLOCK before `transfer_external` executes**, incident recorded, outbound log empty),
  C (pause → human decision → revalidated execution).
- ✅ Backend API + persistent audit events (SQLite; `GET /api/events` reads real rows).
- ✅ Frontend connected to the backend (typed client, CORS verified, polling).

**P1**
- ✅ Incident investigation view (ordered timeline, risk escalation, triggered policy,
  blocked operation, attack-sequence explanation, "tool executed: NO" evidence).
- ✅ Human approval queue with visible outcomes, plus reject/expire/replay/tamper paths.
- ✅ Security metrics (live counters) + automated tests (47) + benchmark (17 cases).

**P2**
- ✅ Evaluation view with detection / false-positive / prevention / latency metrics from
  recorded outcomes only (empty state before any run), subtle animations, polished dark UI.
- ⛔ Optional LLM integration — intentionally omitted (deterministic scenarios only;
  an LLM must never authorize operations).
- ⛔ OPA/Rego, PostgreSQL, Docker Compose — environment fallback, see §4.

## 3. Verified end-to-end results (executed, not simulated)

```
GET  /health                                   → ok, db ok, 9 policies, fail-closed
POST /api/scenarios/scenario_a/run             → 201, status completed, 3×ALLOW executed
POST /api/scenarios/scenario_b/run             → 201, steps: ALLOW ALLOW ALLOW BLOCK(P-CUM-001)
                                                  transfer executed=false, incident created
GET  /api/incidents/{id}                       → timeline 4/4, protected_tool_executed=false
POST /api/scenarios/scenario_c/run             → 201, awaiting_approval, protected write untouched
POST /api/approvals/{id}/decision (approve)    → APPROVED, executed=true, record version +1
POST same approval again                       → 409 approval_conflict (replay)
POST decision w/ wrong fingerprint             → 409 approval_params_mismatch
POST decision after TTL                        → 409 approval_expired, status EXPIRED
POST /api/tools/execute                        → 404 (no bypass surface)
POST /api/evaluation/run                       → 17/17 passed, detection 1.0, prevention 1.0,
                                                  FP 0.0 (5 attack / 4 benign / 5 approval /
                                                  3 input-hardening; per-kind denominators)
CORS  Origin http://127.0.0.1:3010 (approved)  → access-control-allow-origin echoed
CORS  Origin https://untrusted.example         → NO access-control-allow-origin grant
pytest                                         → 47 passed
npm run lint                                   → 0 errors 0 warnings
npm run build                                  → success (10 routes)
```

## 4. Environment constraints and how they were handled

| Optional dependency | Availability here | Fallback used (allowed by PS §3) |
|---|---|---|
| PostgreSQL | ❌ `psql` not installed | **SQLite + SQLAlchemy** (real ORM, not a mock); one-line URL change to migrate |
| Docker / Compose | ❌ `docker` not installed | start scripts for Windows + Git Bash; **no Compose file shipped** (would be dead weight) |
| OPA / Rego | ❌ `opa` not installed | deterministic Python policy engine behind a single `evaluate()` seam; stable `P-*` policy IDs documented for a later Rego mirror |
| LLM API / keys / internet at runtime | deliberately not used | scripted deterministic scenarios |

Ports: **backend 8010, dashboard 3010** — 8000 and 3000 were already occupied by
unrelated processes; those were **not** touched, and 8010/3010 are used consistently in
scripts, `.env.example`, README and the frontend API client default.

## 5. Known issues / work items

1. **API has no authentication** — intended for localhost demo only; every startup
   path binds `127.0.0.1` (SECURITY.md §3–§4). CORS restricts which browser origins
   can *read* responses but does **not** authenticate callers. Put auth in front
   before exposing beyond 127.0.0.1.
2. **`@app.on_event("startup")` deprecation warning** on FastAPI 0.162 — harmless now;
   migrate to a lifespan handler before upgrading further.
3. **Polling instead of SSE** (2.5–6 s) — acceptable for the demo; an events endpoint
   already returns ordered rows, so SSE is a small follow-up.
4. **`next build` warns that `package-lock.json` in `C:\Users\admin` is outside the git
   repo** — that lockfile pre-exists on the machine (user-owned, untouched); the
   frontend's own `package-lock.json` is present and used.
5. **Single-worker SQLite** — approval single-use is enforced by an atomic
   compare-and-set UPDATE, so it is safe against concurrent requests on one
   worker; use PostgreSQL + row locks for multi-node deployments.
6. **`Sentinel-X-VSCode` project** — never accessed or modified (it did not exist in the
   working directory at build time; nothing outside `SENTINEL-X-OpenCode/` was written).
7. **`frontend/.git`** — `create-next-app` initialized a local git repo inside
   `frontend/`. It was removed when the project was pushed as **one clean repository**
   to `https://github.com/shashwathsd2006-glitch/sentinel` (branch `main`); its
   auto-generated "Initial commit from Create Next App" history is intentionally not
   preserved.
8. **Empty `docs/` folder** created during scaffolding was removed; docs live at the
   project root as required.
9. Risk thresholds (65/80) and TTL (15 min) are heuristics tuned for the scenarios and
   are configurable via environment variables.
10. No load/fuzz testing (documented in EVALUATION.md §5).

## 6. How to run (one command each)

```bash
./scripts/start-backend.sh      # or scripts\start-backend.bat   → :8010
./scripts/start-frontend.sh     # or scripts\start-frontend.bat  → :3010
backend/.venv/Scripts/python scripts/demo.py   # scripted end-to-end proof
cd backend && .venv/Scripts/python -m pytest   # 47 tests
```

Dashboard: **http://127.0.0.1:3010** · API docs: **http://127.0.0.1:8010/docs**
