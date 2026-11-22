"use client";

import { useState } from "react";
import { useCase } from "@/lib/api";
import { num, when } from "@/lib/format";
import type { CaseSummary } from "@/lib/types";
import { humanize } from "./Story";
import { Card, cx, Icon, Pulse } from "./ui";

export function ListHead({ title, sub, count }: { title: string; sub: string; count?: number }) {
  return (
    <div className="px-5 pb-3 pt-4">
      <p className="flex items-center gap-2 text-[15px] font-semibold text-zinc-900">
        {title}
        {count !== undefined && <span className="tnum text-[13px] font-normal text-zinc-400">{count}</span>}
      </p>
      <p className="mt-0.5 text-[13px] text-zinc-500">{sub}</p>
    </div>
  );
}

export function Collapsible({
  title,
  count,
  sub,
  children,
}: {
  title: string;
  count?: number;
  sub: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 text-left" aria-expanded={open}>
        <div className="flex-1">
          <ListHead title={title} sub={sub} count={count} />
        </div>
        <Icon name="chevron" className={cx("mr-5 h-4 w-4 text-zinc-400 transition", open && "rotate-90")} />
      </button>
      {open && <div className="animate-fade">{children}</div>}
    </Card>
  );
}

const PHRASE: Record<string, string> = {
  AGREED: "Agreed with the supplier · waiting for the waybill",
  IN_TRANSIT: "On the way",
  DELIVERED: "Delivered",
  AWAITING_SUPPLIER: "Waiting for the supplier’s reply",
  EXECUTING: "Agents are carrying it out",
  VERIFIED: "Done and confirmed",
  DECIDED: "Decided; agents follow your decision",
  ESCALATED: "No reply; escalated to you",
};

/** One in-flight case, told in words from its latest events. */
export function FlightRow({ c, onOpen }: { c: CaseSummary; onOpen: (id: string) => void }) {
  const { data } = useCase(c.id);
  const approvedBy = data?.events
    .map((e) => e.text.match(/^(?:Approved|Decision) by ([^:]+):/)?.[1])
    .filter(Boolean)
    .pop();
  const counterpart = data?.messages.find((m) => m.direction !== "in")?.counterpart;
  const reminded = data?.events.some((e) => /follow.?up|reminder/i.test(e.text));
  const replied = data?.messages.some((m) => m.direction === "in");
  const last = data?.events[data.events.length - 1];
  const t = data?.data.tracking;
  const supplier =
    data?.events
      .map((e) => e.text.match(/(?:Waiting for|Email sent to) ([^(<:·]+?)(?:\s*\(|\s*<|$)/)?.[1])
      .find((x) => x && !x.includes("@")) || t?.supplier_id || "the supplier";
  const eta = t?.expected_arrival ? ` · expected ${when(t.expected_arrival)}` : "";

  let line = PHRASE[c.status] || "In progress";
  if (c.status === "AWAITING_SUPPLIER" && counterpart) line = `Waiting for a reply from ${counterpart}`;
  if (reminded && c.status === "AWAITING_SUPPLIER") line += " · reminder sent";
  if (replied && c.status === "VERIFIED") line = "Supplier confirmed · counted in the plan";
  if (c.status === "AGREED") line = `Agreed with ${supplier} · waiting for the waybill${eta}`;
  if (c.status === "IN_TRANSIT")
    line = `On the way${t?.shipment_reference ? ` · waybill ${t.shipment_reference}` : ""}${eta}`;
  if (c.status === "DELIVERED") {
    const q = t?.received?.qty ?? t?.qty;
    line = `Delivered${q != null ? ` · ${num(q)} received` : ""}`;
  }
  const isDone = ["VERIFIED", "DECIDED", "DELIVERED"].includes(c.status);

  return (
    <li className="border-t border-zinc-100">
      <button onClick={() => onOpen(c.id)} className="group flex w-full items-start gap-3 px-5 py-3 text-left transition hover:bg-zinc-50">
        <span className="mt-1.5">
          {isDone ? (
            <span className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-500 text-white">
              <Icon name="check" className="h-2.5 w-2.5" />
            </span>
          ) : (
            <Pulse />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] text-zinc-800">{humanize(c.recommendation?.title || c.title)}</span>
          <span className={cx("mt-0.5 block text-xs", c.status === "DELIVERED" ? "text-emerald-700" : "text-zinc-500")}>
            {line}
            {approvedBy && <span className="text-zinc-400"> · approved by {approvedBy}</span>}
            {last && !eta && <span className="text-zinc-400"> · {when(last.at)}</span>}
          </span>
        </span>
        <Icon name="chevron" className="mt-1 h-3.5 w-3.5 text-zinc-300 group-hover:text-zinc-600" />
      </button>
    </li>
  );
}

/** First sentence, ignoring dots inside IDs, decimals and common abbreviations. */
export function firstSentence(raw: string): string {
  const s = raw.replace(/^C-\d{3,}\b/, "This");
  const m = s.match(/^.*?[a-z0-9)”"’][.!?](?=\s+[A-Z])/);
  return m ? m[0] : s;
}
