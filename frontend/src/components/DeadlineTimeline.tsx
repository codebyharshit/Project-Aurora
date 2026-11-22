"use client";

import { when } from "@/lib/format";
import { APPROVE } from "@/lib/people";
import type { CaseSummary, Overview } from "@/lib/types";
import { humanize } from "./Story";
import { cx, Tip } from "./ui";

const H = 3600 * 1000;
const BAR = 20; // y of the base line inside the 44px strip

/** Thin bar from now to the deadline: pack shifts shaded, one marker per waiting decision. */
export function DeadlineTimeline({ ov, cases }: { ov: Overview; cases: CaseSummary[] }) {
  const end = new Date(ov.goal?.deadline?.at || ov.deadline).getTime();
  const now = new Date(ov.as_of).getTime();
  if (!Number.isFinite(end) || !Number.isFinite(now) || end <= now) return null;

  // Shifts relative to a 20:00 Sunday deadline: Sat 06–22, Sun 06–20.
  const shifts = [
    { label: "Sat 06–22", start: end - 38 * H, end: end - 22 * H },
    { label: "Sun 06–20", start: end - 14 * H, end },
  ];
  const start = Math.min(now, shifts[0].start);
  const span = end - start;
  const pos = (t: number) => Math.max(0, Math.min(100, ((t - start) / span) * 100));

  const marks = cases
    .filter((c) => APPROVE.includes(c.status) && c.recommendation)
    .flatMap((c) => {
      const r = c.recommendation!;
      const out: { t: number; kind: "needed" | "arrives"; c: CaseSummary }[] = [];
      const lum = r.last_useful_moment ? new Date(r.last_useful_moment).getTime() : NaN;
      const arr = r.arrival_at ? new Date(r.arrival_at).getTime() : NaN;
      if (Number.isFinite(lum)) out.push({ t: lum, kind: "needed", c });
      if (Number.isFinite(arr)) out.push({ t: arr, kind: "arrives", c });
      return out;
    })
    .filter((m) => m.t >= start && m.t <= end + H);

  return (
    <div className="border-t border-zinc-100 px-6 pb-3 pt-3">
      <div className="relative h-11">
        <div className="absolute inset-x-0 h-px bg-zinc-200" style={{ top: BAR }} />

        {shifts.map((s) => (
          <div key={s.label}>
            <div
              className="absolute h-2"
              style={{ left: `${pos(s.start)}%`, width: `${pos(s.end) - pos(s.start)}%`, top: BAR - 4 }}
            >
              <Tip tip={`Pack shift ${s.label} at DC-HAM`} className="h-full w-full">
                <span className="shift-hatch block h-full w-full rounded-sm ring-1 ring-inset ring-soony-blue/15" />
              </Tip>
            </div>
            <span
              className="absolute whitespace-nowrap text-[10px] text-zinc-400"
              style={{ left: `${pos(s.start)}%`, top: BAR + 11 }}
            >
              {s.label}
            </span>
          </div>
        ))}

        <div className="absolute h-[14px] w-px bg-zinc-900" style={{ left: `${pos(now)}%`, top: BAR - 7 }}>
          <span className="absolute -top-[13px] left-1/2 -translate-x-1/2 text-[10px] font-medium text-zinc-700">now</span>
        </div>
        <div className="absolute right-0 h-[14px] w-px bg-soony-red" style={{ top: BAR - 7 }}>
          <span className="absolute -top-[13px] right-0 whitespace-nowrap text-[10px] font-medium text-soony-red">
            trucks {when(ov.deadline)}
          </span>
        </div>

        {marks.map((m, i) => (
          <div key={i} className="absolute" style={{ left: `${pos(m.t)}%`, top: BAR }}>
            <div className="-translate-x-1/2 -translate-y-1/2">
              <Tip
                tip={
                  <>
                    {m.kind === "needed" ? "Needed by" : "Arrives"} {when(new Date(m.t).toISOString())} ·{" "}
                    {humanize(m.c.recommendation?.title || m.c.title)}
                  </>
                }
              >
                <span
                  className={cx(
                    "block cursor-help",
                    m.kind === "needed"
                      ? "h-[10px] w-[2px] rounded bg-amber-500"
                      : "h-[7px] w-[7px] rounded-full bg-soony-blue ring-2 ring-white",
                  )}
                />
              </Tip>
            </div>
          </div>
        ))}
      </div>
      <p className="flex items-center gap-3 text-[10px] text-zinc-400">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-[7px] w-[2px] rounded bg-amber-500" /> needed by
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-[6px] w-[6px] rounded-full bg-soony-blue" /> arrives, if approved
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="shift-hatch inline-block h-[6px] w-[10px] rounded-sm ring-1 ring-inset ring-soony-blue/15" /> pack shift
        </span>
      </p>
    </div>
  );
}
