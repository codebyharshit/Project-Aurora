"use client";

import { useState } from "react";
import { orderEditions } from "@/lib/derive";
import { duration, eur, num, pct, shortEdition, when } from "@/lib/format";
import { APPROVE, DECIDE } from "@/lib/people";
import type { CaseSummary, Overview } from "@/lib/types";
import { ESTIMATE_NOTE, humanize } from "./Story";
import { Card, cx, Icon, Tip } from "./ui";

interface Tile {
  id: string;
  label: string;
  now: number;
  after: number;
  within: boolean;
  short: number;
  shortAfter: number;
  tolerance: number;
  collectors: boolean;
}

/** The one card everyone reads first: the verdict and three numbers. */
export function VerdictCard({
  ov,
  cases,
  owners,
  onOpen,
}: {
  ov: Overview;
  cases: CaseSummary[];
  owners: Record<string, string[]>;
  onOpen: (id: string) => void;
}) {
  const g = ov.goal;
  const onTime = g?.status?.on_time_now ?? ov.verdict?.on_time_now ?? true;
  const onTimeAfter = g?.status?.on_time_with_all ?? ov.verdict?.on_time_with_all ?? onTime;
  const text = g?.status?.text ?? ov.verdict?.text ?? "";

  const tiles: Tile[] = g?.status?.products?.length
    ? g.status.products.map((p) => ({
        id: p.product_id,
        label: shortEdition(p.name),
        now: p.launch_pct_now,
        after: p.launch_pct_with_all,
        within: p.within_now,
        short: p.short_now,
        shortAfter: p.short_with_all,
        tolerance: p.tolerance_pct,
        collectors: /collector/i.test(p.name),
      }))
    : orderEditions(ov.editions).map((e) => {
        const v = ov.verdict?.products.find((p) => p.product_id === e.product_id && p.view === "current");
        const va = ov.verdict?.products.find((p) => p.product_id === e.product_id && p.view === "with_all");
        return {
          id: e.product_id,
          label: shortEdition(e.name),
          now: e.day_one_pct.current,
          after: e.day_one_pct.what_if,
          within: v?.within ?? e.remaining - e.current_buildable <= 0,
          short: Math.max(0, e.remaining - e.current_buildable),
          shortAfter: va ? va.short : Math.max(0, e.remaining - e.what_if_buildable),
          tolerance: v?.tolerance_pct ?? 0,
          collectors: /collector/i.test(e.name),
        };
      });
  const ordered = [...tiles].sort((a, b) => Number(b.collectors) - Number(a.collectors));

  // Decisions: waiting · people · € of the recommended options
  const waiting = cases.filter((c) => APPROVE.includes(c.status) || DECIDE.includes(c.status));
  const people = new Set(waiting.flatMap((c) => owners[c.id] || []));
  const cost = waiting.reduce((s, c) => s + (c.why?.cost_eur ?? c.recommendation?.cost_eur ?? 0), 0);
  const d = g?.decisions ?? { waiting: waiting.length, people: people.size, cost_eur: cost };

  // Money: missing copies × what one missing copy costs on launch day (tenant config)
  const value = Object.fromEntries((g?.priorities || []).map((p) => [p.product_id, p.value_per_unit_eur ?? 0]));
  const lossNow = tiles.reduce((s, t) => s + (t.short || 0) * (value[t.id] || 0), 0);
  const lossAfter = tiles.reduce((s, t) => s + (t.shortAfter || 0) * (value[t.id] || 0), 0);
  const priced = (g?.priorities || []).filter((p) => p.value_per_unit_eur);
  const valueNote = priced.map((p) => `${shortEdition(p.name)} €${num(p.value_per_unit_eur!)}`).join(", ");

  return (
    <Card>
      <div className="px-6 pb-5 pt-5">
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-500">
          <Icon name="target" className="h-3.5 w-3.5 text-zinc-400" />
          Will we make {g?.deadline?.name && /sun/i.test(g.deadline.name) ? g.deadline.name : "Sunday 20:00"}?
        </p>
        <p className="mt-2.5 flex items-start gap-3 text-[20px] font-semibold leading-snug tracking-tight text-soony-ink">
          <span
            className={cx(
              "mt-[7px] inline-flex h-3 w-3 shrink-0 items-center justify-center rounded-full",
              onTime ? "bg-emerald-500" : onTimeAfter ? "bg-amber-500" : "bg-red-500",
            )}
            aria-hidden
          />
          <span>
            {text || (onTime ? "Yes, on time." : "Not yet.")}
            {!onTime && onTimeAfter && (
              <span className="mt-0.5 block text-[14px] font-normal text-zinc-500">
                With every approval below: on time.
              </span>
            )}
          </span>
        </p>
      </div>

      <div className="grid grid-cols-3 divide-x divide-zinc-100 border-t border-zinc-100">
        {ordered.map((t) => (
          <PctTile key={t.id} t={t} />
        ))}
        <div className="px-6 py-4">
          <p className="text-[13px] text-zinc-500">If nobody acts</p>
          <p className="tnum mt-1 flex items-baseline gap-1.5 text-[26px] font-semibold leading-none tracking-tight">
            <Tip
              tip={`Copies that miss Sunday × what one missing copy costs on launch day (${valueNote}). ${ESTIMATE_NOTE}`}
            >
              <span className={cx("cursor-help", lossNow > 0 ? "text-red-600" : "text-emerald-700")}>{eur(lossNow)}</span>
            </Tip>
            <span className="text-[13px] font-normal text-zinc-500">lost</span>
          </p>
          <p className="tnum mt-1.5 text-[13px] text-zinc-500">
            <Tip tip={`What it costs to approve all ${num(d.waiting)} fixes below: freight, sorting, local pickup. ${ESTIMATE_NOTE}`}>
              <span className="cursor-help">
                Fixing costs <span className="font-medium text-zinc-800">{eur(d.cost_eur)}</span>
              </span>
            </Tip>
            {lossNow > lossAfter && (
              <>
                <span className="text-zinc-300"> · </span>
                <Tip tip={`Loss drops from ${eur(lossNow)} to ${eur(lossAfter)} if every fix below is approved.`}>
                  <span className="cursor-help text-emerald-700">saves {eur(lossNow - lossAfter)}</span>
                </Tip>
              </>
            )}
          </p>
        </div>
      </div>

      <NextSteps ov={ov} cases={waiting} owners={owners} onOpen={onOpen} />
    </Card>
  );
}

