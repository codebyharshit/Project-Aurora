"use client";

import { useMemo, useState } from "react";
import { useInbox } from "@/lib/api";
import { eur, num, shortEdition } from "@/lib/format";
import { type DerivedInbox, inboxFor, scopeOf } from "@/lib/people";
import type { ApproveResult, CaseSummary, Person } from "@/lib/types";
import { firstName } from "@/lib/viewAs";
import { type Confirmation, ConfirmationBanner } from "./Confirmation";
import { AskRow, DecideRow, DecisionRow } from "./DecisionRow";
import { Collapsible, FlightRow } from "./Flight";
import { editionList, humanize } from "./Story";
import { Avatar, Card, Pulse, StepLabel } from "./ui";

/** Home as one person: the sentence that matters, then only their items. */
export function PersonView({
  name,
  cases,
  owners,
  people,
  onOpen,
}: {
  name: string;
  cases: CaseSummary[];
  owners: Record<string, string[]>;
  people: Person[] | undefined;
  onOpen: (id: string) => void;
}) {
  const { data: inbox, error: inboxErr } = useInbox(name);
  const derived = useMemo(() => inboxFor(name, cases, owners), [name, cases, owners]);
  const box: DerivedInbox = inbox && !inboxErr ? inbox : derived;
  const person = people?.find((p) => p.name === name);
  const scope = person ? scopeOf(person) : inbox?.person?.scope || inbox?.person?.role || "";

  const [done, setDone] = useState<Confirmation | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);
  const approve = box.approve.filter((c) => !hidden.includes(`${c.id}:${c.status}`));
  const live = { ...box, approve };
  const head = inbox?.headline ? { title: inbox.headline, sub: null } : headlineFor(name, live);

  function approved(c: CaseSummary, result: ApproveResult, by: string) {
    setDone({
      title: humanize(c.recommendation?.title || c.title),
      by,
      result,
      steps: c.explanation?.after_approve || [],
      playbookId: c.playbook_id,
    });
    setHidden((h) => [...h, `${c.id}:${c.status}`]);
  }

  const nothing = !approve.length && !box.decide.length && !box.ask.length && !box.in_flight.length;

  return (
    <div className="mx-auto max-w-[920px] space-y-7">
      <div className="flex items-start gap-4">
        <Avatar name={name} size={44} tone="blue" />
        <div className="min-w-0">
          <p className="text-[13px] text-zinc-500">
            <span className="font-medium text-zinc-700">{name}</span>
            {scope && <span> · {scope}</span>}
          </p>
          <h1 className="mt-1 text-[22px] font-semibold leading-snug tracking-tight text-soony-ink">{head.title}</h1>
          {head.sub && <p className="mt-1 text-[15px] leading-relaxed text-zinc-600">{head.sub}</p>}
        </div>
      </div>

      {done && <ConfirmationBanner c={done} setC={setDone} />}

      {nothing && !done && (
        <Card className="flex items-center gap-3 px-6 py-6 text-[15px] text-zinc-600">
          <Pulse tone="green" />
          Nothing for you right now. The agents will bring you the next decision when there is one.
        </Card>
      )}

      {approve.length > 0 && (
        <section>
          <StepLabel right={<span className="text-xs text-zinc-400">most customers protected first</span>}>
            Sign off · {approve.length}
          </StepLabel>
          <div className="mt-3 space-y-3">
            {approve.map((c) => (
              <DecisionRow key={c.id} c={c} name={name} onOpen={onOpen} onApproved={(r, by) => approved(c, r, by)} />
            ))}
          </div>
        </section>
      )}

      {box.decide.length > 0 && (
        <section>
          <StepLabel right={<span className="text-xs text-zinc-400">new kinds of problems · your decision becomes the playbook</span>}>
            Decide · {box.decide.length}
          </StepLabel>
          <div className="mt-3 space-y-3">
            {box.decide.map((c) => (
              <DecideRow key={c.id} c={c} onOpen={onOpen} />
            ))}
          </div>
        </section>
      )}

      {box.ask.length > 0 && (
        <section>
          <StepLabel right={<span className="text-xs text-zinc-400">one email each · nothing to approve</span>}>
            Agents handle alone · {box.ask.length}
          </StepLabel>
          <Card className="mt-3">
            <ul>
              {box.ask.map((c, i) => (
                <AskRow key={c.id} c={c} name={name} onOpen={onOpen} first={i === 0} />
              ))}
            </ul>
          </Card>
        </section>
      )}

      {(box.in_flight.length > 0 || (inbox?.agents_for_you?.length ?? 0) > 0) && (
        <section>
          <StepLabel right={<span className="text-xs text-zinc-400">signed off · the agents follow up</span>}>
            Agents working for you · {box.in_flight.length + (inbox?.agents_for_you?.length ?? 0)}
          </StepLabel>
          <Card className="mt-3">
            {inbox?.agents_for_you?.length ? (
              <ul>
                {inbox.agents_for_you.map((a, i) => (
                  <li key={i} className="flex items-start gap-3 border-t border-zinc-100 px-5 py-2.5 first:border-t-0">
                    <Pulse />
                    <span className="min-w-0 flex-1 text-[13px] text-zinc-700">
                      <span className="font-medium text-zinc-900">{a.name}</span> · {a.text}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
            <ul className={inbox?.agents_for_you?.length ? "" : "-mt-px"}>
              {box.in_flight.map((c) => (
                <FlightRow key={c.id} c={c} onOpen={onOpen} />
              ))}
            </ul>
          </Card>
        </section>
      )}

      {box.done.length > 0 && (
        <Collapsible title="Done & watching" count={box.done.length} sub="Delivered, verified or decided; counted in the plan.">
          <ul>
            {box.done.map((c) => (
              <FlightRow key={c.id} c={c} onOpen={onOpen} />
            ))}
          </ul>
        </Collapsible>
      )}
    </div>
  );
}

/** "Paul, 1 decision needs you. Approving it protects 3,750 Collector's copies for €16,800." */
function headlineFor(name: string, box: DerivedInbox): { title: string; sub: string | null } {
  const first = firstName(name);
  const n = box.approve.length + box.decide.length;
  if (n === 0) {
    const k = box.ask.length + box.in_flight.length;
    return {
      title: k
        ? `${first}, nothing needs you. Agents are handling ${num(k)} ${k === 1 ? "item" : "items"} for you.`
        : `${first}, nothing needs you right now.`,
      sub: null,
    };
  }
  const title = `${first}, ${num(n)} ${n === 1 ? "decision needs" : "decisions need"} you.`;
  if (!box.approve.length)
    return {
      title,
      sub: `${num(box.decide.length)} ${box.decide.length === 1 ? "is a new kind of problem" : "are new kinds of problems"}; the Investigator has a recommendation ready for you.`,
    };
  const copies: Record<string, number> = {};
  let cost = 0;
  for (const c of box.approve) {
    const serves = c.why?.serves?.length
      ? c.why.serves.map((s) => ({ name: shortEdition(s.name), qty: s.copies }))
      : editionList(c.explanation?.benefit?.copies).filter((x) => x.qty > 0);
    for (const s of serves) copies[s.name] = (copies[s.name] || 0) + s.qty;
    cost += c.why?.cost_eur ?? c.explanation?.benefit?.cost_eur ?? c.recommendation?.cost_eur ?? 0;
  }
  const list = Object.entries(copies)
    .sort((a, b) => Number(/collector/i.test(b[0])) - Number(/collector/i.test(a[0])))
    .map(([k, v]) => `${num(v)} ${k}`);
  const what = list.length ? `protects ${list.join(" and ")} copies` : "keeps the records right";
  const verb = box.approve.length === 1 ? "Approving it" : `Approving the ${num(box.approve.length)}`;
  const extra = box.decide.length ? ` ${num(box.decide.length)} more ${box.decide.length === 1 ? "needs" : "need"} your judgement.` : "";
  return { title, sub: `${verb} ${what}${cost ? ` for ${eur(cost)}` : ""}.${extra}` };
}
