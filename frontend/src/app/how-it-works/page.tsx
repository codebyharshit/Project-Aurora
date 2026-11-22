import type { Metadata } from "next";
import { Cta, Eyebrow, H2, PageHero, Section, SiteShell, Tile } from "@/components/Site";

export const metadata: Metadata = {
  title: "How it works · Aurora",
  description: "Goal → process → agents → people. One specialised agent per business task, shared state, deterministic money decisions.",
};

const STEPS = ["Order", "Confirm", "Ship", "Track", "Receive", "Pack", "Sell"];

const LOOP = [
  { t: "Intake", d: "Watches the customer’s files and mailbox every minute; unknown files are mapped by the Schema Mapper." },
  { t: "Read", d: "Scans, handwriting and PDFs in any language become facts, each with its source and confidence." },
  { t: "Plan", d: "ERP view vs reality, worked backwards from the deadline, with what-ifs and each fix’s last useful moment." },
  { t: "Detect", d: "Matching agents check stock, confirmations, releases and tracking; AI Risk Triage catches anything new." },
  { t: "Decide", d: "Known problems follow a playbook; new ones go to the Investigator. The policy’s approver gets one notice." },
  { t: "Act", d: "The Chaser emails the supplier, the Negotiation agent works within the mandate, Tracking follows the goods." },
];

const AGENTS: [string, string, string][] = [
  ["Data Intake", "Watches sources; understands unknown files", "AI + code"],
  ["Document Reader", "Scans, handwriting, PDFs in any language → facts with confidence", "AI"],
  ["Order Confirmation", "Supplier confirmation vs PO; orders nobody confirmed", "code"],
  ["Stock Truth", "Paper vs ERP: wrong receipts, warehouse remarks, goods without an order", "code + AI"],
  ["Release Gate", "Rejected lots, banned revisions, expired supplier releases", "code"],
  ["Tracking", "Short shipments, cargo at port, silent carriers, tracker vs ERP", "code + AI"],
  ["Launch Planner", "Backwards plan, ERP view vs reality, what-ifs", "code"],
  ["Sourcing", "Options priced and ranked by customers protected per euro", "code"],
  ["Approvals", "Parses policy and org chart; routes to the right available person", "AI + code"],
  ["Supplier Chaser", "Emails in the supplier’s language, reminds once, reads every reply", "AI"],
  ["Negotiation", "Accept · counter · answer · escalate within the mandate", "AI + rules"],
  ["Investigator", "Tool-using agent for unknown problems → options and a draft playbook", "AI agent"],
  ["Decision Copilot", "One-sentence headline and goal line per case", "AI + code"],
  ["Onboarding", "Proposes goal, rules and autonomy from the customer’s files", "AI"],
];

const TIERS = [
  { t: "Observe", a: "Read, reconcile, plan, rank, correct the planning view", p: "—" },
  { t: "Ask", a: "Prepare a question that commits the company to nothing", p: "One click: let the agent ask" },
  { t: "Commit", a: "Options, prices, timing, draft, approver named", p: "The policy’s approver approves" },
  { t: "Review", a: "Investigator researches a new kind of problem with tools", p: "Decides; can save it as a playbook" },
  { t: "Never", a: "Flag and explain: payments, bank details, contracts", p: "Verifies through a known contact" },
];

export default function Page() {
  return (
    <SiteShell active="/how-it-works">
      <PageHero
        eyebrow="How it works"
        title="Goal → process → agents → people"
        sub="One specialised agent per business task, on every step of the customer’s process. Agents share state through a case store, not one long prompt. Language, reading and judgement are AI; numbers, approvals and money are deterministic code."
      />

      <Section>
        <Eyebrow>The process</Eyebrow>
        <div className="mt-3">
          <H2 sub="At Soony only two of seven steps had a system. Everything else was email, PDFs, paper and a spreadsheet. Now every step has an agent.">
            Seven steps, every one covered
          </H2>
        </div>
        <ol className="mt-10 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {STEPS.map((s, i) => (
            <li key={s} className="rounded-lg bg-zinc-50 px-3 py-3 ring-1 ring-inset ring-zinc-200/80">
              <span className="tnum text-[12px] text-zinc-400">0{i + 1}</span>
              <p className="text-[14px] font-medium text-zinc-900">{s}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section tone="muted">
        <Eyebrow>The loop</Eyebrow>
        <div className="mt-3">
          <H2 sub="Runs on every new file and every supplier reply. Re-running without new data changes nothing, and human decisions survive every refresh.">
            From a file drop to a truck on the road
          </H2>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {LOOP.map((l, i) => (
            <Tile key={l.t} kicker={`0${i + 1}`} title={l.t}>
              {l.d}
            </Tile>
          ))}
        </div>
      </Section>

      <Section>
        <Eyebrow>The team</Eyebrow>
        <div className="mt-3">
          <H2 sub="Named for the business task each one owns. See them live on the AI team page.">
            14 agents, one job each
          </H2>
        </div>
        <div className="mt-10 overflow-x-auto rounded-xl ring-1 ring-zinc-200/80">
          <table className="w-full min-w-[560px] text-left text-[14px]">
            <thead className="bg-zinc-50 text-[12px] uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">Agent</th>
                <th className="px-4 py-3 font-medium">Task</th>
                <th className="px-4 py-3 font-medium">Kind</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {AGENTS.map(([n, t, k]) => (
                <tr key={n}>
                  <td className="whitespace-nowrap px-4 py-2.5 font-medium text-zinc-900">{n}</td>
                  <td className="px-4 py-2.5 text-zinc-600">{t}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-zinc-500">{k}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section tone="muted">
        <Eyebrow>Human in the loop</Eyebrow>
        <div className="mt-3">
          <H2 sub="Each playbook has a tier. After 3 approvals without edits, the approver may let it run alone. “Never” stays never.">
            When agents act alone, and when they ask
          </H2>
        </div>
        <div className="mt-10 grid gap-3">
          {TIERS.map((t) => (
            <div key={t.t} className="grid gap-1 rounded-xl bg-white px-5 py-4 ring-1 ring-zinc-200/80 sm:grid-cols-[120px_1fr_1fr] sm:gap-6">
              <p className="text-[14px] font-semibold text-zinc-900">{t.t}</p>
              <p className="text-[14px] text-zinc-600">{t.a}</p>
              <p className="text-[14px] text-zinc-500">{t.p}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <div className="grid gap-4 md:grid-cols-3">
          <Tile kicker="New data drops" title="Nothing to rebuild">
            Every file is cached by SHA-256 and the whole pipeline re-runs. The Schema Mapper picked up format changes (CSV → JSON)
            with no code change.
          </Tile>
          <Tile kicker="Messy data" title="Contradictions are the signal">
            Paper beats a stale ERP only with evidence. Low-confidence or number-format-suspect readings go to review instead
            of the plan.
          </Tile>
          <Tile kicker="Stack" title="Small, boring, deployed">
            Python · FastAPI · SQLite · pandas · OpenAI (provider-neutral, Claude supported) · Gmail · Next.js. Backend on
            Railway, frontend on Vercel.
          </Tile>
        </div>
      </Section>

      <Cta title="Watch the agents work" sub="The AI team page shows each agent’s live activity on Soony’s data." />
    </SiteShell>
  );
}
