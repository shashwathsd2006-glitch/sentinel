"use client";

import { useState } from "react";
import { CheckCircle2, RefreshCw, ShieldQuestion, XCircle } from "lucide-react";
import {
  apiGet,
  apiPost,
  type ApprovalItem,
  type DecisionResponse,
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
  Table,
  formatTsFull,
} from "@/components/ui";

const ACTORS = ["reviewer-1", "security-officer", "oncall-human"];

export default function ApprovalsPage() {
  const [tab, setTab] = useState<"PENDING" | "all">("PENDING");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<DecisionResponse | null>(null);

  const query = tab === "PENDING" ? "?status=PENDING&limit=50" : "?limit=50";
  const { data, error, loading, refresh } = usePolling<{
    items: ApprovalItem[];
    total: number;
  }>(() => apiGet(`/api/approvals${query}`), {
    intervalMs: 3000,
    refetchKey: tab, // switch tabs -> refetch immediately
  });

  async function decide(approval: ApprovalItem, decision: "approve" | "reject") {
    if (busyId) return; // guard against duplicate submissions
    setBusyId(approval.id);
    setMessage(null);
    setOutcome(null);
    try {
      const res = await apiPost<DecisionResponse>(
        `/api/approvals/${approval.id}/decision`,
        {
          decision,
          actor: ACTORS[0],
          // Bind the decision to the exact pending action.
          fingerprint: decision === "approve" ? approval.fingerprint : null,
        },
      );
      setOutcome(res);
      // Report the ACTUAL execution outcome, not just the decision label.
      if (res.result.executed) {
        setMessage("Approved — the protected action executed exactly once.");
      } else if (decision === "approve") {
        setMessage(
          res.result.error
            ? `Approved, but execution failed: ${res.result.error}`
            : "Approved — the gateway revalidated the action; nothing was executed.",
        );
      } else {
        setMessage("Rejected — the protected tool was never invoked.");
      }
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5 animate-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">
            Human Approval Queue
          </h2>
          <p className="text-xs text-slate-400">
            Pending actions are single-use, expire automatically and are bound to
            the exact parameter fingerprint
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
          {(["PENDING", "all"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1.5 text-[11px] font-semibold transition-colors ${
                tab === t
                  ? "bg-cyan-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t === "PENDING" ? "Pending" : "All history"}
            </button>
          ))}
        </div>
      </div>

      {message ? (
        <div
          className={`rounded-xl border px-4 py-3 text-xs ${
            outcome?.result.decision === "BLOCK" || outcome?.result.decision === "REJECTED"
              ? "border-rose-500/30 bg-rose-950/30 text-rose-200"
              : outcome
                ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-200"
                : "border-amber-500/30 bg-amber-950/30 text-amber-200"
          }`}
        >
          {message}
          {outcome ? (
            <p className="mt-1.5 text-[11px] opacity-80">
              {outcome.result.explanation}
            </p>
          ) : null}
        </div>
      ) : null}

      <Card>
        <CardHeader
          title={tab === "PENDING" ? "Pending actions" : "Approval history"}
          subtitle={`${data ? data.total : 0} record(s)`}
          right={
            <Button variant="outline" onClick={() => void refresh()}>
              <RefreshCw size={13} /> Refresh
            </Button>
          }
        />
        {loading && !data ? (
          <div className="p-6">
            <Spinner label="Loading approvals" />
          </div>
        ) : error && !data ? (
          <div className="p-5">
            <ErrorState message={error} onRetry={() => void refresh()} />
          </div>
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title={tab === "PENDING" ? "Queue is empty" : "No approvals yet"}
            description={
              tab === "PENDING"
                ? "When an agent attempts a protected operation, the gateway pauses it and it appears here for a human decision."
                : "Approve or reject a pending action to build history."
            }
          />
        ) : data ? (
          <Table
            headers={[
              "Requested",
              "Agent / Tool",
              "Operation & parameters",
              "Risk",
              "Status",
              "Decision",
            ]}
          >
            {data.items.map((a) => (
              <tr key={a.id} className="align-top hover:bg-slate-800/30">
                <td className="px-4 py-3 text-[11px] text-slate-400">
                  {formatTsFull(a.requested_at)}
                  <span className="mt-1 block font-mono text-[10px] text-slate-600">
                    {a.id}
                  </span>
                  <span className="block text-[10px] text-slate-600">
                    expires {formatTsFull(a.expires_at)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <p className="text-xs text-slate-300">{a.agent_id}</p>
                  <p className="font-mono text-[11px] text-cyan-300">{a.tool}</p>
                  <p className="mt-1 text-[10px] text-slate-500">
                    {a.resource}
                    {a.destination ? ` → ${a.destination}` : ""}
                  </p>
                </td>
                <td className="max-w-[340px] px-4 py-3">
                  <pre className="overflow-x-auto rounded-md border border-slate-800 bg-slate-950/70 p-2 text-[10px] leading-relaxed text-slate-400">
                    {JSON.stringify(a.params, null, 1)}
                  </pre>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
                    {a.explanation}
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-slate-600">
                    fingerprint {a.fingerprint.slice(0, 24)}…
                  </p>
                  {a.outcome ? (
                    <p className="mt-1.5 rounded border border-slate-800 bg-slate-950/60 p-2 text-[11px] text-slate-300">
                      Outcome: {a.outcome}
                    </p>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <RiskBadge value={a.risk_level} score={a.risk_score} />
                  <div className="mt-2 flex flex-wrap gap-1">
                    {a.policies.map((p) => (
                      <span
                        key={p}
                        className="rounded border border-slate-700 bg-slate-950 px-1 py-0.5 font-mono text-[9px] text-cyan-400"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <StatusPill value={a.status} />
                  {a.decided_at ? (
                    <p className="mt-1 text-[10px] text-slate-500">
                      {a.decided_by} · {formatTsFull(a.decided_at)}
                    </p>
                  ) : null}
                  {a.consumed ? (
                    <p className="text-[10px] text-slate-500">single-use: spent</p>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  {a.status === "PENDING" ? (
                    <div className="flex flex-col gap-2">
                      <Button
                        onClick={() => void decide(a, "approve")}
                        disabled={busyId !== null}
                      >
                        <CheckCircle2 size={13} /> Approve
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => void decide(a, "reject")}
                        disabled={busyId !== null}
                      >
                        <XCircle size={13} /> Reject
                      </Button>
                    </div>
                  ) : (
                    <DecisionBadge
                      value={
                        a.decision === "approved"
                          ? "APPROVED"
                          : a.decision === "rejected"
                            ? "REJECTED"
                            : (a.decision || a.status)
                      }
                    />
                  )}
                </td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>

      <Card>
        <div className="flex items-start gap-3 px-5 py-4 text-xs text-slate-400">
          <ShieldQuestion size={16} className="mt-0.5 shrink-0 text-cyan-400" />
          <p className="leading-relaxed">
            Approving triggers a fresh policy evaluation against the{" "}
            <span className="text-slate-200">current</span> action history before the
            tool runs: if the policy now denies the action, the approval fails and
            nothing executes. Replays, expired approvals and altered parameters are
            rejected with HTTP 409.
          </p>
        </div>
      </Card>
    </div>
  );
}
