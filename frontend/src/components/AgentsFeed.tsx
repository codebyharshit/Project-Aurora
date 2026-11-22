"use client";

import Link from "next/link";
import { activityOf, stepsOf } from "@/lib/agents";
import { when } from "@/lib/format";
import type { AgentInfo } from "@/lib/types";
import { Card, cx, Icon, type IconName, Pulse } from "./ui";

export const AGENT_ICON: Record<string, IconName> = {
  intake: "chart",
  watcher: "search",
  mapper: "chart",
  reader: "doc",
  remarks: "doc",
  order_confirmation: "check",
  detectors: "search",
  stock_truth: "search",
  release_gate: "shield",
  tracking: "truck",
  tracker: "truck",
  launch_planner: "chart",
  planner: "chart",
  sourcing: "spark",
  planb: "spark",
  approvals: "shield",
  policy: "shield",
  chaser: "mail",
  comms: "mail",
  negotiator: "spark",
  triage: "spark",
  investigator: "search",
  decision_copilot: "spark",
  onboarding: "person",
  notify: "mail",
};

/** What the AI team has been doing, five agents, most active first. */
export function AgentsFeed({ agents, max = 5 }: { agents: AgentInfo[]; max?: number }) {
  const ranked = [...agents]
    .map((a) => ({ a, act: activityOf(a) }))
    .sort((x, y) => y.act.count - x.act.count || (y.act.last || "").localeCompare(x.act.last || ""))
    .slice(0, max);
  return (
    <Card>
      <div className="flex items-baseline justify-between px-5 pb-2 pt-4">
        <p className="flex items-center gap-2 text-[15px] font-semibold text-zinc-900">
          <Pulse />
          Agents at work
        </p>
        <Link href="/team" className="text-xs text-zinc-600 underline-offset-2 hover:text-soony-blue hover:underline">
          See the AI team →
        </Link>
      </div>
      <ul>
        {ranked.map(({ a, act }) => {
          const steps = stepsOf(a);
          const label =
            act.label ||
            (act.count > 0
              ? `${act.count} ${act.count === 1 ? "action" : "actions"}${act.last ? ` · last ${when(act.last)}` : ""}`
              : a.task);
          return (
            <li key={a.id} className="flex items-start gap-3 border-t border-zinc-100 px-5 py-2.5">
              <span
                className={cx(
                  "mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                  act.count > 0 ? "bg-soony-blue/8 text-soony-blue" : "bg-zinc-100 text-zinc-500",
                )}
              >
                <Icon name={AGENT_ICON[a.id] || "bolt"} className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="text-[14px] font-medium text-zinc-900">{a.name}</span>
                  {steps.length > 0 && (
                    <span className="text-[11px] text-zinc-500">step {steps.join(", ")}</span>
                  )}
                </span>
                <span className="mt-0.5 line-clamp-1 block text-[13px] text-zinc-600">{label}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
