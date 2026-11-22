"use client";

import { orderEditions } from "@/lib/derive";
import { eur, num, pct, shortEdition } from "@/lib/format";
import { APPROVE, DECIDE } from "@/lib/people";
import type { CaseSummary, Overview } from "@/lib/types";
import { ESTIMATE_NOTE } from "./Story";
import { DeadlineTimeline } from "./DeadlineTimeline";
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
}: {
  ov: Overview;
  cases: CaseSummary[];
  owners: Record<string, string[]>;
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
          <p className="text-[13px] text-zinc-500">Decisions</p>
          <p className="tnum mt-1 flex items-baseline gap-1.5 text-[26px] font-semibold leading-none tracking-tight text-soony-ink">
            <Tip tip="Cases waiting for an approval or a decision right now.">
              <span className={cx("cursor-help", d.waiting > 0 && "text-amber-700")}>{num(d.waiting)}</span>
            </Tip>
            <span className="text-[13px] font-normal text-zinc-500">waiting</span>
          </p>
          <p className="tnum mt-1.5 text-[13px] text-zinc-500">
            <Tip tip="People named by the approval policy for these decisions.">
              <span className="cursor-help">{num(d.people)} {d.people === 1 ? "person" : "people"}</span>
            </Tip>
            <span className="text-zinc-300"> · </span>
            <Tip tip={`Sum of the recommended options’ cost. ${ESTIMATE_NOTE}`}>
              <span className="cursor-help">{eur(d.cost_eur)} to commit</span>
            </Tip>
          </p>
        </div>
      </div>

      <DeadlineTimeline ov={ov} cases={cases} />
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
