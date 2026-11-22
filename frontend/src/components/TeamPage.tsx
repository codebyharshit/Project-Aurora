"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { fileUrl, useAgents, useCases, useOverview, usePeople, useSetup } from "@/lib/api";
import { activityOf, aloneText, casesByAgent, hadSystem, openByStep, processOf, shortAgent, stepsOf, TIER_EXPLAIN, TIER_WORD } from "@/lib/agents";
import { editionNames, orderEditions, partNames } from "@/lib/derive";
import { docName, prettyName, resolvePath } from "@/lib/evidence";
import { eur, num, pct, shortEdition, when } from "@/lib/format";
import { OPEN, peopleWithWork, useOwners } from "@/lib/people";
import type { AgentInfo, AgentsResponse, CaseSummary, GoalPriority, Overview, ProcessStep, Rule, Setup } from "@/lib/types";
import { AGENT_ICON } from "./AgentsFeed";
import { CaseDrawer } from "./CaseDrawer";
import { Header } from "./Header";
import { ProcessStrip } from "./ProcessStrip";
import { CorrectionsList, RulesInForce } from "./Sections";
import { ESTIMATE_NOTE, humanize } from "./Story";
import { Card, Chip, cx, Icon, Pulse, Tip } from "./ui";

const CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"];


/** The AI team: the goal it serves, Soony's process, one agent per business task, and what they may do alone. */
export function TeamPage() {
  const { data: ov } = useOverview();
  const { data: cases } = useCases();
  const { data: people } = usePeople();
  const { data: agentsData, error } = useAgents();
  const { data: setup } = useSetup();
  const owners = useOwners(cases, people);
  const [openId, setOpenId] = useState<string | null>(null);
  const close = useCallback(() => setOpenId(null), []);

  const names = useMemo(() => editionNames(ov), [ov]);
  const parts = useMemo(() => ({ ...partNames(cases), ...(ov?.part_names || {}) }), [cases, ov]);
  const work = useMemo(() => peopleWithWork(people || [], cases || [], owners), [people, cases, owners]);
  const counts = useMemo(() => Object.fromEntries(work.map((w) => [w.person.name, w.count])), [work]);
  const process = processOf(agentsData);
  const agents = useMemo(() => agentsData?.agents || [], [agentsData]);
  const open = useMemo(() => openByStep(process, cases, OPEN), [process, cases]);
  const byAgent = useMemo(() => casesByAgent(agents, cases), [agents, cases]);
  const hasGate = agents.some((a) => /gate|release/i.test(a.id) || /gate|release/i.test(a.name));
  const layer = agentsData?.operative_layer;
  const layerName = (id: string) => shortAgent(agents.find((a) => a.id === id)?.name || id);

  return (
    <div className="min-h-screen">
      <Header ov={ov} counts={counts} />
      <main className="mx-auto max-w-[1120px] space-y-6 px-5 pb-20 pt-6">
        <div>
          <h1 className="text-[24px] font-semibold tracking-tight text-soony-ink">The AI team</h1>
          <p className="mt-1 text-[14px] text-zinc-600">
            One specialised agent per business task, mapped to Soony’s process. Each knows the goal, the rules and who
            approves.
          </p>
        </div>

        {error && !agentsData ? (
          <Card className="px-6 py-8 text-sm text-zinc-600">Couldn’t load the AI team. Is the backend running?</Card>
        ) : !agentsData || !ov ? (
          <Card className="flex items-center gap-3 px-6 py-8 text-[15px] text-zinc-600">
            <Pulse tone="amber" /> Gathering the team…
          </Card>
        ) : (
          <>
            <GoalHeader ov={ov} agentsData={agentsData} setup={setup} />
            <ProcessStrip process={process} agents={agents} open={open} linkTo="" />

            <section>
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-[17px] font-semibold tracking-tight text-zinc-900">
                  Matching · Chasing · Exception handling
                </h2>
                <p className="text-xs text-zinc-500">the operative layer · {agents.length} agents</p>
              </div>
              {layer && (
                <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-zinc-600">
                  {Object.entries(layer).map(([k, ids]) => (
                    <span key={k}>
                      <span className="font-medium text-zinc-700">{k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}:</span>{" "}
                      {ids.map(layerName).join(" · ")}
                    </span>
                  ))}
                </p>
              )}
              <div className="mt-4 space-y-6">
                {process.map((s) => {
                  const group = agents.filter((a) => stepsOf(a)[0] === s.step);
                  if (!group.length) return null;
                  return (
                    <StepGroup key={s.step} step={s} open={open[s.step] || 0}>
                      {group.map((a) => (
                        <AgentCard key={a.id} a={a} cases={byAgent[a.id] || []} ov={ov} parts={parts} hasGate={hasGate} onOpen={setOpenId} />
                      ))}
                    </StepGroup>
                  );
                })}
                {agents.some((a) => !stepsOf(a).length) && (
                  <StepGroup open={0}>
                    {agents
                      .filter((a) => !stepsOf(a).length)
                      .map((a) => (
                        <AgentCard key={a.id} a={a} cases={byAgent[a.id] || []} ov={ov} parts={parts} hasGate={hasGate} onOpen={setOpenId} />
                      ))}
                  </StepGroup>
                )}
              </div>
            </section>

            <AutonomyLadder agentsData={agentsData} setup={setup} ov={ov} />
          </>
        )}
      </main>
      <CaseDrawer id={openId} names={names} onClose={close} />
    </div>
  );
}