function PctTile({ t }: { t: Tile }) {
  const changes = Math.abs(t.after - t.now) >= 0.05;
  const good = t.short === 0;
  const tone = good ? "text-emerald-700" : t.within ? "text-soony-ink" : "text-red-600";
  const sub = good
    ? "All copies ship Sunday"
    : t.within
      ? `${num(t.short)} follow later · within ${num(t.tolerance)}% tolerance`
      : `${num(t.short)} short`;
  return (
    <div className="px-6 py-4">
      <p className="text-[13px] text-zinc-500">
        {t.label}
        {t.collectors && <span className="ml-1.5 text-[11px] text-zinc-400">priority 1</span>}
      </p>
      <p className="tnum mt-1 flex items-baseline gap-1.5 text-[26px] font-semibold leading-none tracking-tight">
        <Tip tip="Share of all launch copies that can be packed now, counting approved decisions. Source: ERP corrected by the paperwork.">
          <span className={cx("cursor-help", tone)}>{pct(t.now)}</span>
        </Tip>
        {changes && (
          <>
            <Icon name="arrow" className="h-4 w-4 self-center text-zinc-300" />
            <Tip tip="If every decision waiting below is approved. Hypothetical.">
              <span className="cursor-help text-soony-blue">{pct(t.after)}</span>
            </Tip>
          </>
        )}
        <span className="text-[13px] font-normal text-zinc-500">{changes ? "with approvals" : "of launch"}</span>
      </p>
      <p className={cx("tnum mt-1.5 text-[13px]", good ? "text-emerald-700" : t.within ? "text-zinc-500" : "text-red-600")}>
        {sub}
      </p>
    </div>
  );
}

