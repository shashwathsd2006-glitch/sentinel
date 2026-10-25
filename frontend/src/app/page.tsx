"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  PauseCircle,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import {
  apiGet,
  type EventItem,
  type IncidentItem,
  type Metrics,
} from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  Card,
  CardHeader,
  DecisionBadge,
  EmptyState,
  ErrorState,
  MeterBar,
  RiskBadge,
  Spinner,
  StatCard,
  Table,
  formatTs,
} from "@/components/ui";

export default function OverviewPage() {
  const { data: metrics, error, loading, refresh } = usePolling<Metrics>(
    () => apiGet<Metrics>("/api/metrics"),
    { intervalMs: 4000 },
  );
  const { data: events } = usePolling<{ items: EventItem[]; total: number }>(
    () => apiGet("/api/events?limit=8"),
    { intervalMs: 4000 },
  );
  const { data: incidents } = usePolling<{ items: IncidentItem[]; total: number }>(
    () => apiGet("/api/incidents?limit=5"),
    { intervalMs: 6000 },
  );

  const [health, setHealth] = useState<string>("…");
  useEffect(() => {
    apiGet<{ status: string }>("/health")
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("offline"));
    const id = setInterval(() => {
      apiGet<{ status: string }>("/health")
        .then((h) => setHealth(h.status))
        .catch(() => setHealth("offline"));
    }, 10000);
    return () => clearInterval(id);
  }, []);

  if (loading && !metrics) return <Spinner label="Loading security metrics" />;
  if (error && !metrics)
    return <ErrorState message={error} onRetry={() => void refresh()} />;
  if (!metrics) return null;

  const m = metrics;
  const totalDecisions = m.allowed + m.blocked + m.approval_required +
    m.approved_executed + m.rejected + m.expired;

  return (
    <div className="space-y-5 animate-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">
            Security Operations Overview
          </h2>
          <p className="text-xs text-slate-400">
            Live counters computed from persisted gateway audit events ·
            generated {formatTs(m.generated_at)}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-[11px]">
          <span
            className={`h-2 w-2 rounded-full ${
              health === "ok" ? "bg-emerald-400" : "bg-rose-400"
            }`}
          />
          <span className="text-slate-400">API health: {health}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-6">
        <StatCard
          label="Actions evaluated"
          value={m.actions_evaluated}
          hint="Every gateway decision"
          tone="accent"
        />
        <StatCard
          label="Allowed"
          value={m.allowed}
          hint="Executed after checks"
          tone="good"
        />
        <StatCard
          label="Blocked"
          value={m.blocked}
          hint="Stopped pre-execution"
          tone="bad"
        />
        <StatCard
          label="Approval required"
          value={m.approval_required}
          hint="Paused for a human"
          tone="warn"
        />
        <StatCard
          label="Open incidents"
          value={m.open_incidents}
          hint="Sequences detected"
          tone="bad"
        />
        <StatCard
          label="Pending approvals"
          value={m.pending_approvals}
          hint="Awaiting decision"
          tone="warn"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader
            title="Decision distribution"
            subtitle={`${totalDecisions} recorded decisions`}
          />
          <div className="space-y-4 px-5 py-4">
            <MeterBar
              label="Allowed / Approved"
              value={m.allowed + m.approved_executed}
              total={totalDecisions}
              color="bg-emerald-500"
            />
            <MeterBar
              label="Blocked"
              value={m.blocked}
              total={totalDecisions}
              color="bg-rose-500"
            />
            <MeterBar
              label="Requires approval"
              value={m.approval_required}
              total={totalDecisions}
              color="bg-amber-500"
            />
            <MeterBar
              label="Rejected / Expired"
              value={m.rejected + m.expired}
              total={totalDecisions}
              color="bg-fuchsia-500"
            />
            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-800 pt-4 text-xs">
              <div>
                <p className="text-slate-500">Side effects realized</p>
                <p className="mt-1 text-base font-semibold text-slate-200">
                  {m.side_effects_realized}
                </p>
              </div>
              <div>
                <p className="text-slate-500">Side effects prevented</p>
                <p className="mt-1 text-base font-semibold text-rose-300">
                  {m.prevented_side_effects}
                </p>
              </div>
              <div>
                <p className="text-slate-500">Avg decision latency</p>
                <p className="mt-1 text-base font-semibold text-cyan-300">
                  {m.avg_decision_latency_ms.toFixed(3)} ms
                </p>
              </div>
              <div>
                <p className="text-slate-500">Executed actions</p>
                <p className="mt-1 text-base font-semibold text-slate-200">
                  {m.executed_actions}
                </p>
              </div>
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent security events"
            subtitle="Persisted audit records from the gateway"
            right={
              <Link
                href="/stream"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-cyan-400 hover:text-cyan-300"
              >
                Open live stream <ArrowRight size={13} />
              </Link>
            }
          />
          {events && events.items.length > 0 ? (
            <Table
              headers={["Time", "Agent", "Tool", "Decision", "Risk", "Side effect"]}
            >
              {events.items.map((e) => (
                <tr key={e.id} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 tabular-nums text-slate-400">
                    {formatTs(e.ts)}
                  </td>
                  <td className="px-4 py-2.5 text-slate-300">{e.agent_id}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-slate-300">
                    {e.tool}
                  </td>
                  <td className="px-4 py-2.5">
                    <DecisionBadge value={e.decision} />
                  </td>
                  <td className="px-4 py-2.5">
                    <RiskBadge value={e.risk_level} score={e.risk_score} />
                  </td>
                  <td className="px-4 py-2.5">
                    {e.side_effect ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-amber-300">
                        <Activity size={12} /> recorded
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                        <XCircle size={12} /> none
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <EmptyState
              title="No events yet"
              description="Run a scenario in the Scenario Lab to produce live audit events."
            />
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Current incidents"
            subtitle="Dangerous sequences stopped before execution"
            right={
              <Link
                href="/incidents"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-cyan-400 hover:text-cyan-300"
              >
                Investigate <ArrowRight size={13} />
              </Link>
            }
          />
          {incidents && incidents.items.length > 0 ? (
            <ul className="divide-y divide-slate-800/70">
              {incidents.items.map((i) => (
                <li key={i.id}>
                  <Link
                    href={`/incidents/${i.id}`}
                    className="flex items-start gap-3 px-5 py-3.5 transition-colors hover:bg-slate-800/30"
                  >
                    <ShieldAlert
                      size={16}
                      className="mt-0.5 shrink-0 text-rose-400"
                    />
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-slate-200">
                        {i.title}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-slate-500">
                        {i.trigger_policy} · blocked {i.blocked_tool} ·{" "}
                        {formatTs(i.created_at)}
                      </p>
                    </div>
                    <span className="ml-auto shrink-0 text-[10px] font-semibold uppercase text-rose-300">
                      {i.severity}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="No incidents recorded"
              description="Incidents appear when the gateway blocks a dangerous action sequence."
            />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Prevention summary"
            subtitle="Evidence that blocked actions never executed"
          />
          <div className="space-y-3 px-5 py-4 text-xs">
            <div className="flex items-start gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
              <CheckCircle2 size={15} className="mt-0.5 text-emerald-400" />
              <div>
                <p className="font-semibold text-emerald-300">
                  {m.blocked + m.rejected + m.expired} operations stopped before
                  any side effect
                </p>
                <p className="mt-1 text-slate-400">
                  Each blocked attempt keeps an audit record with{" "}
                  <code className="text-slate-300">executed=false</code>.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3">
              <PauseCircle size={15} className="mt-0.5 text-amber-400" />
              <div>
                <p className="font-semibold text-amber-300">
                  {m.approval_required} action(s) paused for human approval
                </p>
                <p className="mt-1 text-slate-400">
                  Pending approvals expire and are single-use; parameters are
                  fingerprint-bound.
                </p>
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-3">
              <p className="text-[11px] uppercase tracking-wider text-slate-500">
                Evaluation snapshot
              </p>
              {m.evaluation.available ? (
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                  <span className="text-slate-400">Detection rate</span>
                  <span className="text-right font-semibold text-emerald-300">
                    {(m.evaluation.detection_rate! * 100).toFixed(1)}%
                  </span>
                  <span className="text-slate-400">False positives</span>
                  <span className="text-right font-semibold text-slate-200">
                    {(m.evaluation.false_positive_rate! * 100).toFixed(1)}%
                  </span>
                  <span className="text-slate-400">Prevention rate</span>
                  <span className="text-right font-semibold text-emerald-300">
                    {(m.evaluation.prevention_rate! * 100).toFixed(1)}%
                  </span>
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-500">
                  No benchmark has run yet — open{" "}
                  <Link href="/evaluation" className="text-cyan-400 underline">
                    Evaluation
                  </Link>{" "}
                  to execute it. No metrics are shown until real test outcomes
                  exist.
                </p>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
