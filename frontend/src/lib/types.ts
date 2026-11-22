// Mirrors the real responses of the Aurora backend (aurora/api.py), inspected with curl.

export type CaseStatus =
  | "AWAITING_APPROVAL"
  | "READY_TO_ASK"
  | "AWAITING_HUMAN_REVIEW"
  | "AWAITING_SUPPLIER"
  | "EXECUTING"
  | "VERIFIED"
  | "ESCALATED"
  | "DECIDED"
  | "AGREED"
  | "IN_TRANSIT"
  | "DELIVERED"
  | "SUPERSEDED";

export interface Tracking {
  agreed_at?: string | null;
  expected_arrival?: string | null;
  qty?: number | null;
  supplier_id?: string | null;
  part?: string | null;
  shipment_reference?: string | null;
  received?: { gr_number?: string; qty?: number; delivery_note?: string } | null;
}

export interface DayOnePct {
  system: number;
  truth: number;
  current: number;
  what_if: number;
}

export interface Edition {
  product_id: string;
  name: string;
  remaining: number;
  system_buildable: number;
  truth_buildable: number;
  current_buildable: number;
  what_if_buildable: number;
  capacity_limit: number;
  bottleneck: string | null;
  short_by_part: Record<string, number>;
  day_one_qty: number;
  packed_before: number;
  day_one_pct: DayOnePct;
}

export interface Rule {
  text: string;
  source: string;
}

export interface Correction {
  part_id: string;
  qty: number;
  kind: string;
  reason: string;
  evidence: string[];
}

export interface RunReport {
  reason: string;
  documents: number;
  signals: number;
  cases_new: number;
  cases_updated: number;
  errors: string[];
}

export interface LastRun {
  id: number;
  started: string;
  finished: string;
  reason: string;
  report: RunReport;
}

export interface LastDrop {
  at: string;
  added: string[];
  changed: string[];
}

export interface Overview {
  tenant: string;
  deadline_name: string;
  deadline: string;
  as_of: string;
  hours_left: number;
  editions: Edition[];
  committed_actions: string[];
  rules_in_force: Rule[];
  corrections: Correction[];
  documents_read: number;
  verdict?: Verdict | null;
  /** Goal-oriented view of the launch (being added by the backend; optional until then). */
  goal?: Goal | null;
  part_names?: Record<string, string>;
  pack_hours_left?: number;
  autonomy_threshold?: number;
  counts: Partial<Record<CaseStatus, number>>;
  last_run: LastRun | null;
  last_drop: LastDrop | null;
  now: string;
}

export interface Approver {
  person: string | null;
  role: string;
  reason: string;
  policy_ref: string;
  fallback_for: string | null;
}

export interface ApproverChain {
  approvers: Approver[];
  notes: string[];
}

export interface Impact {
  copies_at_risk?: number;
  eur_at_risk?: number;
  by_product?: Record<string, number>;
  part?: string;
  part_name?: string;
  last_useful_moment?: string | null;
}

export interface Option {
  id: string;
  kind: string;
  title: string;
  qty: number;
  copies_gained: Record<string, number>;
  cost_eur: number;
  cost_note?: string;
  arrival_at: string | null;
  feasible: boolean;
  partial?: boolean;
  last_useful_moment: string | null;
  approver: ApproverChain;
  approval_kind: string;
  evidence: string[];
  score: number;
}

export interface CaseSummary {
  id: string;
  title: string;
  status: CaseStatus;
  playbook_id: string | null;
  playbook_title: string | null;
  tier: string | null;
  rank_score: number;
  summary: string;
  signal_type: string;
  severity: number;
  affects_deadline: boolean;
  impact: Impact;
  recommendation: Option | null;
  approver: ApproverChain | null;
  updated_at: string;
  explanation?: Explanation | null;
  supplier_intent?: string | null;
  also?: string[];
  /** People who must act on this case (approvers, deciders). */
  owners?: string[];
  /** The specialised agent that raised the case and which process step it sits on. */
  agent?: CaseAgent | null;
  /** Why this matters for the goal, in numbers. */
  why?: CaseWhy | null;
}

export interface CaseAgent {
  id: string;
  name: string;
  step: number;
}

export interface WhyCopies {
  product_id: string;
  name: string;
  copies: number;
}

export interface CaseWhy {
  goal: string;
  serves: WhyCopies[];
  trades: WhyCopies[];
  protects_eur: number;
  cost_eur: number;
  return_ratio: number;
  if_not: { copies: number; eur: number; name: string } | null;
  rule: { text: string; ref: string; source: string; stand_in?: string | null } | null;
  priority_rule: { text: string; source: string } | null;
  evidence_count: number;
  touches_deadline: boolean;
}

export interface ExplanationFact {
  text: string;
  source: string;
  system?: number | null;
  truth?: number | null;
}

