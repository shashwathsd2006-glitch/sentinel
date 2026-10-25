/** Shared UI primitives: cards, badges, tables, empty/error states. */

import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm shadow-black/20 ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold tracking-wide text-slate-100">
          {title}
        </h2>
        {subtitle ? (
          <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
        ) : null}
      </div>
      {right}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "neutral" | "good" | "bad" | "warn" | "accent";
}) {
  const tones: Record<string, string> = {
    neutral: "text-slate-100",
    good: "text-emerald-400",
    bad: "text-rose-400",
    warn: "text-amber-400",
    accent: "text-cyan-400",
  };
  return (
    <Card className="p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${tones[tone]}`}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </Card>
  );
}

const DECISION_STYLES: Record<string, string> = {
  ALLOW: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  APPROVED: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  BLOCK: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  REQUIRE_APPROVAL: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  REJECTED: "border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-300",
  EXPIRED: "border-slate-500/30 bg-slate-500/10 text-slate-300",
};

export function DecisionBadge({ value }: { value: string }) {
  const cls =
    DECISION_STYLES[value] ||
    "border-slate-600/40 bg-slate-700/20 text-slate-300";
  const label = value.replace(/_/g, " ");
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold tracking-wide ${cls}`}
    >
      {label}
    </span>
  );
}

const RISK_STYLES: Record<string, string> = {
  low: "text-emerald-400",
  medium: "text-amber-400",
  high: "text-orange-400",
  critical: "text-rose-400",
};

export function RiskBadge({ value, score }: { value: string; score?: number }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${
        RISK_STYLES[value] || "text-slate-300"
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {value}
      {typeof score === "number" ? (
        <span className="tabular-nums text-slate-500">{score.toFixed(0)}</span>
      ) : null}
    </span>
  );
}

export function SeverityBadge({ value }: { value: string }) {
  const cls =
    value === "critical"
      ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
      : value === "high"
        ? "border-orange-500/40 bg-orange-500/10 text-orange-300"
        : "border-amber-500/40 bg-amber-500/10 text-amber-300";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${cls}`}
    >
      {value}
    </span>
  );
}

export function StatusPill({ value }: { value: string }) {
  const map: Record<string, string> = {
    PENDING: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    APPROVED: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    REJECTED: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    EXPIRED: "border-slate-500/40 bg-slate-500/10 text-slate-300",
    FAILED: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    EXECUTION_FAILED: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    completed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    awaiting_approval: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    running: "border-cyan-500/40 bg-cyan-500/10 text-cyan-300",
    executed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
    blocked: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    pending_approval: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    pending: "border-slate-500/40 bg-slate-500/10 text-slate-300",
    rejected: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    expired: "border-slate-500/40 bg-slate-500/10 text-slate-300",
    failed: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    open: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  };
  const cls = map[value] || "border-slate-600/40 bg-slate-700/20 text-slate-300";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${cls}`}
    >
      {value.replace(/_/g, " ")}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled = false,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "danger" | "ghost" | "outline";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const styles: Record<string, string> = {
    primary:
      "bg-cyan-600 hover:bg-cyan-500 text-white border-cyan-500/40 disabled:bg-cyan-900 disabled:text-cyan-500",
    danger:
      "bg-rose-600/90 hover:bg-rose-500 text-white border-rose-500/40 disabled:bg-rose-900 disabled:text-rose-400",
    outline:
      "border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-200 disabled:opacity-50",
    ghost:
      "border-transparent bg-transparent hover:bg-slate-800 text-slate-300 disabled:opacity-50",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60 ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-400">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-600 border-t-cyan-400" />
      {label}…
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-700 bg-slate-800/60 text-slate-400">
        —
      </div>
      <p className="text-sm font-semibold text-slate-200">{title}</p>
      <p className="max-w-md text-xs leading-relaxed text-slate-400">
        {description}
      </p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-950/30 px-5 py-4">
      <p className="text-sm font-semibold text-rose-300">
        Backend connection problem
      </p>
      <p className="mt-1 break-words text-xs text-rose-200/70">{message}</p>
      {onRetry ? (
        <div className="mt-3">
          <Button variant="outline" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function Table({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-500">
            {headers.map((h) => (
              <th key={h} className="px-4 py-3 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/70">{children}</tbody>
      </table>
    </div>
  );
}

export function MeterBar({
  label,
  value,
  total,
  color = "bg-cyan-500",
}: {
  label: string;
  value: number;
  total: number;
  color?: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="tabular-nums text-slate-300">
          {value} ({pct}%)
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function formatTs(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatTsFull(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
