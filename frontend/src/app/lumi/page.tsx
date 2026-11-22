import type { Metadata } from "next";
import Link from "next/link";
import { Cta, PageHero, Section, SiteShell } from "@/components/Site";

export const metadata: Metadata = {
  title: "Team LUMI · Aurora",
  description: "The people behind Aurora, built at START Hack Munich 2026.",
};

const TEAM = ["Harshit Agarwal", "Zorawar Singh", "Mikail Ugur", "Jakub Walentek", "Antonina Begacheva"];

const TINTS = [
  "bg-amber-100 text-amber-800",
  "bg-sky-100 text-sky-800",
  "bg-emerald-100 text-emerald-800",
  "bg-rose-100 text-rose-800",
  "bg-violet-100 text-violet-800",
];

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2);
}

export default function Page() {
  return (
    <SiteShell active="/lumi">
      <PageHero
        eyebrow="Team LUMI"
        title="Five people, one weekend, one launch to save"
        sub="We built Aurora at START Hack Munich 2026 for the challenge “Keep the Line Running”: a young startup with one paying customer, a hard deadline, and a chance to prove we are worth the contract."
      />

      <Section>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {TEAM.map((name, i) => (
            <li key={name} className="flex flex-col items-center rounded-xl bg-white px-4 py-8 text-center ring-1 ring-zinc-200/80">
              <span className={`flex h-16 w-16 items-center justify-center rounded-full text-[20px] font-semibold ${TINTS[i % TINTS.length]}`}>
                {initials(name)}
              </span>
              <p className="mt-4 text-[15px] font-semibold text-zinc-900">{name}</p>
              <p className="mt-0.5 text-[13px] text-zinc-500">Team LUMI</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section tone="muted">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <h2 className="text-[24px] font-semibold tracking-tight text-zinc-900">And the other team</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-zinc-600">
              Aurora itself is a team: 14 specialised agents, one per business task, from the Document Reader that reads
              handwriting on Polish delivery notes to the Negotiation agent that counters a supplier’s offer within the
              approver’s mandate.
            </p>
            <Link href="/team" className="mt-5 inline-flex items-center gap-1.5 text-[14px] font-medium text-zinc-900 hover:underline">
              Meet the AI team <span aria-hidden>→</span>
            </Link>
          </div>
          <div>
            <h2 className="text-[24px] font-semibold tracking-tight text-zinc-900">Thank you</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-zinc-600">
              To the challenge team and to Soony’s project team for the office hours. “Data is a mess, we find out at the
              dock, and a 1–2% delay is fine as long as pre-orders are served” shaped the goal every agent works toward.
            </p>
          </div>
        </div>
      </Section>

      <Cta title="See what we built" sub="Aurora running live on Soony’s data." />
    </SiteShell>
  );
}