export interface Explanation {
  headline: string;
  facts: ExplanationFact[];
  benefit: {
    copies: Record<string, number>; // keyed by edition NAME, e.g. "Collector's Edition"
    eur_protected: number;
    cost_eur: number;
    return_ratio: number;
    partial: boolean;
    text: string;
  } | null;
  if_not: { copies: Record<string, number>; eur_at_risk: number; text: string } | null;
  after_approve: string[];
}

export interface Finding {
  title: string;
  kind: string;
  source: string;
  raw: string;
}

export interface Signal {
  type: string;
  title: string;
  summary: string;
  entities: Record<string, string>;
  evidence: string[];
  severity: number;
  facts: {
    delta_qty?: number;
    affects_deadline?: boolean;
    findings?: Finding[];
    [k: string]: unknown;
  };
  fingerprint: string;
}

export interface CaseData {
  title: string;
  status: CaseStatus;
  playbook_id: string | null;
  playbook_title: string | null;
  tier: string | null;
  signal: Signal;
  impact: Impact;
  options: Option[];
  recommended_option: string | null;
  approver: ApproverChain | null;
  also: string[];
  supplier_intent: string | null;
  rank_score: number;
  tracking?: Tracking | null;
  investigation?: Investigation | null;
}

export interface InvestigationOption {
  title: string;
  action_kind: string;
  who_approves: string;
  cost_estimate_eur: number | null;
  effect: string;
  timing: string;
}

export interface Investigation {
  summary: string;
  affects_deadline: boolean;
  impact?: { copies_at_risk?: number; when?: string; explanation?: string };
  root_cause?: string;
  options?: InvestigationOption[];
  recommendation?: string;
  questions_for_human?: string[];
  evidence?: string[];
  playbook?: { title: string; trigger_keywords?: string[]; steps: string[]; tier: string } | null;
  confidence?: number;
  trace?: { tool: string; args?: Record<string, unknown>; result_preview?: string }[];
}

export interface CaseEvent {
  id: number;
  case_id: string;
  at: string;
  actor: string;
  text: string;
  data: string; // JSON string
}

export interface CaseMessage {
  id: number;
  case_id: string;
  direction: "in" | "out" | "outbox";
  counterpart: string;
  subject: string;
  body: string;
  body_en: string;
  message_id: string;
  at: string;
  parsed: string; // JSON string
}

export interface CaseAction {
  id: number;
  case_id: string;
  kind: string;
  tier: string;
  status: string;
  payload: string;
  result: string;
  created_at: string;
  updated_at: string;
}

export interface Autonomy {
  playbook_id: string;
  approvals: number;
  approvals_without_edit: number;
  auto_enabled: number | boolean;
}

export interface CaseDetail extends CaseSummary {
  data: CaseData;
  events: CaseEvent[];
  messages: CaseMessage[];
  actions: CaseAction[];
  autonomy: Autonomy;
}

// POST contracts
export interface ApproveBody {
  option_id?: string;
  approved_by: string;
  edited?: boolean;
  note?: string;
}

export interface ApproveResult {
  autonomy: Autonomy;
  email?: { sent: boolean; reason?: string; message_id?: string };
  offer_auto: boolean;
}

export interface DecideBody {
  decision: string;
  decided_by: string;
  save_as_playbook: boolean;
}

export interface DecideResult {
  ok: boolean;
  save_as_playbook?: boolean;
  saved_playbook?: string | { id?: string; title?: string } | null;
}

export interface PollResult {
  drop: { added?: string[]; changed?: string[]; removed?: string[]; pulled_at?: string };
  report: RunReport | null;
  replies: unknown[];
}

// GET /api/setup
export interface SetupSourceItem {
  kind: string;
  detail: string;
  status: string;
  note?: string;
}
export interface SetupTable {
  table: string;
  rows: number;
  files: number;
  configured: string[];
  learned: string[];
}
export interface LearnedSource {
  path: string;
  table: string;
  confidence: number;
  status?: string;
  reason: string;
}
export interface SetupProduct {
  id: string;
  name: string;
  priority: number;
  demand?: number;
  reason?: string;
  source?: string;
}
export interface GoalCheck {
  item: string;
  proposed: unknown;
  live: unknown;
  match: boolean;
}
export interface SetupPerson {
  name: string;
  role: string;
  category: string | null;
  site: string | null;
  from_date: string | null;
  until_date: string | null;
  vacant_until_start: boolean;
}
export interface SetupPlaybook {
  id: string;
  title: string;
  tier: "observe" | "ask" | "commit" | "never" | string;
  approval: string;
  /** "learned from C-0021 · Dr. Maren Vogt" for playbooks saved from a decision. */
  origin?: string;
}
export type SetupSectionKey = "sources" | "data" | "goal" | "rules" | "autonomy";

