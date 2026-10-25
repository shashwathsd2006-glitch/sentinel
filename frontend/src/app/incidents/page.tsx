"use client";

import Link from "next/link";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { apiGet, type IncidentItem } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  Card,
  EmptyState,
  ErrorState,
  SeverityBadge,
  Spinner,
  StatusPill,
  formatTsFull,
} from "@/components/ui";

export default function IncidentsPage() {
  const { data, error, loading, refresh } = usePolling<{
    items: IncidentItem[];
    total: number;
  }>(() => apiGet("/api/incidents?limit=50"), { intervalMs: 5000 });

  return (
    <div className="space-y-5 animate-in">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">
          Incident Investigation
        </h2>
        <p className="text-xs text-slate-400">
          Detected attack sequences with ordered timelines and pre-execution
          evidence
        </p>
      </div>

      {loading && !data ? (
        <Spinner label="Loading incidents" />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={() => void refresh()} />
      ) : data && data.items.length === 0 ? (
        <Card>
          <EmptyState
            title="No incidents recorded yet"
            description="An incident is created whenever the gateway blocks a dangerous multi-step sequence. Run Scenario B in the Scenario Lab."
            action={
              <Link
                href="/scenarios"
                className="text-xs font-medium text-cyan-400 underline"
              >
                Open Scenario Lab
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data?.items.map((i) => (
            <Link key={i.id} href={`/incidents/${i.id}`}>
              <Card className="h-full p-5 transition-colors hover:border-slate-700">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-400">
                      <ShieldAlert size={16} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-100">
                        {i.title}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {formatTsFull(i.created_at)}
                      </p>
                    </div>
                  </div>
                  <SeverityBadge value={i.severity} />
                </div>

                <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-slate-400">
                  {i.explanation}
                </p>

                <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-cyan-300">
                    {i.trigger_policy}
                  </span>
                  <span className="text-slate-500">
                    blocked <span className="font-mono text-rose-300">{i.blocked_tool}</span>
                  </span>
                  <span className="ml-auto flex items-center gap-1 text-emerald-400">
                    <ShieldCheck size={12} /> tool did not execute
                  </span>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3">
                  <StatusPill value={i.status} />
                  <span className="text-[11px] text-cyan-500">
                    Investigate →
                  </span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