/* ───────── Goal ───────── */

function GoalHeader({ ov, agentsData, setup }: { ov: Overview; agentsData: AgentsResponse; setup?: Setup }) {
  const g = ov.goal;
  const ag = agentsData.goal || null;
  const sg = setup?.sections.goal.proposal;
  const objective = g?.objective || ag?.objective || sg?.objective || "";
  const tol = (id: string) => ov.verdict?.products.find((p) => p.product_id === id)?.tolerance_pct;
  const priorities: GoalPriority[] =
    g?.priorities ||
    ag?.priorities ||
    (ag?.products || sg?.products || []).map((p) => ({
      product_id: p.id,
      name: p.name,
      priority: p.priority,
      tolerance_pct: tol(p.id) ?? 0,
      why: p.reason,
      source: p.source,
    }));
  const ranking = g?.ranking_rule || ag?.ranking_rule || "Most customers protected per euro, in time; shared parts go to Collector’s first.";
  const statusText = g?.status?.text || ov.verdict?.text || "";
  const sources = Array.from(
    new Set(
      g?.sources ||
        ag?.sources ||
        priorities.flatMap((p) => (p.source || "").split(/;\s*/).filter(Boolean)),
    ),
  );
  const confirmed = g?.confirmed ?? ag?.confirmed ?? setup?.confirmations?.goal ?? null;
  const eds = orderEditions(ov.editions);
  const pctOf = (id: string) => {
    const p = g?.status?.products?.find((x) => x.product_id === id);
    const e = eds.find((x) => x.product_id === id);
    return p ? { now: p.launch_pct_now, after: p.launch_pct_with_all } : e ? { now: e.day_one_pct.current, after: e.day_one_pct.what_if } : null;
  };

  return (
    <Card className="p-6">
      <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600">
        <Icon name="target" className="h-3.5 w-3.5 text-zinc-500" />
        The goal every agent serves
      </p>
      <p className="mt-2.5 max-w-3xl text-[18px] font-medium leading-snug tracking-tight text-soony-ink">{objective}</p>

      <div className="mt-5 grid gap-x-10 gap-y-5 md:grid-cols-[1fr_1fr]">
        <div>
          <p className="text-xs text-zinc-500">Priorities</p>
          <ol className="mt-2 space-y-2">
            {[...priorities]
              .sort((a, b) => a.priority - b.priority)
              .map((p) => {
                const s = pctOf(p.product_id);
                return (
                  <li key={p.product_id} className="flex items-start gap-3">
                    <span className="tnum mt-px inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-soony-blue text-[11px] font-semibold text-white">
                      {p.priority}
                    </span>
                    <div className="min-w-0">
                      <p className="tnum text-[14px] text-zinc-900">
                        <span className="font-medium">{shortEdition(p.name)}</span>
                        <span className="text-zinc-600">
                          {" "}
                          · tolerance {num(p.tolerance_pct)}%
                          {p.value_per_unit_eur != null && (
                            <Tip tip={ESTIMATE_NOTE}>
                              <span className="cursor-help"> · {eur(p.value_per_unit_eur)}/copy</span>
                            </Tip>
                          )}
                        </span>
                      </p>
                      {s && (
                        <p className="tnum text-[12.5px] text-zinc-600">
                          Now <span className="font-medium text-zinc-800">{pct(s.now)}</span>
                          {Math.abs(s.after - s.now) >= 0.05 && (
                            <>
                              {" "}
                              → with approvals <span className="font-medium text-soony-blue">{pct(s.after)}</span>
                            </>
                          )}{" "}
                          of launch
                        </p>
                      )}
                      {p.why && <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-snug text-zinc-600">{p.why}</p>}
                    </div>
                  </li>
                );
              })}
          </ol>
        </div>
        <div className="space-y-4">
          <div>
            <p className="text-xs text-zinc-500">Ranking rule</p>
            <p className="mt-1 text-[13.5px] leading-snug text-zinc-700">{ranking}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">Status</p>
            <p className="mt-1 flex items-start gap-2 text-[13.5px] leading-snug text-zinc-700">
              <span
                className={cx(
                  "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                  (g?.status?.on_time_now ?? ov.verdict?.on_time_now) ? "bg-emerald-500" : "bg-amber-500",
                )}
              />
              {statusText}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs text-zinc-500">Read from</span>
          {sources.map((s) => (
            <a
              key={s}
              href={fileUrl(resolvePath(s))}
              target="_blank"
              rel="noreferrer"
              title={prettyName(s)}
              className="inline-flex max-w-[260px] items-center gap-1 rounded-md bg-white px-1.5 py-0.5 text-xs text-zinc-600 ring-1 ring-inset ring-zinc-200 transition hover:text-zinc-900 hover:ring-zinc-400"
            >
              <Icon name="doc" className="h-3 w-3 text-zinc-500" />
              <span className="truncate">{docName(s)}</span>
            </a>
          ))}
        </div>
        {confirmed ? (
          <span className="inline-flex items-center gap-1.5 text-[13px] text-emerald-700">
            <Icon name="check" className="h-3.5 w-3.5" /> Confirmed by {confirmed.by} {when(confirmed.at)}
          </span>
        ) : (
          <Link href="/setup#goal" className="text-[13px] text-soony-blue underline-offset-2 hover:underline">
            Proposed by {g?.proposed_by || "the Onboarding agent"} · Confirm in Setup →
          </Link>
        )}
      </div>
    </Card>
  );
}

/* ───────── Agents by step ───────── */

function StepGroup({ step, open, children }: { step?: ProcessStep; open: number; children: React.ReactNode }) {
  return (
    <div id={step ? `step-${step.step}` : "step-all"} className="scroll-mt-20">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-[15px] font-semibold text-zinc-900">
          {step ? (
            <>
              <span className="mr-1.5 text-zinc-500" aria-hidden>
                {CIRCLED[step.step - 1]}
              </span>
              {step.name}
            </>
          ) : (
            "Across every step"
          )}
        </h3>
        {step && (
          <>
            <span className="text-[13px] text-zinc-600">{step.system_today}</span>
            <span
              className={cx(
                "rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide",
                hadSystem(step) ? "text-zinc-600 ring-1 ring-inset ring-zinc-200" : "bg-soony-blue/8 text-soony-blue",
              )}
            >
              {hadSystem(step) ? "had a system" : "now an agent"}
            </span>
            {open > 0 && <span className="tnum text-[12px] text-amber-700">{open} open</span>}
          </>
        )}
      </div>
      <div className="mt-2.5 grid grid-cols-1 gap-4 md:grid-cols-2">{children}</div>
    </div>
  );
}

function AgentCard({
  a,
  cases,
  ov,
  parts,
  hasGate,
  onOpen,
}: {
  a: AgentInfo;
  cases: CaseSummary[];
  ov: Overview;
  parts: Record<string, string>;
  /** Is there a Release Gate agent to carry the memo's release rules? Else the Approvals agent carries all rules. */
  hasGate: boolean;
  onOpen: (id: string) => void;
}) {
  const act = activityOf(a);
  const [more, setMore] = useState(false);
  const alone = aloneText(a);
  const isStockTruth = a.id === "stock_truth" || a.id === "detectors" || /stock truth/i.test(a.name);
  const isPolicy = a.id === "approvals" || a.id === "policy" || /approval/i.test(a.name);
  const isGate = /gate|release/i.test(a.id) || /gate|release/i.test(a.name);
  const rules: Rule[] = isPolicy
    ? hasGate
      ? ov.rules_in_force.filter((r) => /pp-07|policy/i.test(r.source))
      : ov.rules_in_force
    : isGate
      ? ov.rules_in_force.filter((r) => !/pp-07|policy/i.test(r.source))
      : [];
  const extra = isStockTruth
    ? { title: "What we corrected in the ERP, and why", count: ov.corrections.length }
    : rules.length
      ? { title: "Rules it applies", count: rules.length }
      : null;
  const label =
    act.label ||
    (act.count > 0 ? `${act.count} ${act.count === 1 ? "action" : "actions"}${act.last ? ` · last ${when(act.last)}` : ""}` : "Quiet so far");

  return (
    <Card className="flex flex-col">
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-start gap-3">
          <span
            className={cx(
              "mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              act.count > 0 ? "bg-soony-blue/8 text-soony-blue" : "bg-zinc-100 text-zinc-600",
            )}
          >
            <Icon name={AGENT_ICON[a.id] || "bolt"} className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h4 className="text-[15px] font-semibold text-zinc-900">{a.name}</h4>
              {a.aop_tier && (
                <Chip tone="ghost" className="!py-0 text-[11px]" title="Autonomy tier">
                  {TIER_WORD[a.aop_tier] || a.aop_tier}
                </Chip>
              )}
            </div>
            <p className="mt-1 text-[13px] leading-snug text-zinc-600">{a.task}</p>
          </div>
        </div>

        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12.5px]">
          <dt className="text-zinc-500">Trigger</dt>
          <dd className="text-zinc-700">{a.trigger}</dd>
          <dt className="text-zinc-500">Alone</dt>
          <dd className="text-zinc-700">
            <span className={alone.alone ? "text-emerald-700" : "text-amber-700"}>{alone.text}</span>
            {a.needs_human && a.needs_human !== "Never" && (
              <span className="text-zinc-600"> · needs a person: {lowerFirst(a.needs_human)}</span>
            )}
          </dd>
          <dt className="text-zinc-500">Kind</dt>
          <dd className="text-zinc-700">{a.kind}</dd>
        </dl>

        <p className="mt-3 flex items-center gap-2 text-[12.5px] text-zinc-600">
          {act.count > 0 ? <Pulse tone="green" /> : <span className="inline-block h-2 w-2 rounded-full bg-zinc-200" />}
          {label}
        </p>

        {cases.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {cases.slice(0, 4).map((c) => (
              <button
                key={c.id}
                onClick={() => onOpen(c.id)}
                className="inline-flex max-w-[240px] items-center gap-1 rounded-md bg-zinc-50 px-1.5 py-0.5 text-[11.5px] text-zinc-600 ring-1 ring-inset ring-zinc-200 transition hover:text-zinc-900 hover:ring-zinc-400"
                title={humanize(c.title)}
              >
                <span
                  className={cx(
                    "h-1.5 w-1.5 shrink-0 rounded-full",
                    OPEN.includes(c.status) ? "bg-amber-500" : c.status === "SUPERSEDED" ? "bg-zinc-300" : "bg-emerald-500",
                  )}
                />
                <span className="truncate">{shortTitle(c, parts)}</span>
              </button>
            ))}
            {cases.length > 4 && <span className="self-center text-[11px] text-zinc-500">+{cases.length - 4} more</span>}
          </div>
        )}
      </div>

      {extra && (
        <div className="mt-auto border-t border-zinc-100">
          <button
            onClick={() => setMore(!more)}
            aria-expanded={more}
            className="flex w-full items-center justify-between gap-2 px-4 py-2 text-left text-[12.5px] text-zinc-600 transition hover:text-zinc-900"
          >
            <span>
              {extra.title} <span className="tnum text-zinc-500">{extra.count}</span>
            </span>
            <Icon name="chevron" className={cx("h-3.5 w-3.5 transition", more && "rotate-90")} />
          </button>
          {more &&
            (isStockTruth ? (
              <CorrectionsList items={ov.corrections} parts={parts} />
            ) : (
              <div className="border-t border-zinc-100 px-4 py-3">
                <RulesInForce rules={rules} bare />
              </div>
            ))}
        </div>
      )}
    </Card>
  );
}

