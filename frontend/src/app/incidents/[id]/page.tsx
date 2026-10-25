"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Ban,
  ChevronRight,
  FileWarning,
  ShieldCheck,
} from "lucide-react";
import { apiGet, type IncidentDetail } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  Card,
  CardHeader,
  DecisionBadge,
  ErrorState,
  RiskBadge,
  SeverityBadge,
  Spinner,
  StatusPill,
  formatTsFull,
} from "@/components/ui";

const ESCALATION: Record<string, string> = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-orange-500",
  critical: "bg-rose-500",
};

export default function IncidentDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6">
          <Spinner label="Loading incident" />
        </div>
      }
    >
      <IncidentDetailContent />
    </Suspense>
  );
}

function IncidentDetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data, error, loading, refresh } = usePolling<IncidentDetail>(
    () => apiGet<IncidentDetail>(`/api/incidents/${id}`),
    { intervalMs: 5000 },
  );

  if (loading && !data) return <Spinner label="Loading incident" />;
  if (error && !data)
    return <ErrorState message={error} onRetry={() => void refresh()} />;
  if (!data) return null;

  const { incident, timeline, steps, run } = data;
  const maxRisk = Math.max(...timeline.map((t) => t.risk_score), 0);

  return (
    <div className="space-y-5 animate-in">
      <Link
        href="/incidents"
        className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200"
      >
        <ArrowLeft size={13} /> Back to incidents
      </Link>

      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-400">
              <FileWarning size={19} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-100">
                {incident.title}
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                {formatTsFull(incident.created_at)} · session{" "}
                <span className="font-mono text-slate-500">
                  {incident.session_id}
                </span>{" "}
                · {incident.scenario_id}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <SeverityBadge value={incident.severity} />
                <StatusPill value={incident.status} />
                {run ? <StatusPill value={run.status} /> : null}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2.5 text-xs font-semibold text-emerald-300">
            <ShieldCheck size={15} />
            Protected tool executed:{" "}
            {incident.protected_tool_executed ? "YES" : "NO"}
          </div>
        </div>

        <div className="mt-5 grid gap-4 border-t border-slate-800 pt-4 md:grid-cols-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Triggered policy
            </p>
            <p className="mt-1 font-mono text-sm text-cyan-300">
              {incident.trigger_policy}
            </p>
            <p className="mt-1 text-xs font-medium text-slate-300">
              {incident.trigger_policy_name}
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
              {incident.trigger_policy_description}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Blocked operation
            </p>
            <p className="mt-1 font-mono text-sm text-rose-300">
              {incident.blocked_tool}
            </p>
            <p className="mt-1 break-all text-[11px] text-slate-400">
              resource: {incident.blocked_resource || "—"}
            </p>
            <p className="break-all text-[11px] text-slate-400">
              destination: {incident.destination || "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-500">
              Run
            </p>
            {run ? (
              <>
                <Link
                  href="/scenarios"
                  className="font-mono text-xs text-cyan-400 underline"
                >
                  {run.id}
                </Link>
                <p className="mt-1 text-[11px] text-slate-400">
                  {run.allowed_count} allowed · {run.blocked_count} blocked ·{" "}
                  {run.approval_count} approval
                </p>
              </>
            ) : (
              <p className="text-xs text-slate-500">manual gateway action</p>
            )}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Risk escalation across the session"
          subtitle="Each evaluated action's cumulative risk score in chronological order"
        />
        <div className="space-y-2 px-5 py-4">
          {timeline.map((t) => {
            const pct = maxRisk > 0 ? Math.round((t.risk_score / maxRisk) * 100) : 0;
            return (
              <div key={t.id} className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-400">
                    <span className="mr-2 text-slate-600">#{t.index}</span>
                    {t.tool}
                  </span>
                  <span className="flex items-center gap-2">
                    <RiskBadge value={t.risk_level} score={t.risk_score} />
                    <DecisionBadge value={t.decision} />
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${ESCALATION[t.risk_level] || "bg-slate-500"}`}
                    style={{ width: `${Math.max(pct, 3)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Ordered action timeline"
            subtitle="Full audit evidence for this session"
          />
          <ol className="divide-y divide-slate-800/70">
            {timeline.map((t) => (
              <li key={t.id} className="px-5 py-3.5">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-[10px] text-slate-400">
                      {t.index}
                    </span>
                    <span className="font-mono text-slate-200">{t.tool}</span>
                    <ChevronRight size={12} className="text-slate-600" />
                    <DecisionBadge value={t.decision} />
                  </div>
                  <span
                    className={`text-[11px] ${t.executed ? "text-emerald-400" : "text-slate-500"}`}
                  >
                    {t.executed ? "executed" : "not executed"}
                    {t.side_effect ? " · side effect" : ""}
                  </span>
                </div>
                <p className="mt-1.5 pl-7 text-[11px] leading-relaxed text-slate-400">
                  {t.explanation}
                </p>
                <p className="mt-1 pl-7 font-mono text-[10px] text-slate-600">
                  {t.action_summary}
                </p>
              </li>
            ))}
          </ol>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Attack sequence explanation"
              subtitle="How individually permitted steps combined into a threat"
            />
            <div className="whitespace-pre-wrap px-5 py-4 text-xs leading-relaxed text-slate-300">
              {data.attack_explanation}
            </div>
            <div className="border-t border-slate-800 px-5 py-4">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                Sequence summary
              </p>
              <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-rose-300">
                {incident.sequence_summary}
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader title="Scenario step outcomes" />
            <ol className="divide-y divide-slate-800/70">
              {steps.map((s) => (
                <li key={s.step_index} className="flex items-center gap-3 px-5 py-3">
                  <span className="text-[11px] text-slate-500">
                    {s.step_index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-slate-200">{s.label}</p>
                    <p className="truncate font-mono text-[10px] text-slate-500">
                      {s.tool}
                    </p>
                  </div>
                  {s.decision === "BLOCK" ? (
                    <Ban size={14} className="shrink-0 text-rose-400" />
                  ) : null}
                  <DecisionBadge value={s.decision || "—"} />
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}
