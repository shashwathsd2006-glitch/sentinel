# SENTINEL-X — Demo Script (≈5 minutes)

**Setup before the demo (2 minutes, done once)**

```bash
# terminal 1
./scripts/start-backend.sh        # Windows: scripts\start-backend.bat
# terminal 2
./scripts/start-frontend.sh       # Windows: scripts\start-frontend.bat
```

Open **http://127.0.0.1:3010**. Confirm the top-right indicator shows *Gateway online*
and the Overview cards are non-zero (or start from a clean slate: stop the backend,
delete `backend/sentinel.db`, start again).

Optional one-command proof run (backend must be up):

```bash
backend/.venv/Scripts/python scripts/demo.py
```

---

## 1 · Overview (30 s) — "What is this?"

- Point at **Actions evaluated / Allowed / Blocked / Approval required**.
- Key line: *every number is computed from persisted audit rows, none are hardcoded.*
- Show **Prevention summary**: "operations stopped before any side effect" and the
  Evaluation snapshot (absent until a benchmark actually runs — deliberate empty state).

## 2 · Scenario Lab → A (45 s) — "Normal work flows freely"

- Open **Scenario Lab**, run **A — Legitimate workflow**.
- Read the three steps: `read_document → generate_report → save_to_destination`,
  all `ALLOW`, all *executed*, risk 7 → 12 → 10.
- Line: *"The gateway is not a blocker by default — legitimate work is fast and fully
  audited (each row carries an explanation and a latency figure)."*

## 3 · Scenario Lab → B (1 min 30 s) — "The differentiator"

- Run **B — Multi-step data exposure**; narrate as the steps appear:
  1. `read_customer_records` → **ALLOW** (support-agent is authorized — risk 27)
  2. `aggregate_customer_data` → **ALLOW** (risk 40)
  3. `create_summary` (contains PII) → **ALLOW** (risk 55)
  4. `transfer_external` → **BLOCK**, policy **`P-CUM-001`** — *"this session read
     sensitive data … individually permitted steps combine into a data-exposure path"*
- Stress the evidence: step 4 shows **not executed**, and the run summary says
  "Blocked before execution".
- Click through to the **Incident** view: ordered timeline (4 events), risk escalation
  bars, trigger policy, and the badge **Protected tool executed: NO**.
- Optional console proof that nothing left the system:
  `curl "http://127.0.0.1:8010/api/events?decision=BLOCK&limit=1"` → `"executed": false`.

## 4 · Scenario Lab → C + Approval Queue (1 min 30 s) — "Human in the loop"

- Run **C — Human approval**: step 1 proposal executes, step 2 pauses with
  `REQUIRE_APPROVAL` and the run status becomes **awaiting approval**.
- Go to **Approval Queue**: show operation, exact parameters (JSON), risk explanation,
  policy chips, fingerprint, expiry.
- **Approve** → the step turns executed, the operational record's version bumps, and the
  explanation says authorization was *revalidated immediately before execution*.
- **Try the abuse cases live:** pressing Approve again returns **409 replay rejected**;
  (via API) supplying a different fingerprint returns **409 approval_params_mismatch**;
  an approval left past its TTL returns **409 approval_expired**.
- Mention the rejection path: **Reject** leaves the protected record untouched
  (`executed=false`).

## 5 · Evaluation (45 s) — "Measured, not claimed"

- Open **Evaluation**: if no benchmark has run, highlight the deliberate **empty state**
  ("no fabricated numbers"), then press **Run benchmark suite**.
- Result table (9 recorded cases: 5 attack, 4 benign) with expected vs actual and
  per-case latency.
- Headline metrics: **detection rate, prevention rate, false-positive rate, average/p95
  decision latency** — all recomputed from stored `test_results` rows.

## 6 · Close (30 s)

- **Live Action Stream**: filters (scenario / decision / agent), click "why?" on any row
  for the explanation + policies + latency.
- Say what's intentionally out of scope: no OPA binary and no PostgreSQL/Docker in this
  environment → deterministic in-process policy engine with an OPA-ready seam and
  SQLite (documented in ARCHITECTURE.md / SECURITY.md).
- Optional developer proof: `cd backend && .venv/Scripts/python -m pytest` → **30 passed**.

---

### One-shot scripted demo (if time runs short)

```bash
backend/.venv/Scripts/python scripts/demo.py
```

Prints health → Scenario A → Scenario B + incident evidence → Scenario C + approval,
replay-409 → metrics → benchmark, straight from the live API.
