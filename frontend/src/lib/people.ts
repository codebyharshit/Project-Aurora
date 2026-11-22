"use client";

import { useMemo } from "react";
import { useCaseDetails } from "./api";
import { byRank } from "./derive";
import type { ApproverChain, CaseDetail, CaseStatus, CaseSummary, Person } from "./types";

/* Which statuses mean what for a person. */
export const APPROVE: readonly CaseStatus[] = ["ESCALATED", "AWAITING_APPROVAL"];
export const DECIDE: readonly CaseStatus[] = ["AWAITING_HUMAN_REVIEW"];
export const ASK: readonly CaseStatus[] = ["READY_TO_ASK"];
export const IN_FLIGHT: readonly CaseStatus[] = ["AWAITING_SUPPLIER", "AGREED", "IN_TRANSIT", "EXECUTING"];
export const DONE: readonly CaseStatus[] = ["DELIVERED", "VERIFIED", "DECIDED"];
export const OPEN: readonly CaseStatus[] = [...APPROVE, ...DECIDE, ...ASK];

export function chainOf(c: CaseSummary): ApproverChain | null | undefined {
  return c.recommendation?.approver || c.approver;
}

/** Owners from the summary: the backend's `owners`, else the people the policy routes it to. */
export function ownersFromSummary(c: CaseSummary): string[] {
  if (c.owners?.length) return c.owners;
  const out: string[] = [];
  for (const a of chainOf(c)?.approvers || []) if (a.person && !out.includes(a.person)) out.push(a.person);
  return out;
}

const NOTIFIED = /(?:emailed|sent|notified|routed) to ([^.;:(]+?)(?:\s+\(|$)/i;

/** Review cases carry no approver chain; the Notifier's event says who was asked. */
export function ownersFromDetail(d: CaseDetail, people: Person[]): string[] {
  const base = ownersFromSummary(d);
  if (base.length) return base;
  const found: string[] = [];
  for (const e of d.events || []) {
    const m = e.text.match(NOTIFIED);
    if (m) {
      const n = m[1].trim();
      if (!found.includes(n)) found.push(n);
    }
  }
  if (found.length) return found;
  const names = people.map((p) => p.name);
  for (const o of d.data?.investigation?.options || []) {
    const p = names.find((n) => o.who_approves?.includes(n));
    if (p) return [p];
  }
  return [];
}

/** Owners for every case; review cases without a chain are filled from their details. */
export function useOwners(cases: CaseSummary[] | undefined, people: Person[] | undefined): Record<string, string[]> {
  const needDetail = useMemo(
    () =>
      (cases || [])
        .filter((c) => OPEN.includes(c.status) && !ownersFromSummary(c).length)
        .map((c) => c.id),
    [cases],
  );
  const { data: details } = useCaseDetails(needDetail);
  return useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const c of cases || []) {
      let o = ownersFromSummary(c);
      if (!o.length) {
        const d = details?.find((x) => x.id === c.id);
        if (d) o = ownersFromDetail(d, people || []);
      }
      m[c.id] = o;
    }
    return m;
  }, [cases, details, people]);
}

export interface DerivedInbox {
  approve: CaseSummary[];
  decide: CaseSummary[];
  ask: CaseSummary[];
  in_flight: CaseSummary[];
  done: CaseSummary[];
}

function pick(cases: CaseSummary[], statuses: readonly CaseStatus[], keep: (c: CaseSummary) => boolean) {
  const order = (s: CaseStatus) => statuses.indexOf(s);
  return cases
    .filter((c) => statuses.includes(c.status) && keep(c))
    .sort((a, b) => order(a.status) - order(b.status) || byRank(a, b));
}

/** What one person sees, derived from the queue when /api/people/{name}/inbox is not there. */
export function inboxFor(name: string, cases: CaseSummary[], owners: Record<string, string[]>): DerivedInbox {
  const mine = (c: CaseSummary) => (owners[c.id] || []).includes(name);
  return {
    approve: pick(cases, APPROVE, mine),
    decide: pick(cases, DECIDE, mine),
    ask: pick(cases, ASK, mine),
    in_flight: pick(cases, IN_FLIGHT, mine),
    done: pick(cases, DONE, mine),
  };
}

export interface PersonWork {
  person: Person;
  count: number;
  top: CaseSummary | null;
  topLine: string | null;
  standIn: boolean;
  scope: string;
}

export function scopeOf(p: Person): string {
  return p.scope || [p.role, p.category].filter(Boolean).join(" · ");
}

/** People with something open, most urgent first. */
export function peopleWithWork(
  people: Person[],
  cases: CaseSummary[],
  owners: Record<string, string[]>,
): PersonWork[] {
  const out: PersonWork[] = [];
  for (const p of people) {
    const mine = cases.filter((c) => OPEN.includes(c.status) && (owners[c.id] || []).includes(p.name));
    const derived = mine.length;
    const count = derived || p.open_items || 0;
    if (count === 0) continue;
    const top = [...mine].sort((a, b) => Number(APPROVE.includes(b.status)) - Number(APPROVE.includes(a.status)) || byRank(a, b))[0] || null;
    const standIn =
      (p.stand_in_for?.length ?? 0) > 0 ||
      mine.some((c) => (chainOf(c)?.approvers || []).some((a) => a.person === p.name && !!a.fallback_for));
    out.push({ person: p, count, top, topLine: p.top?.line || null, standIn, scope: scopeOf(p) });
  }
  return out.sort((a, b) => {
    const ua = a.top ? Number(APPROVE.includes(a.top.status)) : 0;
    const ub = b.top ? Number(APPROVE.includes(b.top.status)) : 0;
    return ub - ua || b.count - a.count || (b.top?.rank_score || 0) - (a.top?.rank_score || 0);
  });
}