export interface Setup {
  tenant: string;
  sections: {
    sources: { items: SetupSourceItem[] };
    data: {
      tables: SetupTable[];
      learned_sources: LearnedSource[];
      pending_confirmation: LearnedSource[];
      documents: { total: number; by_type: Record<string, number>; by_language: Record<string, number> };
    };
    goal: {
      proposal: {
        objective: string;
        deadline_at: string;
        deadline_name: string;
        deadline_meaning: string;
        site: string;
        shifts: unknown[];
        products: SetupProduct[];
        success_metric: string;
        tolerances: string[];
        open_questions: string[];
      };
      live?: Record<string, unknown>;
      checks: GoalCheck[];
    };
    rules: {
      sources: string[];
      approval_limits: { role: string; max_eur_exclusive: number | null; jointly_with: string | null }[];
      people: SetupPerson[];
      site_leads: { site: string; lead: string; deputy: string | null }[];
      exception_role: string;
      quality_final_say: string;
      conditional_release_days: number;
      priority_rules: Rule[];
      release_rules: Rule[];
    };
    autonomy: {
      playbooks: SetupPlaybook[];
      unknown_problems: string;
      mandate_tolerance: number;
      max_agent_rounds: number;
      earned_autonomy_after: number;
      reply_timeout_minutes_demo?: number;
      notifications: string;
      never: string[];
    };
  };
  confirmations: Partial<Record<SetupSectionKey, { by: string; at: string }>>;
  /** Section order the backend wants shown (goal first). */
  flow?: SetupSectionKey[];
  progress?: { confirmed: number; total: number };
}

export interface VerdictProduct {
  product_id: string;
  name: string;
  view: "current" | "with_all";
  short: number;
  short_pct_of_launch: number;
  tolerance_pct: number;
  within: boolean;
}
export interface Verdict {
  on_time_now: boolean;
  on_time_with_all: boolean;
  text: string;
  products: VerdictProduct[];
}

/* ───────── Goal (GET /api/overview.goal) ───────── */

export interface GoalPriority {
  product_id: string;
  name: string;
  priority: number;
  tolerance_pct: number;
  customer_weight?: number;
  value_per_unit_eur?: number;
  why?: string;
  source?: string;
}

export interface GoalStatusProduct {
  product_id: string;
  name: string;
  launch_pct_now: number;
  launch_pct_with_all: number;
  short_now: number;
  short_with_all: number;
  tolerance_pct: number;
  within_now: boolean;
  within_with_all: boolean;
}

export interface Goal {
  objective: string;
  deadline: { name: string; at: string; site: string; meaning?: string; pack_hours_left?: number };
  priorities: GoalPriority[];
  ranking_rule?: string;
  status: {
    on_time_now: boolean;
    on_time_with_all: boolean;
    text: string;
    products: GoalStatusProduct[];
  };
  decisions?: { waiting: number; people: number; cost_eur: number };
  sources?: string[];
  proposed_by?: string;
  confirmed?: { by: string; at: string } | null;
}

/* ───────── AI team (GET /api/agents) ───────── */

export interface ProcessStep {
  step: number;
  name: string;
  system_today: string;
  had_system?: boolean;
  agents: string[];
  open_cases?: number;
}

export interface AgentInfo {
  id: string;
  name: string;
  steps?: number[];
  /** Older shape. */
  process_steps?: number[];
  task: string;
  trigger: string;
  /** Boolean in the older shape; a verb phrase ("Asks the supplier") in the newer one. */
  acts_alone: boolean | string;
  needs_human: string;
  kind: string;
  aop_tier?: string;
  activity: number | { count: number; label?: string; last?: string | null };
  /** Older shape. */
  last_activity?: string | null;
  cases?: string[];
}

export interface AutonomyInfo {
  tiers?: { tier: string; title?: string; explain?: string }[] | string[];
  earned_after?: number;
  never?: string[];
  playbooks?: { id: string; title: string; tier: string; approval?: string; origin?: string }[];
}

export interface AgentsResponse {
  goal?: {
    objective?: string;
    deadline_at?: string;
    deadline_name?: string;
    site?: string;
    products?: SetupProduct[];
    tolerances?: string[];
    priorities?: GoalPriority[];
    ranking_rule?: string;
    sources?: string[];
    confirmed?: { by: string; at: string } | null;
    [k: string]: unknown;
  } | null;
  process: ProcessStep[];
  agents: AgentInfo[];
  autonomy?: AutonomyInfo | null;
  /** "matching" | "chasing" | "exception_handling" → agent ids. */
  operative_layer?: Record<string, string[]>;
  stats?: { documents_read?: number; problems_open?: number; last_run?: string | null };
}

/* ───────── People (GET /api/people, /api/people/{name}/inbox) ───────── */

export interface Person {
  name: string;
  role: string;
  category: string | null;
  from_date?: string | null;
  open_items: number;
  case_ids: string[];
  scope?: string;
  inbox?: { approve: number; decide: number; ask: number };
  in_flight?: number;
  stand_in_for?: string[];
  top?: { case_id: string; line: string } | null;
}

export interface Inbox {
  person: { name: string; role: string; category?: string | null; scope?: string };
  headline?: string;
  approve: CaseSummary[];
  decide: CaseSummary[];
  ask: CaseSummary[];
  in_flight: CaseSummary[];
  done: CaseSummary[];
  agents_for_you?: { agent: string; name: string; case_id: string; text: string }[];
}
