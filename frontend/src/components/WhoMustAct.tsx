"use client";

import { APPROVE, type PersonWork } from "@/lib/people";
import { humanize } from "./Story";
import { Avatar, Card, Chip, cx, Icon, Pulse } from "./ui";

/** Everyone sees who holds the pen: one row per person with something open. Click to see it as them. */
export function WhoMustAct({ work, onPick }: { work: PersonWork[]; onPick: (name: string) => void }) {
  return (
    <Card>
      <div className="flex items-baseline justify-between px-5 pb-2 pt-4">
        <p className="flex items-center gap-2 text-[15px] font-semibold text-zinc-900">
          Who must act
          {work.length > 0 && (
            <span className="tnum text-[13px] font-normal text-zinc-500">
              {work.length} {work.length === 1 ? "person" : "people"}
            </span>
          )}
        </p>
        <span className="text-xs text-zinc-500">Click a name to see their view</span>
      </div>
      {work.length === 0 ? (
        <p className="flex items-center gap-2.5 border-t border-zinc-100 px-5 py-5 text-[14px] text-zinc-600">
          <Pulse tone="green" />
          Nothing needs a person right now. The agents keep reading.
        </p>
      ) : (
        <ul>
          {work.map((w) => {
            const urgent = w.top ? APPROVE.includes(w.top.status) : false;
            const line = w.top ? humanize(w.top.explanation?.headline || w.top.title) : w.topLine;
            return (
              <li key={w.person.name} className="border-t border-zinc-100">
                <button
                  onClick={() => onPick(w.person.name)}
                  className="group flex w-full items-start gap-3 px-5 py-3 text-left transition hover:bg-zinc-50"
                >
                  <Avatar name={w.person.name} size={32} tone="blue" />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="text-[14px] font-medium text-zinc-900">{w.person.name}</span>
                      <span className="truncate text-[12px] text-zinc-600">{w.scope}</span>
                      {w.standIn && (
                        <Chip tone="amber" title="Approves as stand-in for a vacant role" className="!py-0 text-[11px]">
                          stand-in
                        </Chip>
                      )}
                    </span>
                    {line && (
                      <span className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-zinc-600">{line}</span>
                    )}
                  </span>
                  <span className="flex shrink-0 items-center gap-2 pt-0.5">
                    <span
                      className={cx(
                        "tnum inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-full px-1.5 text-[12px] font-semibold",
                        urgent ? "bg-amber-500 text-white" : "bg-zinc-100 text-zinc-700",
                      )}
                      title={`${w.count} open ${w.count === 1 ? "item" : "items"}`}
                    >
                      {w.count}
                    </span>
                    <Icon name="chevron" className="h-4 w-4 text-zinc-300 transition group-hover:text-soony-blue" />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
