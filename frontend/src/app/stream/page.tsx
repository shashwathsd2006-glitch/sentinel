"use client";

import { Fragment, useState } from "react";
import { Radio } from "lucide-react";
import { apiGet, type EventItem, type EventsResponse } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import {
  Card,
  DecisionBadge,
  EmptyState,
  ErrorState,
  RiskBadge,
  Spinner,
  Table,
  formatTs,
} from "@/components/ui";

const DECISIONS = ["", "ALLOW", "BLOCK", "REQUIRE_APPROVAL", "APPROVED", "REJECTED", "EXPIRED"];
const SCENARIOS = [
  { value: "", label: "All sources" },
  { value: "scenario_a", label: "Scenario A · legitimate" },
  { value: "scenario_b", label: "Scenario B · data exposure" },
  { value: "scenario_c", label: "Scenario C · approval" },
  { value: "benchmark", label: "Evaluation benchmark" },
];
const AGENTS = ["", "report-agent", "support-agent", "ops-agent"];

export default function StreamPage() {
  const [scenario, setScenario] = useState("");
  const [decision, setDecision] = useState("");
  const [agent, setAgent] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const query = new URLSearchParams({ limit: "60" });
  if (scenario) query.set("scenario", scenario);
  if (decision) query.set("decision", decision);
  if (agent) query.set("agent", agent);

  const { data, error, loading, refresh } = usePolling<EventsResponse>(
    () => apiGet<EventsResponse>(`/api/events?${query.toString()}`),
    { intervalMs: 2500 },
  );

  return (
    <div className="space-y-5 animate-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">
            Live Action Stream
          </h2>
          <p className="text-xs text-slate-400">
            Every gateway evaluation with its decision, explanation and side-effect
            evidence · refreshes every 2.5s
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-[11px] text-slate-400">
          <Radio size={13} className="live-dot text-emerald-400" />
          {data ? `${data.total} matching event(s)` : "connecting…"}
        </span>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-800 px-5 py-4">
          <label className="space-y-1 text-[11px] text-slate-400">
            <span className="block uppercase tracking-wider">Scenario</span>
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none focus:border-cyan-500/60"
            >
              {SCENARIOS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-[11px] text-slate-400">
            <span className="block uppercase tracking-wider">Decision</span>
            <select
              value={decision}
              onChange={(e) => setDecision(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none focus:border-cyan-500/60"
            >
              {DECISIONS.map((d) => (
                <option key={d} value={d}>
                  {d ? d.replace("_", " ") : "All decisions"}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-[11px] text-slate-400">
            <span className="block uppercase tracking-wider">Agent</span>
            <select
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none focus:border-cyan-500/60"
            >
              {AGENTS.map((a) => (
                <option key={a} value={a}>
                  {a || "All agents"}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => {
              setScenario("");
              setDecision("");
              setAgent("");
            }}
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 transition-colors hover:bg-slate-800"
          >
            Reset filters
          </button>
        </div>

        {loading && !data ? (
          <div className="p-6">
            <Spinner label="Loading events" />
          </div>
        ) : error && !data ? (
          <div className="p-5">
            <ErrorState message={error} onRetry={() => void refresh()} />
          </div>
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title="No matching events"
            description="No audit events match the selected filters. Run a scenario in the Scenario Lab to generate live traffic."
          />
        ) : data ? (
          <Table
            headers={[
              "Time",
              "Agent",
              "Tool",
              "Resource / Destination",
              "Risk",
              "Decision",
              "Executed",
              "",
            ]}
          >
            {data.items.map((e) => (
              <Fragment key={e.id}>
                <tr
                  className="cursor-pointer transition-colors hover:bg-slate-800/30"
                  onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                >
                  <td className="px-4 py-2.5 tabular-nums text-slate-400">
                    {formatTs(e.ts)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="text-slate-300">{e.agent_id}</span>
                    <span className="ml-2 text-[10px] text-slate-600">
                      {e.scenario_id || "manual"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-slate-200">
                    {e.tool}
                  </td>
                  <td className="max-w-[260px] truncate px-4 py-2.5 text-[11px] text-slate-400">
                    {e.destination ? (
                      <>
                        <span className="text-rose-300">→ {e.destination}</span>
                        <span className="block truncate text-slate-600">
                          {e.resource}
                        </span>
                      </>
                    ) : (
                      e.resource || "—"
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <RiskBadge value={e.risk_level} score={e.risk_score} />
                  </td>
                  <td className="px-4 py-2.5">
                    <DecisionBadge value={e.decision} />
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`text-[11px] ${e.executed ? "text-emerald-400" : "text-slate-500"}`}
                    >
                      {e.executed ? "yes" : "no"}
                      {e.side_effect ? " · side effect" : ""}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-[11px] text-cyan-500">
                    {expanded === e.id ? "hide" : "why?"}
                  </td>
                </tr>
                {expanded === e.id ? (
                  <tr className="bg-slate-950/60">
                    <td colSpan={8} className="px-4 py-4">
                      <EventExplanation event={e} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </Table>
        ) : null}
      </Card>
    </div>
  );
}

function EventExplanation({ event: e }: { event: EventItem }) {
  return (
    <div className="grid gap-4 rounded-lg border border-slate-800 bg-slate-950/70 p-4 text-xs md:grid-cols-3">
      <div className="md:col-span-2">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">
          Decision explanation
        </p>
        <p className="mt-1.5 leading-relaxed text-slate-200">{e.explanation}</p>
        <p className="mt-3 font-mono text-[11px] text-slate-500">
          {e.action_summary}
        </p>
      </div>
      <div className="space-y-2">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">
            Policies applied
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {e.policies.length > 0 ? (
              e.policies.map((p) => (
                <span
                  key={p}
                  className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300"
                >
                  {p}
                </span>
              ))
            ) : (
              <span className="text-[11px] text-slate-500">
                no denying policy (allowed by rule set)
              </span>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <span className="text-slate-500">Session</span>
          <span className="truncate text-right font-mono text-slate-400">
            {e.session_id}
          </span>
          <span className="text-slate-500">Sensitivity</span>
          <span className="text-right text-slate-300">{e.sensitivity || "—"}</span>
          <span className="text-slate-500">Decision latency</span>
          <span className="text-right tabular-nums text-cyan-300">
            {e.latency_ms.toFixed(3)} ms
          </span>
          <span className="text-slate-500">Event ID</span>
          <span className="text-right tabular-nums text-slate-400">#{e.id}</span>
        </div>
      </div>
    </div>
  );
}
