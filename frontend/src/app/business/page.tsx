import type { Metadata } from "next";
import { Cta, Eyebrow, H2, PageHero, Section, SiteShell, Tile } from "@/components/Site";

export const metadata: Metadata = {
  title: "Business case · Aurora",
  description: "Every company with a hard date and outside suppliers has a Soony weekend. Aurora prices the gap and closes it.",
};

const MARKETS = [
  { t: "Game and electronics launches", d: "A street date, a dozen parts, suppliers in four languages." },
  { t: "Toys before Christmas", d: "One season; missing the shelf means missing the year." },
  { t: "Automotive start of production", d: "A line that cannot start without the last supplier part." },
  { t: "Pharma launches", d: "Regulated release dates, packaging revisions, batch approvals." },
];

export default function Page() {
  return (
    <SiteShell active="/business">
      <PageHero
        eyebrow="Business case"
        title="Every company with a hard date has a Soony weekend"
        sub="When the date can’t move and the parts come from outside, the last 20% decides the launch. Today that 20% lives in email, PDFs, paper and someone’s spreadsheet. Aurora turns it into decisions priced in euros and closed with the right person’s approval."
      />

      <Section>
        <Eyebrow>Why Soony pays</Eyebrow>
        <div className="mt-3">
          <H2>Three approvals protect ~€880k for €18,840</H2>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-zinc-900 p-6 text-white">
            <p className="tnum text-[36px] font-semibold tracking-tight">~€880k</p>
            <p className="mt-1 text-[14px] text-zinc-400">of Collector’s pre-orders that would otherwise be refunded</p>
          </div>
          <div className="rounded-xl bg-white p-6 ring-1 ring-zinc-200/80">
            <p className="tnum text-[36px] font-semibold tracking-tight text-zinc-900">€18,840</p>
            <p className="mt-1 text-[14px] text-zinc-500">the cost of the three fixes the agents found, priced and routed</p>
          </div>
          <div className="rounded-xl bg-white p-6 ring-1 ring-zinc-200/80">
            <p className="tnum text-[36px] font-semibold tracking-tight text-zinc-900">0</p>
            <p className="mt-1 text-[14px] text-zinc-500">IT projects: Aurora reads the files Soony already has</p>
          </div>
        </div>
        <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-zinc-600">
          Collector’s goes from 91.8% to 100% of launch, Standard from 95.0% to 98.9%, within the 2% delay Soony’s senior buyer
          told us is acceptable as long as pre-orders are served.
        </p>
      </Section>

      <Section tone="muted">
        <Eyebrow>Why now</Eyebrow>
        <div className="mt-3">
          <H2 sub="Two things changed. Models can now read a handwritten correction on a Polish delivery note and write back to that supplier in Polish. And tool-using agents can investigate a problem nobody defined in advance.">
            The messy part is finally automatable
          </H2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          <Tile title="The pain is universal">Only 2 of Soony’s 7 process steps had a system. That is normal, not an exception.</Tile>
          <Tile title="The cost is concrete">Every gap is priced as euros at risk per hour until its last useful moment.</Tile>
          <Tile title="The buyer is clear">Head of Procurement and CPO: “No more surprises.”</Tile>
        </div>
      </Section>

      <Section>
        <Eyebrow>Beyond Soony</Eyebrow>
        <div className="mt-3">
          <H2 sub="Everything about a customer lives in one config folder and their own documents: sources, deadline, products, tolerances, policy, people. The product code contains no customer values.">
            A new customer is a config folder, not a project
          </H2>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {MARKETS.map((m) => (
            <Tile key={m.t} title={m.t}>
              {m.d}
            </Tile>
          ))}
        </div>
        <ol className="mt-10 grid gap-3 sm:grid-cols-4">
          {["Connect their files and mailbox", "Agents map the data and read the documents", "Onboarding agent proposes goal, rules, autonomy", "A person confirms each section"].map(
            (s, i) => (
              <li key={s} className="flex gap-3 text-[14px] text-zinc-600">
                <span className="tnum flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-100 text-[12px] font-semibold text-amber-800">
                  {i + 1}
                </span>
                {s}
              </li>
            ),
          )}
        </ol>
      </Section>

      <Section tone="muted">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <Eyebrow>Business model</Eyebrow>
            <div className="mt-3">
              <H2 sub="Priced against what a launch is worth, not per seat: the people who approve are few, the value they protect is large.">
                Per active launch or season, plus a platform fee
              </H2>
            </div>
          </div>
          <div className="grid gap-4">
            <Tile title="It compounds">
              Every decision can be saved as a playbook, and every approval earns a playbook more autonomy. The playbook library
              gets better with every customer.
            </Tile>
            <Tile title="It lands without IT">
              Reads the email, PDFs, scans and spreadsheets the customer already has. The ERP is never changed.
            </Tile>
          </div>
        </div>
      </Section>

      <Cta title="Soony is customer one" sub="See the launch it is saving, live." />
    </SiteShell>
  );
}
