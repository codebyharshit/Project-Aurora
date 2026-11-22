import type { CaseSummary, Edition, Option, Overview } from "./types";
import { shortEdition } from "./format";

/** part id → readable name, learned from the cases (the overview only carries ids). */
export function partNames(cases: CaseSummary[] | undefined): Record<string, string> {
  const m: Record<string, string> = {};
  for (const c of cases || []) {
    const p = c.impact?.part;
    const n = c.impact?.part_name;
    if (p && n && n !== p) m[p] = n;
  }
  return m;
}

export function editionNames(ov: Overview | undefined): Record<string, string> {
  const m: Record<string, string> = {};
  for (const e of ov?.editions || []) m[e.product_id] = shortEdition(e.name);
  return m;
}

/** Collector's first (it is the priority line), then the rest in backend order. */
export function orderEditions(eds: Edition[]): Edition[] {
  return [...eds].sort((a, b) => Number(/collector/i.test(b.name)) - Number(/collector/i.test(a.name)));
}

export interface Gain {
  product: string;
  name: string;
  qty: number;
}

export function gains(opt: Option | null | undefined, names: Record<string, string>): { up: Gain[]; down: Gain[] } {
  const up: Gain[] = [];
  const down: Gain[] = [];
  for (const [product, qty] of Object.entries(opt?.copies_gained || {})) {
    const g = { product, name: names[product] || product, qty };
    if (qty > 0) up.push(g);
    else if (qty < 0) down.push(g);
  }
  // Collector's first in both lists
  const byPriority = (a: Gain, b: Gain) => Number(/collector/i.test(b.name)) - Number(/collector/i.test(a.name));
  return { up: up.sort(byPriority), down: down.sort(byPriority) };
}

export const STATUS_ORDER = {
  // Escalated cases (no supplier reply after a follow-up) jump to the top of the queue.
  queue: ["ESCALATED", "AWAITING_APPROVAL"],
  inFlight: ["IN_TRANSIT", "AGREED", "AWAITING_SUPPLIER", "EXECUTING"],
  done: ["DELIVERED", "VERIFIED", "DECIDED"],
  judgement: ["AWAITING_HUMAN_REVIEW"],
  ask: ["READY_TO_ASK"],
} as const;

export function byRank(a: CaseSummary, b: CaseSummary): number {
  return (b.rank_score || 0) - (a.rank_score || 0);
}

/** Plain words for correction kinds. */
export const CORRECTION_KIND: Record<string, string> = {
  receipt_correction: "Receipt booked wrong",
  short_shipment: "Shipped less than ordered",
  banned_revision: "Old revision, not allowed",
  rejected_lot: "Failed inspection",
  needs_review: "Unclear, not applied",
};
