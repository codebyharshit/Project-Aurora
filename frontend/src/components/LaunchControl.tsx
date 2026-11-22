"use client";

import { useCallback, useMemo, useState } from "react";
import { API_URL, useAgents, useCases, useOverview, usePeople } from "@/lib/api";
import { openByStep, processOf } from "@/lib/agents";
import { editionNames } from "@/lib/derive";
import { OPEN, peopleWithWork, useOwners } from "@/lib/people";
import { useViewAs } from "@/lib/viewAs";
import { AgentsFeed } from "./AgentsFeed";
import { CaseDrawer } from "./CaseDrawer";
import { Header, StatusRow } from "./Header";
import { PersonView } from "./PersonView";
import { ProcessStrip } from "./ProcessStrip";
import { Card, Pulse } from "./ui";
import { VerdictCard } from "./VerdictCard";
import { WhoMustAct } from "./WhoMustAct";

/** Soony's launch room. Everyone sees the verdict, the process and who must act; a person sees only their items. */
export function LaunchControl() {
  const { data: ov, error: ovErr } = useOverview();
  const { data: cases, error: casesErr } = useCases();
  const { data: people } = usePeople();
  const { data: agentsData } = useAgents();
  const [who, setWho] = useViewAs();
  const owners = useOwners(cases, people);
  const [openId, setOpenId] = useState<string | null>(null);
  const close = useCallback(() => setOpenId(null), []);

  const names = useMemo(() => editionNames(ov), [ov]);
  const work = useMemo(() => peopleWithWork(people || [], cases || [], owners), [people, cases, owners]);
  const counts = useMemo(() => Object.fromEntries(work.map((w) => [w.person.name, w.count])), [work]);
  const process = processOf(agentsData);
  const agents = agentsData?.agents || [];
  const open = useMemo(() => openByStep(process, cases, OPEN), [process, cases]);
  const offline = (ovErr || casesErr) && !ov;

  return (
    <div className="min-h-screen">
      <Header ov={ov} counts={counts} />
      <main className="mx-auto max-w-[1120px] px-5 pb-20 pt-4">
        <div className="mb-5">
          <StatusRow ov={ov} />
        </div>
        {offline ? (
          <Offline />
        ) : !ov || !cases ? (
          <Loading />
        ) : who ? (
          <PersonView key={who} name={who} cases={cases} owners={owners} people={people} onOpen={setOpenId} />
        ) : (
          <div className="space-y-5">
            <VerdictCard ov={ov} cases={cases} owners={owners} />
            <ProcessStrip process={process} agents={agents} open={open} />
            <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.2fr_1fr]">
              <WhoMustAct work={work} onPick={setWho} />
              <AgentsFeed agents={agents} />
            </div>
          </div>
        )}
      </main>
      <CaseDrawer id={openId} names={names} onClose={close} />
    </div>
  );
}

function Loading() {
  return (
    <div className="space-y-5">
      <Card className="h-[220px] p-6">
        <div className="h-3 w-48 animate-pulse rounded bg-zinc-100" />
        <div className="mt-4 h-6 w-[520px] max-w-full animate-pulse rounded bg-zinc-100" />
        <div className="mt-8 grid grid-cols-3 gap-10">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-3">
              <div className="h-2 animate-pulse rounded-full bg-zinc-100" />
              <div className="h-2 animate-pulse rounded-full bg-zinc-100" />
            </div>
          ))}
        </div>
      </Card>
      <Card className="flex items-center gap-3 px-6 py-8 text-[15px] text-zinc-500">
        <Pulse tone="amber" />
        Agents are reading delivery notes, order confirmations and the ERP, and pricing every gap against Sunday 20:00…
      </Card>
    </div>
  );
}

function Offline() {
  return (
    <Card className="mx-auto mt-16 max-w-lg px-6 py-8 text-center">
      <p className="text-sm font-medium text-zinc-900">Can’t reach the agents</p>
      <p className="mt-1 text-[13px] text-zinc-500">
        Aurora’s backend isn’t answering at <code className="rounded bg-zinc-100 px-1 py-0.5 text-xs">{API_URL}</code>.
        Start it, or set <code className="rounded bg-zinc-100 px-1 py-0.5 text-xs">NEXT_PUBLIC_API_URL</code>. This page
        retries every 5 seconds.
      </p>
    </Card>
  );
}
