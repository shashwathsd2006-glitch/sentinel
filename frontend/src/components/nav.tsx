"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FlaskConical,
  LayoutDashboard,
  Radio,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
} from "lucide-react";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/stream", label: "Live Action Stream", icon: Radio },
  { href: "/incidents", label: "Incidents", icon: ShieldAlert },
  { href: "/approvals", label: "Approval Queue", icon: UserCheck },
  { href: "/scenarios", label: "Scenario Lab", icon: FlaskConical },
  { href: "/evaluation", label: "Evaluation", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-slate-800 bg-slate-950/90 backdrop-blur md:flex">
      <div className="flex items-center gap-2.5 border-b border-slate-800 px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/10 text-cyan-400">
          <ShieldCheck size={18} />
        </div>
        <div>
          <p className="text-sm font-bold tracking-widest text-slate-100">
            SENTINEL-X
          </p>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">
            Agent Runtime Gateway
          </p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1 p-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium transition-colors ${
                active
                  ? "border border-cyan-500/30 bg-cyan-500/10 text-cyan-300"
                  : "border border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-200"
              }`}
            >
              <Icon size={15} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-slate-800 px-5 py-4 text-[10px] leading-relaxed text-slate-500">
        DEVHOST 2026 · PS 2.1
        <br />
        AI Agent Safety &amp; Control
        <br />
        <span className="text-emerald-500/80">Fail-closed enforcement</span>
      </div>
    </aside>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const current =
    NAV.find((n) =>
      n.href === "/" ? pathname === "/" : pathname.startsWith(n.href),
    )?.label || "SENTINEL-X";
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/85 px-4 py-3 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-md border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 md:hidden">
          <ShieldCheck size={15} />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-slate-100">{current}</h1>
          <p className="hidden text-[11px] text-slate-500 sm:block">
            Runtime security gateway for autonomous AI agents
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="live-dot h-2 w-2 rounded-full bg-emerald-400" />
        <span className="text-[11px] font-medium text-slate-400">
          Gateway online
        </span>
      </div>
    </header>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-slate-800 bg-slate-950/95 px-1 py-1.5 backdrop-blur md:hidden">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`flex flex-col items-center gap-0.5 rounded px-2 py-1.5 text-[9px] font-medium ${
              active ? "text-cyan-300" : "text-slate-500"
            }`}
            title={label}
          >
            <Icon size={16} />
            {label.split(" ")[0]}
          </Link>
        );
      })}
    </nav>
  );
}