/** What to do next, in plain words: each waiting decision, who signs, and how long it can wait. Most urgent first. */
function NextSteps({
  ov,
  cases,
  owners,
  onOpen,
}: {
  ov: Overview;
  cases: CaseSummary[];
  owners: Record<string, string[]>;
  onOpen: (id: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  if (!cases.length) return null;
  const now = new Date(ov.as_of).getTime();
  // Slack = needed-by minus arrival-if-approved-now. Every hour of waiting eats one hour of slack.
  const rows = cases
    .map((c) => {
      const r = c.recommendation;
      const lum = r?.last_useful_moment ? new Date(r.last_useful_moment).getTime() : NaN;
      const arr = r?.arrival_at ? new Date(r.arrival_at).getTime() : NaN;
      const slack = Number.isFinite(lum) && Number.isFinite(arr) ? lum - arr : null;
      return { c, slack, by: slack != null ? now + slack : null };
    })
    .sort((a, b) => (a.slack ?? Infinity) - (b.slack ?? Infinity));
  // The clock-driven decisions are the next step; the open-ended ones fold into one line until asked for.
  const timed = rows.filter((r) => r.slack != null);
  const rest = rows.filter((r) => r.slack == null);
  const byPerson = Object.entries(
    rest.reduce<Record<string, number>>((m, r) => {
      const who = owners[r.c.id]?.[0] || "Someone";
      m[who] = (m[who] || 0) + 1;
      return m;
    }, {}),
  ).sort((a, b) => b[1] - a[1]);
  const shown = showAll ? rows : timed;

  return (
    <div className="border-t border-zinc-100 px-6 pb-4 pt-4">
      <p className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-semibold text-zinc-900">What to do next</span>
        <span className="text-[12px] text-zinc-400">
          {timed.length ? `${num(timed.length)} against the clock · most urgent first` : `${num(cases.length)} decisions`}
        </span>
      </p>
      <ol className="mt-2 divide-y divide-zinc-100">
        {shown.map(({ c, slack, by }, i) => {
          const who = owners[c.id]?.[0];
          const cost = c.why?.cost_eur ?? c.recommendation?.cost_eur;
          const saves = c.why?.protects_eur;
          const late = slack != null && slack < 0;
          return (
            <li key={c.id}>
              <button
                onClick={() => onOpen(c.id)}
                className="group flex w-full items-start gap-3 py-2.5 text-left transition hover:bg-zinc-50/80"
              >
                <span
                  className={cx(
                    "tnum mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                    i === 0 ? "bg-soony-ink text-white" : "bg-zinc-100 text-zinc-500",
                  )}
                >
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[14px] leading-snug text-zinc-900">
                    {who ? <span className="font-medium">{who}</span> : "Someone"} {DECIDE.includes(c.status) ? "decides" : "approves"}:{" "}
                    {humanize(c.recommendation?.title || c.explanation?.headline || c.title)}
                  </span>
                  <span className="tnum mt-0.5 block text-[12.5px] text-zinc-500">
                    {late ? (
                      <span className="text-red-600">
                        Already {duration(-slack!)} too late, even if approved now. Approve now to keep the damage small.
                      </span>
                    ) : by != null ? (
                      <>
                        <span className={cx(slack! < 6 * 3600 * 1000 ? "text-amber-700" : "text-zinc-700")}>
                          Approve by {when(new Date(by).toISOString())}
                        </span>{" "}
                        ({duration(slack)} left), or the parts arrive after packing needs them.
                      </>
                    ) : (
                      "No fixed deadline; it needs your judgement."
                    )}
                    {cost != null && (
                      <>
                        <span className="text-zinc-300"> · </span>costs {eur(cost)}
                        {saves ? <>, protects up to {eur(saves)}</> : null}
                      </>
                    )}
                  </span>
                </span>
                <span className="mt-0.5 shrink-0 text-[12px] text-zinc-400 group-hover:text-zinc-700">Open →</span>
              </button>
            </li>
          );
        })}
      </ol>
      {rest.length > 0 && (
        <p className="mt-1 flex flex-wrap items-baseline justify-between gap-2 border-t border-zinc-100 pt-2.5 text-[12.5px] text-zinc-500">
          <span>
            {showAll ? "Showing all decisions." : (
              <>
                Plus {num(rest.length)} with no deadline that need a judgement call:{" "}
                {byPerson.map(([who, n]) => `${who} ${n}`).join(", ")}.
              </>
            )}
          </span>
          <button onClick={() => setShowAll((v) => !v)} className="shrink-0 text-zinc-500 hover:text-zinc-900">
            {showAll ? "Show less" : "Show all →"}
          </button>
        </p>
      )}
    </div>
  );
}