function shortTitle(c: CaseSummary, parts: Record<string, string>): string {
  const t = humanize(c.title).replace(/^(accept|collect|sort|confirm)\b/i, (m) => m);
  const part = c.impact?.part_name || (c.impact?.part ? parts[c.impact.part] : "");
  const s = t.length > 44 && part ? part : t;
  return s.length > 44 ? s.slice(0, 42).trimEnd() + "…" : s;
}

function lowerFirst(s: string): string {
  return s && s[1] && s[1] === s[1].toLowerCase() ? s[0].toLowerCase() + s.slice(1) : s;
}

/* ───────── Autonomy ladder ───────── */

const LADDER = ["observe", "ask", "commit", "never"] as const;

function AutonomyLadder({ agentsData, setup, ov }: { agentsData: AgentsResponse; setup?: Setup; ov: Overview }) {
  const au = agentsData.autonomy || null;
  const sa = setup?.sections.autonomy;
  const earned = au?.earned_after ?? sa?.earned_autonomy_after ?? ov.autonomy_threshold ?? 3;
  const never = au?.never ?? sa?.never ?? [];
  const playbooks = au?.playbooks ?? sa?.playbooks ?? [];

  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-[17px] font-semibold tracking-tight text-zinc-900">What they may do alone</h2>
        <p className="text-xs text-zinc-500">
          a playbook moves up one rung after {earned} clean approvals · <Link href="/setup#autonomy" className="underline-offset-2 hover:text-soony-blue hover:underline">change in Setup</Link>
        </p>
      </div>
      <Card className="mt-4 p-5">
        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
          {LADDER.map((tier, i) => {
            const list = playbooks.filter((p) => p.tier === tier);
            return (
              <li key={tier} className="relative">
                {i > 0 && (
                  <span className="absolute -left-3 top-3 hidden h-px w-3 bg-zinc-300 md:block" aria-hidden />
                )}
                <div
                  className={cx(
                    "rounded-lg p-3.5 ring-1 ring-inset",
                    tier === "commit" ? "bg-amber-50/40 ring-amber-200" : tier === "never" ? "ring-zinc-300" : "ring-zinc-200",
                  )}
                >
                  <p className="flex items-center gap-2 text-[14px] font-medium text-zinc-900">
                    <span className="tnum inline-flex h-5 w-5 items-center justify-center rounded-full bg-soony-ink text-[11px] font-semibold text-white">
                      {i + 1}
                    </span>
                    {TIER_WORD[tier]}
                  </p>
                  <p className="mt-1 text-xs text-zinc-600">{TIER_EXPLAIN[tier]}</p>
                  <ul className="mt-2.5 space-y-1.5">
                    {tier === "never" && list.length === 0
                      ? never.map((n) => (
                          <li key={n} className="text-[13px] leading-snug text-zinc-700">
                            {n.replace(/^./, (c) => c.toUpperCase())}
                          </li>
                        ))
                      : list.length
                        ? list.map((p) => (
                            <li key={p.id} className="text-[13px] leading-snug text-zinc-700">
                              {p.title}
                              {p.origin && (
                                <span className="mt-0.5 block text-[11px] text-emerald-700" title="Learned from a decision a person recorded">
                                  learned · {p.origin}
                                </span>
                              )}
                            </li>
                          ))
                        : <li className="text-[13px] text-zinc-500">Nothing yet</li>}
                    {tier === "never" && list.length > 0 && never.map((n) => (
                      <li key={n} className="text-[13px] leading-snug text-zinc-700">
                        {n.replace(/^./, (c) => c.toUpperCase())}
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            );
          })}
        </ol>
        <p className="mt-4 border-t border-zinc-100 pt-3 text-[12.5px] text-zinc-600">
          Observe → ask → commit, earned after {earned} clean approvals; payments, bank details and contracts never.
        </p>
      </Card>
    </section>
  );
}
