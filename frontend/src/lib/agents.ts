import type { AgentInfo, AgentsResponse, CaseAgent, CaseSummary, ProcessStep } from "./types";

/** Soony's seven-step process, used until /api/agents carries `process`. */
export const PROCESS_FALLBACK: ProcessStep[] = [
  { step: 1, name: "Order", system_today: "SAP (purchase orders)", had_system: true, agents: ["approvals", "sourcing"] },
  { step: 2, name: "Confirm", system_today: "Email, PDF", had_system: false, agents: ["order_confirmation", "reader"] },
  { step: 3, name: "Ship", system_today: "4 logistics providers", had_system: false, agents: ["chaser", "negotiator"] },
  { step: 4, name: "Track", system_today: "Spreadsheet", had_system: false, agents: ["tracking"] },
  { step: 5, name: "Receive", system_today: "Paper scans", had_system: false, agents: ["stock_truth", "release_gate"] },
  { step: 6, name: "Pack", system_today: "Pack-out log", had_system: true, agents: ["launch_planner"] },
  { step: 7, name: "Sell", system_today: "Sun 20:00", had_system: false, agents: ["launch_planner", "investigator"] },
];

/** Only ① Order (SAP) and ⑥ Pack (pack-out log) had a system before Aurora. */
const HAD_SYSTEM = new Set([1, 6]);

export function hadSystem(s: ProcessStep): boolean {
  return s.had_system ?? HAD_SYSTEM.has(s.step);
}

/** Which agent raised a case and where it sits, when the backend doesn't say. */
const SIGNAL_AGENT: Record<string, CaseAgent> = {
  qty_contradiction: { id: "stock_truth", name: "Stock Truth Agent", step: 5 },
  receipt_without_po: { id: "stock_truth", name: "Stock Truth Agent", step: 5 },
  short_shipment: { id: "stock_truth", name: "Stock Truth Agent", step: 5 },
  rejected_lot_in_stock: { id: "release_gate", name: "Release Gate Agent", step: 5 },
  banned_revision: { id: "release_gate", name: "Release Gate Agent", step: 5 },
  qualification_expired: { id: "release_gate", name: "Release Gate Agent", step: 5 },
  needs_review: { id: "reader", name: "Document Reader Agent", step: 5 },
  confirmation_mismatch: { id: "order_confirmation", name: "Order Confirmation Agent", step: 2 },
  arrived_not_collected: { id: "tracking", name: "Tracking Agent", step: 4 },
  stale_tracking: { id: "tracking", name: "Tracking Agent", step: 4 },
  tracking_contradiction: { id: "tracking", name: "Tracking Agent", step: 4 },
};

/** "Stock Truth Agent" → "Stock Truth", for tight spaces. */
export function shortAgent(name: string): string {
  return name.replace(/\s+Agent$/i, "");
}

/** "Acts alone" / "Needs a person", or the backend's own verb phrase. */
export function aloneText(a: AgentInfo): { text: string; alone: boolean } {
  if (typeof a.acts_alone === "string") return { text: a.acts_alone, alone: true };
  return a.acts_alone ? { text: "Acts alone", alone: true } : { text: "Needs a person", alone: false };
}

export function agentOf(c: CaseSummary): CaseAgent | null {
  if (c.agent) return c.agent;
  if (SIGNAL_AGENT[c.signal_type]) return SIGNAL_AGENT[c.signal_type];
  if (c.signal_type?.startsWith("novel:")) return { id: "investigator", name: "Investigator", step: 7 };
  return null;
}

export function stepsOf(a: AgentInfo): number[] {
  return a.steps || a.process_steps || [];
}

export function activityOf(a: AgentInfo): { count: number; label: string | null; last: string | null } {
  if (typeof a.activity === "number") return { count: a.activity, label: null, last: a.last_activity ?? null };
  return { count: a.activity?.count ?? 0, label: a.activity?.label ?? null, last: a.activity?.last ?? null };
}

/** Open cases per step: the backend's `open_cases`, else counted from the queue. */
export function openByStep(process: ProcessStep[], cases: CaseSummary[] | undefined, openStatuses: readonly string[]) {
  const m: Record<number, number> = {};
  for (const s of process) m[s.step] = s.open_cases ?? 0;
  if (process.some((s) => s.open_cases != null)) return m;
  for (const c of cases || []) {
    if (!openStatuses.includes(c.status)) continue;
    const a = agentOf(c);
    if (a) m[a.step] = (m[a.step] || 0) + 1;
  }
  return m;
}

/** Cases per agent id: the backend's `cases`, else matched by the case's agent. */
export function casesByAgent(agents: AgentInfo[], cases: CaseSummary[] | undefined): Record<string, CaseSummary[]> {
  const m: Record<string, CaseSummary[]> = {};
  const byId: Record<string, CaseSummary> = {};
  for (const c of cases || []) byId[c.id] = c;
  for (const a of agents) {
    if (a.cases) m[a.id] = a.cases.map((id) => byId[id]).filter((c): c is CaseSummary => !!c);
    else m[a.id] = (cases || []).filter((c) => agentOf(c)?.id === a.id && c.status !== "SUPERSEDED");
  }
  return m;
}

export function processOf(data: AgentsResponse | undefined): ProcessStep[] {
  return data?.process?.length ? data.process : PROCESS_FALLBACK;
}

export const TIER_WORD: Record<string, string> = {
  observe: "Observe",
  ask: "Ask",
  commit: "Commit",
  never: "Never automatic",
};

export const TIER_EXPLAIN: Record<string, string> = {
  observe: "Watches and records; nobody is bothered.",
  ask: "May email a supplier with a question on its own.",
  commit: "Prepares it; the person the policy names approves with one click.",
  never: "Always a human, whatever the track record.",
};
