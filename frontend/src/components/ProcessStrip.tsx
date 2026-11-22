"use client";

import Link from "next/link";
import { hadSystem, shortAgent } from "@/lib/agents";
import type { AgentInfo, ProcessStep } from "@/lib/types";
import { cx, Tip } from "./ui";

const CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"];

/** Soony's seven steps, the system each had (or not), and the agent that now sits on it. */
export function ProcessStrip({
  process,
  agents,
  open,
  linkTo = "/team",
  className,
}: {
  process: ProcessStep[];
  agents: AgentInfo[];
  open: Record<number, number>;
  /** Base path for the step links ("" when already on the team page). */
  linkTo?: string;
  className?: string;
}) {
  const nameOf = (id: string) => shortAgent(agents.find((a) => a.id === id)?.name || id);
  return (
    <div className={cx("rounded-xl bg-white ring-1 ring-zinc-200/80 shadow-[0_1px_2px_rgba(24,24,27,0.04)]", className)}>
      <ol className="grid grid-cols-7 divide-x divide-zinc-100">
        {process.map((s) => {
          const had = hadSystem(s);
          const n = open[s.step] || 0;
          const names = s.agents.map(nameOf);
          return (
            <li key={s.step} className="min-w-0">
              <Link
                href={`${linkTo}#step-${s.step}`}
                className="group block h-full px-3.5 py-3 transition hover:bg-zinc-50/80"
                title={`Step ${s.step} · ${s.name}: ${names.join(", ")}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-baseline gap-1.5">
                    <span className="text-[13px] text-zinc-400" aria-hidden>
                      {CIRCLED[s.step - 1] || s.step}
                    </span>
                    <span className="text-[14px] font-semibold text-zinc-900 group-hover:text-soony-blue">{s.name}</span>
                  </span>
                  {n > 0 && (
                    <Tip tip={`${n} open ${n === 1 ? "case" : "cases"} on this step`}>
                      <span className="tnum inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-amber-500 px-1 text-[10.5px] font-semibold text-white">
                        {n}
                      </span>
                    </Tip>
                  )}
                </div>
                <p className="mt-1 truncate text-[12px] text-zinc-500" title={s.system_today}>
                  {s.system_today}
                </p>
                <p className="mt-2 flex items-center gap-1.5">
                  <span
                    className={cx(
                      "inline-flex items-center gap-1 rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide",
                      had ? "text-zinc-500 ring-1 ring-inset ring-zinc-200" : "bg-soony-blue/8 text-soony-blue",
                    )}
                  >
                    {had ? "had a system" : "now an agent"}
                  </span>
                </p>
                <p className="mt-1.5 line-clamp-2 text-[11.5px] leading-snug text-zinc-600" title={names.join(", ")}>
                  {names.join(" · ")}
                </p>
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
