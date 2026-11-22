import type { Metadata } from "next";
import Link from "next/link";
import { Cta, Eyebrow, H2, Section, SiteShell, Tile } from "@/components/Site";

export const metadata: Metadata = {
  title: "Aurora · AI agents that keep your launch on time",
  description:
    "Your ERP says you're fine. Your paperwork says you're not. Aurora's agents find the gap, price it against your deadline, and close it with your approval.",
};

const STATS = [
  { n: "299", l: "documents read: scans, handwriting, PDFs" },
  { n: "5", l: "languages, incl. Korean, Chinese and Polish" },
  { n: "21/21", l: "known problems re-found from raw files" },
  { n: "0", l: "customer values hardcoded in the product" },
];

const FOUND = [
  "An art-book receipt booked as 80,000 that the delivery note corrects by hand to 8,000",
  "A statue lot that failed inspection but still counts as usable stock",
  "28,000 of 48,000 game cards flown, announced only in a Korean notice",
  "A container waiting at the port while the tracker still says “in transit”",
  "A banned sleeve revision in stock and on a supplier’s order confirmation",
  "An order nobody confirmed, from a supplier that just announced a shutdown",
];

export default function Page() {
  return (
    <SiteShell>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-zinc-200/70 bg-gradient-to-b from-zinc-50 to-white">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 left-1/2 h-[420px] w-[900px] -translate-x-1/2 rounded-full bg-amber-400/15 blur-3xl"
        />
        <div className="relative mx-auto max-w-[1120px] px-5 pb-20 pt-20 sm:pt-28">
          <Eyebrow>AI agents for launch-critical supply</Eyebrow>
          <h1 className="mt-4 max-w-3xl text-balance text-[40px] font-semibold leading-[1.05] tracking-tight text-zinc-900 sm:text-[60px]">
            Your ERP says you’re fine. Your paperwork says you’re not.
          </h1>
          <p className="mt-6 max-w-2xl text-pretty text-[18px] leading-relaxed text-zinc-600">
            Aurora is a team of specialised AI agents that finds the gap, prices it against your next deadline, and closes
            it within your own rules and with your approval: it reads every document, routes each decision to the one
            person your policy names, negotiates with suppliers in their language, and tracks the goods until they arrive.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/"
              className="inline-flex h-11 items-center gap-2 rounded-full bg-zinc-900 px-5 text-[14px] font-semibold text-white transition hover:bg-zinc-700"
            >
              Open the live launch room <span aria-hidden>→</span>
            </Link>
            <Link
              href="/how-it-works"
              className="inline-flex h-11 items-center rounded-full bg-white px-5 text-[14px] font-medium text-zinc-800 ring-1 ring-inset ring-zinc-300 transition hover:bg-zinc-50"
            >
              How it works
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-b border-zinc-200/70">
        <div className="mx-auto grid max-w-[1120px] grid-cols-2 gap-px bg-zinc-200/70 sm:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.l} className="bg-white px-5 py-7">
              <p className="tnum text-[30px] font-semibold tracking-tight text-zinc-900">{s.n}</p>
              <p className="mt-1 text-[13px] leading-snug text-zinc-500">{s.l}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Three moves */}
      <Section>
        <Eyebrow>What Aurora does</Eyebrow>
        <div className="mt-3">
          <H2 sub="One goal, one deadline, one team of agents working backwards from it.">Find it. Price it. Close it.</H2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          <Tile kicker="01 · Find" title="The gap between system and reality">
            Every delivery note, scan, supplier email and spreadsheet is read and reconciled against the ERP, with the source
            and confidence on every number.
          </Tile>
          <Tile kicker="02 · Price" title="Against the deadline that matters">
            A backwards plan from the launch ranks every problem by euros at risk per hour until its last useful moment, and
            prices each fix.
          </Tile>
          <Tile kicker="03 · Close" title="With the right person’s approval">
            One click from the approver your own policy names. Then agents email the supplier, negotiate within the mandate
            and track the goods to the dock.
          </Tile>
        </div>
      </Section>

      {/* Soony result */}
      <Section tone="muted">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-start">
          <div>
            <Eyebrow>First customer · Soony</Eyebrow>
            <div className="mt-3">
              <H2 sub="Grand Heist 6 goes on sale Sunday 20:00. Trucks leave Hamburg whether the boxes are packed or not. Soony’s ERP said 100% of everything would ship.">
                “We find out at the dock.”
              </H2>
            </div>
            <p className="mt-4 text-[14px] text-zinc-500">Dr. Maren Vogt, Head of Procurement, Soony</p>
          </div>
          <div className="overflow-hidden rounded-xl bg-white ring-1 ring-zinc-200/80">
            <table className="w-full text-left text-[14px]">
              <thead className="bg-zinc-50 text-[12px] uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Edition</th>
                  <th className="px-4 py-3 font-medium">ERP says</th>
                  <th className="px-4 py-3 font-medium">Reality</th>
                  <th className="px-4 py-3 font-medium text-zinc-900">With Aurora</th>
                </tr>
              </thead>
              <tbody className="tnum divide-y divide-zinc-100">
                <tr>
                  <td className="px-4 py-3 font-medium text-zinc-900">Collector’s</td>
                  <td className="px-4 py-3 text-zinc-500">100%</td>
                  <td className="px-4 py-3 text-red-600">91.8%</td>
                  <td className="px-4 py-3 font-semibold text-emerald-700">100%</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-medium text-zinc-900">Standard</td>
                  <td className="px-4 py-3 text-zinc-500">100%</td>
                  <td className="px-4 py-3 text-red-600">95.0%</td>
                  <td className="px-4 py-3 font-semibold text-emerald-700">98.9%</td>
                </tr>
              </tbody>
            </table>
            <p className="border-t border-zinc-100 px-4 py-3 text-[13px] text-zinc-500">
              3 approvals, <span className="tnum font-medium text-zinc-800">€18,840</span>. Standard stays within the agreed 2%
              tolerance; 6,800 copies follow after launch.
            </p>
          </div>
        </div>

        <div className="mt-14">
          <h3 className="text-[15px] font-semibold text-zinc-900">Found from the raw files, nothing hardcoded</h3>
          <ul className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {FOUND.map((f) => (
              <li key={f} className="flex gap-3 text-[14px] leading-relaxed text-zinc-600">
                <span aria-hidden className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      </Section>

      {/* Trust */}
      <Section>
        <Eyebrow>Built to be trusted</Eyebrow>
        <div className="mt-3">
          <H2 sub="Agents act alone only where it is safe. Asking is free; committing needs the right person; money is never automatic.">
            Autonomy you can switch on, one playbook at a time
          </H2>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Tile title="Every number has evidence">The document, the line and the reading confidence. Doubtful readings are flagged, not applied.</Tile>
          <Tile title="The ERP is never changed">Corrections live in the planning view and are offered as proposed bookings.</Tile>
          <Tile title="Your policy decides who decides">Approval limits, roles and stand-ins are parsed from your own policy and org chart.</Tile>
          <Tile title="Earned autonomy">After 3 approvals without edits, the approver can let a playbook run on its own.</Tile>
        </div>
      </Section>

      <Cta title="See it running on Soony’s real data" sub="The launch room is live: the verdict, who must act, and what the agents are doing right now." />
    </SiteShell>
  );
}
