"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { clock, duration, msBetween, num, when, whenLong } from "@/lib/format";
import type { Overview } from "@/lib/types";
import { AuroraMark, SoonyWordmark } from "./Brand";
import { btn, cx, Icon, Spinner, Tip } from "./ui";
import { ViewAs } from "./ViewAs";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/team", label: "AI team" },
  { href: "/setup", label: "Setup" },
];

/** Soony's launch room header: wordmark, nav, countdown, View-as, "powered by Aurora". */
export function Header({ ov, counts }: { ov?: Overview; counts?: Record<string, number> }) {
  const path = usePathname();
  const left = ov ? msBetween(ov.as_of, ov.deadline) : null;
  const urgent = left !== null && left < 6 * 3600 * 1000;

  return (
    <header className="sticky top-0 z-30 border-b border-zinc-200/80 bg-white/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 md:grid md:h-14 md:grid-cols-[1fr_auto_1fr] md:gap-4 md:px-5 md:py-0">
        <Link href="/" className="flex min-w-0 flex-1 items-center gap-3">
          <SoonyWordmark />
          <span className="hidden h-4 w-px bg-zinc-200 lg:block" />
          <span className="hidden truncate text-[13px] text-zinc-600 lg:inline">
            Grand Heist 6 <span className="text-zinc-300">·</span> Launch room
          </span>
        </Link>

        <nav className="order-last flex w-full items-center gap-1 rounded-full bg-zinc-100/80 p-0.5 md:order-none md:w-auto" aria-label="Main">
          {NAV.map((n) => {
            const active = n.href === "/" ? path === "/" || path.startsWith("/cases") : path.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex-1 rounded-full px-3.5 py-1 text-center text-[13px] transition md:flex-none",
                  active ? "bg-white font-medium text-soony-blue shadow-sm ring-1 ring-zinc-200/80" : "text-zinc-600 hover:text-zinc-900",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex shrink-0 items-center justify-end gap-2">
          <div className="flex h-8 items-center gap-1.5 rounded-full bg-white py-1 pl-2.5 pr-3 ring-1 ring-inset ring-zinc-200 sm:gap-2">
            <Icon name="truck" className={cx("h-4 w-4", urgent ? "text-amber-600" : "text-zinc-600")} />
            {ov ? (
              <Tip
                below
                tip={
                  <>
                    Counted from the data clock ({whenLong(ov.as_of)}) to the deadline ({whenLong(ov.deadline)}).
                  </>
                }
              >
                <span className="whitespace-nowrap text-[13px] text-zinc-600">
                  <span className="hidden sm:inline">Trucks leave in </span>
                  <span className={cx("tnum font-semibold", urgent ? "text-amber-700" : "text-zinc-900")}>
                    {duration(left)}
                  </span>
                  <span className="hidden text-zinc-500 xl:inline"> · {when(ov.deadline)}</span>
                </span>
              </Tip>
            ) : (
              <span className="text-[13px] text-zinc-500">Loading deadline…</span>
            )}
          </div>
          <ViewAs counts={counts} />
          <span className="ml-1 hidden lg:inline-flex">
            <AuroraMark />
          </span>
        </div>
      </div>
    </header>
  );
}

/** Quiet line under the header, Home only: freshness and the manual check. */
export function StatusRow({ ov }: { ov?: Overview }) {
  if (!ov) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500">
      <Tip
        below
        tip={
          ov.last_run ? (
            <>
              Agents last ran at {clock(ov.last_run.finished)} ({ov.last_run.reason}): {ov.last_run.report?.signals ?? 0}{" "}
              findings, {ov.last_run.report?.cases_new ?? 0} new cases.
            </>
          ) : (
            "Agents haven’t run yet"
          )
        }
      >
        <span className="tnum inline-flex items-center gap-1.5">
          <Icon name="clock" className="h-3.5 w-3.5 text-zinc-300" />
          Data as of {when(ov.as_of)}
        </span>
      </Tip>
      <Tip below tip="Delivery notes, order confirmations, supplier notices, memos and ERP tables read by the agents.">
        <span className="tnum inline-flex items-center gap-1.5">
          <Icon name="doc" className="h-3.5 w-3.5 text-zinc-300" />
          {num(ov.documents_read)} documents read
        </span>
      </Tip>
      <PollButton />
    </div>
  );
}

function PollButton() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const { mutate } = useSWRConfig();

  async function poll() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.poll();
      const added = r.drop?.added?.length || 0;
      const changed = r.drop?.changed?.length || 0;
      const replies = Array.isArray(r.replies) ? r.replies.length : 0;
      const parts: string[] = [];
      if (added + changed) parts.push(`${added + changed} new file${added + changed === 1 ? "" : "s"}`);
      if (replies) parts.push(`${replies} supplier repl${replies === 1 ? "y" : "ies"}`);
      setMsg(parts.length ? parts.join(" · ") : "Nothing new");
      mutate("/api/overview");
      mutate("/api/cases");
      mutate("/api/people");
    } catch {
      setMsg("Couldn’t reach the agents");
    } finally {
      setBusy(false);
      setTimeout(() => setMsg(null), 5000);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button className={cx(btn.quiet, "-my-0.5 text-xs")} onClick={poll} disabled={busy} title="Look for new files and supplier replies">
        {busy ? <Spinner /> : <Icon name="refresh" className="h-3.5 w-3.5" />}
        <span className="text-xs">{busy ? "Checking…" : "Check for updates"}</span>
      </button>
      {msg && <span className="animate-fade text-xs text-zinc-600">{msg}</span>}
    </span>
  );
}
