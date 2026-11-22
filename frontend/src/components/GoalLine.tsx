"use client";

import { fileUrl } from "@/lib/api";
import { agentOf } from "@/lib/agents";
import { resolvePath, prettyName } from "@/lib/evidence";
import { eur, num, shortEdition } from "@/lib/format";
import { chainOf } from "@/lib/people";
import type { CaseSummary } from "@/lib/types";
import { ESTIMATE_NOTE, editionList } from "./Story";
import { cx, Icon, Tip } from "./ui";

interface Piece {
  key: string;
  node: React.ReactNode;
  tip?: React.ReactNode;
  href?: string;
  tone?: "blue" | "zinc" | "amber";
}

/** One quiet line of chips: what the case serves, what it trades, what it costs, which rule, who raised it. */
export function GoalLine({ c, className, compact }: { c: CaseSummary; className?: string; compact?: boolean }) {
  const pieces = goalPieces(c, compact);
  if (!pieces.length) return null;
  return (
    <div className={cx("flex flex-wrap items-center gap-x-1.5 gap-y-1", className)}>
      {pieces.map((p) => {
        const cls = cx(
          "inline-flex max-w-full items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] leading-snug",
          p.tone === "blue"
            ? "bg-soony-blue/8 text-soony-blue"
            : p.tone === "amber"
              ? "bg-amber-50 text-amber-800"
              : "bg-zinc-50 text-zinc-600 ring-1 ring-inset ring-zinc-200/80",
          p.href && "transition hover:ring-zinc-400",
        );
        const inner = p.href ? (
          <a href={p.href} target="_blank" rel="noreferrer" className={cls}>
            {p.node}
          </a>
        ) : (
          <span className={cx(cls, !!p.tip && "cursor-help")}>{p.node}</span>
        );
        return p.tip ? (
          <Tip key={p.key} tip={p.tip}>
            {inner}
          </Tip>
        ) : (
          <span key={p.key}>{inner}</span>
        );
      })}
    </div>
  );
}

function goalPieces(c: CaseSummary, compact?: boolean): Piece[] {
  const why = c.why;
  const b = c.explanation?.benefit;
  const n = c.explanation?.if_not;
  const chain = chainOf(c);
  const first = chain?.approvers?.[0];
  const out: Piece[] = [];

  // ◆ Serves
  const serves = why?.serves?.length ? why.serves : editionList(b?.copies).filter((x) => x.qty > 0).map((x) => ({ name: x.name, copies: x.qty }));
  const trades = why?.trades?.length ? why.trades : editionList(b?.copies).filter((x) => x.qty < 0).map((x) => ({ name: x.name, copies: -x.qty }));
  const goal = why?.goal || (serves[0] ? `${shortEdition(serves[0].name)} ${/collector/i.test(serves[0].name) ? "first" : "second"}` : n ? `Protects ${editionList(n.copies)[0]?.name || "the launch"}` : null);
  if (goal)
    out.push({
      key: "goal",
      tone: "blue",
      node: (
        <>
          <span aria-hidden>◆</span> Serves: {goal}
        </>
      ),
      tip: "Soony’s priority order: Collector’s Edition first, Standard second. From the launch memo.",
    });

  // +serves / −trades
  if (serves.length || trades.length)
    out.push({
      key: "copies",
      node: (
        <span className="tnum">
          {serves.map((s) => `+${num(Math.abs(s.copies))} ${shortEdition(s.name)}`).join(" · ")}
          {serves.length && trades.length ? " / " : ""}
          {trades.map((t) => `−${num(Math.abs(t.copies))} ${shortEdition(t.name)}`).join(" · ")}
        </span>
      ),
      tip: trades.length ? "Shared parts go to the priority edition; the rest wait for later." : "Copies that make Sunday if this is approved.",
    });

  // € cost → protects
  const cost = why?.cost_eur ?? b?.cost_eur;
  const protects = why?.protects_eur ?? b?.eur_protected;
  if (cost != null && protects != null)
    out.push({
      key: "eur",
      node: (
        <span className="tnum">
          {eur(cost)} → protects {eur(protects)}
        </span>
      ),
      tip: ESTIMATE_NOTE,
    });
  else if (why?.if_not?.eur || n?.eur_at_risk)
    out.push({
      key: "risk",
      tone: "amber",
      node: <span className="tnum">{eur(why?.if_not?.eur ?? n?.eur_at_risk)} at risk</span>,
      tip: ESTIMATE_NOTE,
    });

  // Rule
  const rule = why?.rule
    ? { text: why.rule.text, source: why.rule.source, ref: why.rule.ref }
    : first?.reason
      ? { text: first.reason, source: null, ref: first.policy_ref }
      : null;
  if (rule && !compact)
    out.push({
      key: "rule",
      node: (
        <>
          <Icon name="shield" className="h-3 w-3 text-zinc-400" />
          <span className="max-w-[320px] truncate">Rule: {rule.text}</span>
          {rule.source && <span className="text-zinc-400">· {ruleSourceName(rule.source)}</span>}
        </>
      ),
      tip: `${rule.text}${rule.ref ? ` · ${rule.ref}` : ""}${rule.source ? ` · ${prettyName(rule.source)}` : ""}`,
      href: rule.source ? fileUrl(resolvePath(rule.source)) : undefined,
    });

  // Evidence count
  const evidence =
    why?.evidence_count ??
    new Set([...(c.recommendation?.evidence || []), ...(c.explanation?.facts || []).map((f) => f.source)]).size;
  if (evidence > 0)
    out.push({
      key: "ev",
      node: (
        <>
          <Icon name="doc" className="h-3 w-3 text-zinc-400" />
          <span className="tnum">{evidence} evidence</span>
        </>
      ),
      tip: "Documents the agents cite. Open Details to see them.",
    });

  // Agent · step
  const a = agentOf(c);
  if (a)
    out.push({
      key: "agent",
      node: (
        <>
          <Icon name="bolt" className="h-3 w-3 text-zinc-400" />
          {a.name} <span className="text-zinc-400">· step {a.step}</span>
        </>
      ),
      tip: `Raised by the ${a.name} agent on step ${a.step} of Soony’s process.`,
    });

  return out;
}

function ruleSourceName(s: string): string {
  if (/pp-07|policy/i.test(s)) return "Approval policy";
  if (/memo/i.test(s)) return "Launch memo";
  if (/org_chart/i.test(s)) return "Org chart";
  return prettyName(s);
}
