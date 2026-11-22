"use client";

import { useState } from "react";
import { useOverview } from "@/lib/api";
import { eur, num, shortEdition, when } from "@/lib/format";
import type { Investigation as Inv } from "@/lib/types";
import { SourceChip } from "./Story";
import { cx, Icon, type IconName } from "./ui";

export function DeadlineBadge({ affects, className }: { affects: boolean; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        affects ? "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200" : "bg-zinc-100 text-zinc-600",
        className,
      )}
    >
      <span className={cx("h-1.5 w-1.5 rounded-full", affects ? "bg-amber-500" : "bg-zinc-400")} />
      {affects ? "Affects Sunday" : "Doesn’t affect Sunday"}
    </span>
  );
}

/** "The Investigator looked into this": the agent's brief for a new kind of problem. */
export function InvestigationBrief({ inv }: { inv: Inv }) {
  const evidence = (inv.evidence || []).map(splitEvidence);
  return (
    <div className="mx-6 mt-6">
      <p className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-zinc-500">
        <Icon name="search" className="h-3.5 w-3.5 text-zinc-400" />
        The Investigator looked into this
        {inv.confidence != null && (
          <span className="font-normal normal-case tracking-normal text-zinc-400">
            · {Math.round(inv.confidence * 100)}% confident
          </span>
        )}
      </p>
      <p className="mt-3 text-[15px] leading-relaxed text-zinc-800">{inv.summary.replace(/^C-\d{3,}\b/, "This")}</p>

      <div className="mt-4 rounded-lg bg-zinc-50 p-4 ring-1 ring-inset ring-zinc-200">
        <div className="flex flex-wrap items-center gap-2">
          <DeadlineBadge affects={inv.affects_deadline} />
          {inv.affects_deadline && !!inv.impact?.copies_at_risk && (
            <span className="tnum text-[13px] font-medium text-red-600">{num(inv.impact.copies_at_risk)} copies at risk</span>
          )}
        </div>
        {inv.impact?.explanation && <p className="mt-2 text-[13px] leading-relaxed text-zinc-600">{inv.impact.explanation}</p>}
      </div>

      {inv.root_cause && (
        <div className="mt-5">
          <p className="text-xs text-zinc-400">Root cause</p>
          <p className="mt-1 text-[14px] leading-relaxed text-zinc-700">{inv.root_cause}</p>
        </div>
      )}

      {inv.recommendation && (
        <div className="mt-5 rounded-lg border-l-2 border-zinc-900 bg-white py-1 pl-4">
          <p className="text-xs font-medium text-zinc-900">Investigator recommends</p>
          <p className="mt-1 text-[14px] leading-relaxed text-zinc-800">{inv.recommendation}</p>
        </div>
      )}

      {(inv.options?.length ?? 0) > 0 && (
        <div className="mt-5">
          <p className="text-xs text-zinc-400">Options it found</p>
          <ul className="mt-2 grid gap-2.5 sm:grid-cols-2">
            {inv.options!.map((o, i) => (
              <li key={i} className="rounded-lg p-3.5 ring-1 ring-inset ring-zinc-200">
                <p className="text-[14px] font-medium leading-snug text-zinc-900">{o.title}</p>
                <p className="mt-1.5 text-[13px] leading-snug text-zinc-600">{o.effect}</p>
                <dl className="mt-2.5 space-y-1 text-xs text-zinc-500">
                  <div className="flex gap-1.5">
                    <Icon name="person" className="h-3.5 w-3.5 text-zinc-400" />
                    {o.who_approves || "No approval needed"}
                  </div>
                  <div className="tnum flex gap-1.5">
                    <Icon name="chart" className="h-3.5 w-3.5 text-zinc-400" />
                    {o.cost_estimate_eur ? `about ${eur(o.cost_estimate_eur)}` : o.cost_estimate_eur === 0 ? "No cost" : "Cost unknown"}
                  </div>
                  {o.timing && (
                    <div className="flex gap-1.5">
                      <Icon name="clock" className="h-3.5 w-3.5 text-zinc-400" />
                      {o.timing}
                    </div>
                  )}
                </dl>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(inv.questions_for_human?.length ?? 0) > 0 && (
        <div className="mt-5 rounded-lg bg-amber-50/60 p-4 ring-1 ring-inset ring-amber-200/80">
          <p className="text-[13px] font-medium text-amber-900">Questions for you</p>
          <ul className="mt-2 space-y-1.5">
            {inv.questions_for_human!.map((q, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-snug text-zinc-700">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {evidence.length > 0 && (
        <div className="mt-5">
          <p className="text-xs text-zinc-400">What it based this on</p>
          <ul className="mt-2 space-y-2">
            {evidence.map((e, i) => (
              <li key={i} className="text-[13px] leading-snug text-zinc-600">
                {e.path && <SourceChip source={e.path} className="mr-2" />}
                {e.text}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(inv.trace?.length ?? 0) > 0 && <Trace trace={inv.trace!} />}
    </div>
  );
}

/** "soony/context/x.md: text" → {path, text}; plain statements stay text. */
function splitEvidence(s: string): { path?: string; text: string } {
  const m = s.match(/^([\w./-]+\.(?:md|pdf|csv|docx|json|jpe?g|png|xlsx|txt))(?::\s*(.*))?$/i);
  if (m) return { path: m[1], text: m[2] || "" };
  return { text: s };
}

/* ───────── How the agent investigated ───────── */

const TOOL: Record<string, { verb: string; icon: IconName }> = {
  get_plan_overview: { verb: "Checked the launch plan", icon: "chart" },
  query_part: { verb: "Looked up part", icon: "search" },
  query_supplier: { verb: "Looked up supplier", icon: "person" },
  search_documents: { verb: "Searched documents for", icon: "search" },
  read_document: { verb: "Read", icon: "doc" },
  what_if: { verb: "Ran what-if:", icon: "spark" },
  get_approver: { verb: "Checked who approves", icon: "shield" },
  list_open_cases: { verb: "Checked open cases", icon: "check" },
  submit: { verb: "Wrote the brief", icon: "check" },
};

const KIND_WORD: Record<string, string> = {
  ask_supplier: "a supplier question",
  dock_slot: "a dock slot",
  purchase: "a purchase",
  internal_instruction: "an internal instruction",
  monitor: "monitoring",
  concession: "a concession",
};

function Trace({ trace }: { trace: NonNullable<Inv["trace"]> }) {
  const [open, setOpen] = useState(false);
  const { data: ov } = useOverview();
  const parts = ov?.part_names || {};
  const editions: Record<string, string> = {};
  for (const e of ov?.editions || []) editions[e.product_id] = shortEdition(e.name);
  const steps = trace.filter((t) => t.tool !== "submit");

  return (
    <div className="mt-5 border-t border-zinc-100 pt-3">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-900">
        <Icon name="chevron" className={cx("h-3.5 w-3.5 transition", open && "rotate-90")} />
        How the agent investigated ({steps.length} steps)
      </button>
      {open && (
        <ol className="relative mt-3 animate-fade space-y-2 before:absolute before:bottom-1 before:left-[9px] before:top-1 before:w-px before:bg-zinc-200">
          {steps.map((t, i) => {
            const meta = TOOL[t.tool] || { verb: t.tool.replace(/_/g, " "), icon: "bolt" as IconName };
            return (
              <li key={i} className="relative flex items-start gap-2.5">
                <span className="relative z-10 mt-px inline-flex h-[19px] w-[19px] shrink-0 items-center justify-center rounded-full bg-white text-zinc-400 ring-1 ring-zinc-200">
                  <Icon name={meta.icon} className="h-3 w-3" />
                </span>
                <span className="text-[13px] leading-snug text-zinc-700">{describe(t, meta.verb, parts, editions)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

function describe(
  t: NonNullable<Inv["trace"]>[number],
  verb: string,
  parts: Record<string, string>,
  editions: Record<string, string>,
): string {
  const a = t.args || {};
  const prev = t.result_preview || "";
  const name = prev.match(/"name":\s*"([^"]+)"/)?.[1];
  switch (t.tool) {
    case "query_part": {
      const id = str(a.part);
      return `${verb} ${parts[id] || name || id}`;
    }
    case "query_supplier":
      return `${verb} ${name || str(a.supplier)}`;
    case "search_documents":
      return `${verb} “${str(a.query)}”`;
    case "read_document": {
      const src = str(a.source);
      const file = src.split("/").pop()?.replace(/_/g, " ") || src;
      const type = prev.match(/"doc_type":\s*"([^"]+)"/)?.[1]?.replace(/_/g, " ");
      return `${verb} ${type ? `${type} ` : ""}${file}`;
    }
    case "what_if": {
      const id = str(a.part);
      const q = Number(a.qty_change);
      const qty = Number.isFinite(q) ? `${q >= 0 ? "+" : ""}${num(q)}` : str(a.qty_change);
      const at = a.available_at ? ` from ${when(str(a.available_at))}` : "";
      const changes = [...prev.matchAll(/"product_id":\s*"([^"]+)",\s*"before":\s*(\d+),\s*"after":\s*(\d+)/g)]
        .map(([, p, b, af]) => ({ p: editions[p] || p, b: +b, af: +af }));
      const moved = changes.filter((c) => c.b !== c.af);
      const outcome = changes.length
        ? moved.length
          ? moved.map((c) => `${c.p} ${num(c.b)} → ${num(c.af)}`).join(", ")
          : "launch unchanged"
        : "";
      return `${verb} ${qty} ${parts[id] || id}${at}${outcome ? ` → ${outcome}` : ""}`;
    }
    case "get_approver": {
      const kind = KIND_WORD[str(a.action_kind)] || str(a.action_kind).replace(/_/g, " ");
      const v = Number(a.value_eur);
      const person = prev.match(/"person":\s*"([^"]+)"/)?.[1] || prev.match(/"role":\s*"([^"]+)"/)?.[1];
      return `${verb} ${kind}${v ? ` of ${eur(v)}` : ""}${person ? ` → ${person}` : ""}`;
    }
    default:
      return verb;
  }
}
