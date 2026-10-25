"use client";

import { useState } from "react";
import { Beaker, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { apiGet, apiPost, type Metrics } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Spinner,
  StatCard,
  Table,
} from "@/components/ui";

export default function EvaluationPage() {
  const { data: metrics, error, loading, refresh } = usePolling<Metrics>(
    () => apiGet<Metrics>("/api/metrics"),
    { intervalMs: 6000 },
  );
  const [running, setRunning] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function runBenchmark() {
    setRunning(true);
    setActionError(null);
    try {
      await apiPost("/api/evaluation/run");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  if (loading && !metrics) return <Spinner label="Loading evaluation data" />;
  if (error && !metrics)
    return <ErrorState message={error} onRetry={() => void refresh()} />;
  if (!metrics) return null;

  const ev = metrics.evaluation;
  const pct = (v: number | null) =>
    v === null ? "—" : `${(v * 100).toFixed(1)}%`;

  return (
    <div className="space-y-5 animate-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Evaluation</h2>
          <p className="text-xs text-slate-400">
            Metrics computed from recorded gateway test outcomes — never fabricated
          </p>
        </div>
        <Button onClick={() => void runBenchmark()} disabled={running}>
          {running ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Beaker size={13} />
          )}
          {running ? "Running benchmark…" : "Run benchmark suite"}
        </Button>
      </div>

      {actionError ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-xs text-rose-200">
          {actionError}
        </div>
      ) : null}

      {!ev.available ? (
        <Card>
          <EmptyState
            title="No benchmark has run yet"
            description="Detection rate, false-positive rate, prevention rate and decision latency stay hidden until a real benchmark suite executes against the live gateway. Press 'Run benchmark suite' to execute it."
            action={
              <Button onClick={() => void runBenchmark()} disabled={running}>
                {running ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Beaker size={13} />
                )}
                Run benchmark suite
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard
              label="Detection rate"
              value={pct(ev.detection_rate)}
              hint={`${ev.attacks} attack cases`}
              tone={ev.detection_rate === 1 ? "good" : "warn"}
            />
            <StatCard
              label="Prevention rate"
              value={pct(ev.prevention_rate)}
              hint="attacker actions stopped pre-execution"
              tone={ev.prevention_rate === 1 ? "good" : "warn"}
            />
            <StatCard
              label="False-positive rate"
              value={pct(ev.false_positive_rate)}
              hint={`${ev.false_positives} of ${ev.benign} benign cases`}
              tone={ev.false_positive_rate === 0 ? "good" : "bad"}
            />
            <StatCard
              label="Avg decision latency"
              value={`${(ev.decision_latency_avg_ms ?? 0).toFixed(3)} ms`}
              hint={`p95 ${(ev.decision_latency_p95_ms ?? 0).toFixed(3)} ms`}
              tone="accent"
            />
            <StatCard
              label="Avg end-to-end latency"
              value={`${(ev.e2e_latency_avg_ms ?? 0).toFixed(2)} ms`}
              hint={`p95 ${(ev.e2e_latency_p95_ms ?? 0).toFixed(2)} ms`}
              tone="accent"
            />
            <StatCard
              label="Cases passed"
              value={`${ev.passed_cases}/${ev.total_cases}`}
              hint="expected == actual"
              tone={ev.passed_cases === ev.total_cases ? "good" : "bad"}
            />
          </div>

          {ev.notes ? (
            <p className="text-[11px] italic leading-relaxed text-slate-500">
              {ev.notes}
            </p>
          ) : null}

          <Card>
            <CardHeader
              title="Recorded test outcomes"
              subtitle={`Suite ${ev.suite} · stored in the test_results table`}
            />
            <Table
              headers={[
                "Case",
                "Kind",
                "Expected",
                "Actual",
                "Policy",
                "End-to-end",
                "Result",
              ]}
            >
              {(ev.rows || []).map((r) => (
                <tr key={r.case} className="hover:bg-slate-800/30">
                  <td className="px-4 py-2.5 text-xs text-slate-300">{r.case}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                        r.kind === "attack"
                          ? "border-rose-500/40 text-rose-300"
                          : r.kind === "benign"
                            ? "border-emerald-500/40 text-emerald-300"
                            : r.kind === "approval"
                              ? "border-amber-500/40 text-amber-300"
                              : "border-slate-600/60 text-slate-300"
                      }`}
                    >
                      {r.kind}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-slate-400">
                    {r.expected}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-slate-200">
                    {r.actual}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-[11px] text-cyan-300">
                    {r.latency_ms.toFixed(3)} ms
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-[11px] text-slate-400">
                    {(r.e2e_ms ?? 0).toFixed(2)} ms
                  </td>
                  <td className="px-4 py-2.5">
                    {r.passed ? (
                      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-300">
                        <CheckCircle2 size={12} /> pass
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] text-rose-300">
                        <XCircle size={12} /> fail
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      )}

      <Card>
        <CardHeader
          title="Benchmark methodology"
          subtitle="How each metric is derived"
        />
        <div className="grid gap-4 px-5 py-4 text-xs leading-relaxed text-slate-400 md:grid-cols-2">
          <div>
            <p className="font-semibold text-slate-200">Detection rate</p>
            <p className="mt-1">
              Share of attack cases where the gateway returned BLOCK or
              REQUIRE_APPROVAL instead of ALLOW.
            </p>
            <p className="mt-3 font-semibold text-slate-200">Prevention rate</p>
            <p className="mt-1">
              Share of attack cases where the protected tool never executed
              (no side effect recorded in the audit log).
            </p>
          </div>
          <div>
            <p className="font-semibold text-slate-200">False-positive rate</p>
            <p className="mt-1">
              Share of benign cases that were blocked. Benign pauses for approval
              are expected behaviour, not false positives.
            </p>
            <p className="mt-3 font-semibold text-slate-200">Decision latency</p>
            <p className="mt-1">
              Wall-clock time of each policy evaluation inside the gateway
              (<code className="text-slate-300">perf_counter</code>), averaged over all
              recorded cases with a p95 figure.
            </p>
            <p className="mt-3 font-semibold text-slate-200">End-to-end latency</p>
            <p className="mt-1">
              Full case wall time including evaluation, persistence and (where
              applicable) simulated tool execution — reported separately so
              policy cost is never hidden behind I/O.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
