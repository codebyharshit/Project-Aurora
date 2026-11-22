"use client";

import { useEffect, useRef, useState } from "react";
import { usePeople } from "@/lib/api";
import { scopeOf } from "@/lib/people";
import { useViewAs } from "@/lib/viewAs";
import { Avatar, cx, Icon } from "./ui";

/** "View as": Everyone, or one person from GET /api/people. Chosen name prefills every form. */
export function ViewAs({ counts }: { counts?: Record<string, number> }) {
  const [who, setWho] = useViewAs();
  const { data: people } = usePeople();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const me = people?.find((p) => p.name === who);
  const openCount = (name: string) => counts?.[name] ?? people?.find((p) => p.name === name)?.open_items ?? 0;

  return (
    <div ref={wrap} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={cx(
          "inline-flex h-8 items-center gap-2 rounded-full bg-white pl-1.5 pr-2.5 text-[13px] ring-1 ring-inset transition",
          open ? "ring-soony-blue/50" : "ring-zinc-200 hover:ring-zinc-300",
        )}
        title="See the launch room as one person"
      >
        {who ? (
          <Avatar name={who} size={20} tone="blue" />
        ) : (
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-zinc-100 text-zinc-600">
            <Icon name="people" className="h-3 w-3" />
          </span>
        )}
        <span className="max-w-[150px] truncate">
          <span className="text-zinc-500">View as </span>
          <span className="font-medium text-zinc-900">{who || "Everyone"}</span>
        </span>
        <Icon name="chevron" className={cx("h-3.5 w-3.5 text-zinc-500 transition", open ? "-rotate-90" : "rotate-90")} />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute right-0 top-full z-50 mt-2 w-[340px] animate-pop overflow-hidden rounded-xl bg-white p-1.5 shadow-[0_12px_40px_-8px_rgba(24,24,27,0.25)] ring-1 ring-zinc-200"
        >
          <Row
            selected={!who}
            onClick={() => {
              setWho(null);
              setOpen(false);
            }}
            left={
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-zinc-100 text-zinc-600">
                <Icon name="people" className="h-3.5 w-3.5" />
              </span>
            }
            title="Everyone"
            sub="The whole launch room"
          />
          <div className="mx-2 my-1 h-px bg-zinc-100" />
          {!people ? (
            <p className="px-3 py-2 text-xs text-zinc-500">Loading people…</p>
          ) : (
            <div className="max-h-[360px] overflow-y-auto">
              {people.map((p) => {
                const n = openCount(p.name);
                return (
                  <Row
                    key={p.name}
                    selected={who === p.name}
                    onClick={() => {
                      setWho(p.name);
                      setOpen(false);
                    }}
                    left={<Avatar name={p.name} size={28} tone={who === p.name ? "blue" : "zinc"} />}
                    title={p.name}
                    sub={scopeOf(p)}
                    right={
                      n > 0 ? (
                        <span className="tnum inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 text-[11px] font-semibold text-white">
                          {n}
                        </span>
                      ) : (
                        <span className="text-[11px] text-zinc-500">—</span>
                      )
                    }
                  />
                );
              })}
            </div>
          )}
          {me?.scope && <p className="px-3 pb-1.5 pt-2 text-[11px] text-zinc-500">{me.scope}</p>}
        </div>
      )}
    </div>
  );
}

function Row({
  selected,
  onClick,
  left,
  title,
  sub,
  right,
}: {
  selected: boolean;
  onClick: () => void;
  left: React.ReactNode;
  title: string;
  sub?: string;
  right?: React.ReactNode;
}) {
  return (
    <button
      role="option"
      aria-selected={selected}
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left transition hover:bg-zinc-50",
        selected && "bg-soony-blue/6",
      )}
    >
      {left}
      <span className="min-w-0 flex-1">
        <span className={cx("block truncate text-[13px]", selected ? "font-semibold text-soony-blue" : "text-zinc-900")}>
          {title}
        </span>
        {sub && <span className="block truncate text-[11px] text-zinc-500">{sub}</span>}
      </span>
      {right}
    </button>
  );
}
