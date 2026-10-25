"use client";

import { useState } from "react";
import {
  CheckCircle2,
  FlaskConical,
  Loader2,
  Play,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import {
  apiGet,
  apiPost,
  type ApprovalItem,
  type DecisionResponse,
  type RunDetail,
  type RunSummary,
  type ScenarioInfo,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  Button,
  Card,
  CardHeader,
  DecisionBadge,
  EmptyState,
  ErrorState,
  RiskBadge,
  Spinner,
  StatusPill,
  formatTsFull,
} from "@/components/ui";

export default function ScenarioLabPage() {
  const { data: scenarios, error: scenError } = usePolling<{
    items: ScenarioInfo[];
  }>(() => apiGet("/api/scenarios"), { intervalMs: 15000 });

  const { data: runs, refresh: refreshRuns } = usePolling<{
    items: RunSummary[];
    total: number;
  }>(() => apiGet("/api/scenarios/runs?limit=10"), { intervalMs: 5000 });

  const [activeId, setActiveId] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [decisionMsg, setDecisionMsg] = useState<string | null>(null);

  const { data: activeRun, refresh: refreshActive } = usePolling<RunDetail>(
    () => apiGet<RunDetail>(`/api/scenarios/${activeId}`),
    { intervalMs: 2500, enabled: !!activeId },
  );

  async function run(id: string) {
    setRunningId(id);
    setActionError(null);
    setDecisionMsg(null);
    try {
      const created = await apiPost<RunDetail>(`/api/scenarios/${id}/run`);
      setActiveId(created.id);
      await refreshRuns();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunningId(null);
    }
  }

  async function decide(approval: ApprovalItem, decision: "approve" | "reject") {
    if (decidingId) return; // guard against duplicate submissions
    setDecidingId(approval.id);
    setActionError(null);
    setDecisionMsg(null);
    try {
      const res = await apiPost<DecisionResponse>(
        `/api/approvals/${approval.id}/decision`,
        {
          decision,
          actor: "lab-reviewer",
          fingerprint: decision === "approve" ? approval.fingerprint : null,
        },
      );
      // Report the actual execution outcome, not just the decision label.
      if (res.result.executed) {
        setDecisionMsg(`${res.result.explanation} (executed exactly once)`);
      } else if (res.result.error) {
        setDecisionMsg(`Decision recorded, but execution failed: ${res.result.error}`);
      } else {
        setDecisionMsg(res.result.explanation);
      }
      await Promise.all([refreshActive(), refreshRuns()]);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setDecidingId(null);
    }
  }

  return (
    <div className="space-y-5 animate-in">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">Scenario Lab</h2>
        <p className="text-xs text-slate-400">
          Deterministic agent scenarios executed through the live security gateway —
          every result below comes from real backend execution
        </p>
      </div>

      {scenError ? <ErrorState message={scenError} /> : null}
      {actionError ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-xs text-rose-200">
          {actionError}
        </div>
      ) : null}
      {decisionMsg ? (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/30 px-4 py-3 text-xs text-emerald-200">
          {decisionMsg}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        {scenarios?.items.map((s) => (
          <Card key={s.id} className="flex flex-col p-5">
            <div className="flex items-start justify-between gap-2">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-lg border ${
                  s.attack
                    ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
                    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                }`}
              >
                {s.attack ? <ShieldAlert size={16} /> : <FlaskConical size={16} />}
              </div>
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  s.attack
                    ? "border-rose-500/40 text-rose-300"
                    : "border-emerald-500/40 text-emerald-300"
                }`}
              >
                {s.attack ? "attack" : "legitimate"}
              </span>
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-100">{s.title}</h3>
            <p className="mt-1.5 flex-1 text-xs leading-relaxed text-slate-400">
              {s.description}
            </p>
            <ol className="mt-3 space-y-1 border-t border-slate-800 pt-3">
              {s.steps.map((step) => (
                <li key={step.index} className="flex items-center gap-2 text-[11px]">
                  <span className="w-4 text-right text-slate-600">
                    {step.index + 1}
                  </span>
                  <span className="text-slate-400">{step.label}</span>
                  <span className="ml-auto font-mono text-[10px] text-slate-600">
                    {step.tool}
                  </span>
                </li>
              ))}
            </ol>
            <div className="mt-4 flex items-center gap-2">
              <Button
                onClick={() => void run(s.id)}
                disabled={runningId !== null}
                className="flex-1"
              >
                {runningId === s.id ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Play size={13} />
                )}
                {runningId === s.id ? "Running…" : "Run scenario"}
              </Button>
            </div>
            <p className="mt-2 text-[10px] text-slate-600">agent: {s.agent_id}</p>
          </Card>
        ))}
        {!scenarios && !scenError ? <Spinner label="Loading scenarios" /> : null}
      </div>

      {activeRun ? (
        <Card>
          <CardHeader
            title={`Run results · ${activeRun.title}`}
            subtitle={`${activeRun.id} · started ${formatTsFull(activeRun.started_at)}`}
            right={
              <div className="flex items-center gap-2">
                <StatusPill value={activeRun.status} />
                <span className="text-[11px] text-slate-500">
                  {activeRun.allowed_count} allowed · {activeRun.blocked_count}{" "}
                  blocked · {activeRun.approval_count} approval
                </span>
              </div>
            }
          />
          <p className="border-b border-slate-800 px-5 py-3 text-xs text-slate-400">
            {activeRun.summary}
          </p>

          <ol className="divide-y divide-slate-800/70">
            {activeRun.steps.map((step) => (
              <li key={step.step_index} className="px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-[11px] text-slate-400">
                      {step.step_index + 1}
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-slate-200">
                        {step.label}
                      </p>
                      <p className="font-mono text-[11px] text-cyan-400">
                        {step.tool}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <RiskBadge value={step.risk_level} score={step.risk_score} />
                    <DecisionBadge value={step.decision || step.status} />
                    <span
                      className={`w-24 text-right text-[11px] ${
                        step.executed ? "text-emerald-400" : "text-slate-500"
                      }`}
                    >
                      {step.executed ? "executed" : "not executed"}
                    </span>
                  </div>
                </div>
                <p className="mt-2 pl-9 text-[11px] leading-relaxed text-slate-400">
                  {step.explanation}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2 pl-9">
                  {step.policies.map((p) => (
                    <span
                      key={p}
                      className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300"
                    >
                      {p}
                    </span>
                  ))}
                  {step.decision === "BLOCK" ? (
                    <span className="inline-flex items-center gap-1 text-[10px] text-rose-300">
                      <XCircle size={11} /> protected tool never ran — no side effect
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>

          {activeRun.approvals?.length ? (
            <div className="border-t border-slate-800 px-5 py-4">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                Pending human decision
              </p>
              {activeRun.approvals
                .filter((a) => a.status === "PENDING")
                .map((a) => (
                  <div
                    key={a.id}
                    className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-amber-200">
                          {a.tool} on {a.resource}
                        </p>
                        <p className="mt-1 text-[11px] text-amber-200/70">
                          {a.explanation}
                        </p>
                        <pre className="mt-2 rounded border border-amber-500/20 bg-slate-950/60 p-2 text-[10px] text-slate-400">
                          {JSON.stringify(a.params, null, 1)}
                        </pre>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          onClick={() => void decide(a, "approve")}
                          disabled={decidingId !== null}
                        >
                          <CheckCircle2 size={13} /> Approve exact action
                        </Button>
                        <Button
                          variant="danger"
                          onClick={() => void decide(a, "reject")}
                          disabled={decidingId !== null}
                        >
                          <XCircle size={13} /> Reject
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              {activeRun.status === "awaiting_approval" &&
              !activeRun.approvals.some((a) => a.status === "PENDING") ? (
                <p className="mt-2 text-xs text-slate-400">
                  Decision recorded — refreshing…
                </p>
              ) : null}
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Recent runs"
          subtitle="Reruns are deterministic and safe"
        />
        {runs && runs.items.length > 0 ? (
          <ul className="divide-y divide-slate-800/70">
            {runs.items.map((r) => (
              <li
                key={r.id}
                className="flex cursor-pointer flex-wrap items-center gap-3 px-5 py-3 text-xs transition-colors hover:bg-slate-800/30"
                onClick={() => setActiveId(r.id)}
              >
                <span className="font-mono text-[11px] text-slate-500">{r.id}</span>
                <span className="text-slate-300">{r.title}</span>
                <StatusPill value={r.status} />
                <span className="text-[11px] text-slate-500">
                  {formatTsFull(r.started_at)}
                </span>
                <span className="ml-auto text-[11px] text-cyan-500">view →</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="No runs yet"
            description="Execute a scenario above to see step-by-step gateway decisions here."
          />
        )}
      </Card>
    </div>
  );
}
