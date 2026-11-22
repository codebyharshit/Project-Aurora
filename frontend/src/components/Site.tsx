import Link from "next/link";
import type { ReactNode } from "react";

/** Aurora's own pages (landing, how it works, business, team): static, no API, Aurora brand rather than Soony's. */

const NAV = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/business", label: "Business" },
  { href: "/lumi", label: "Team" },
];

function join(...c: (string | false | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function AuroraLogo({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
      <defs>
        <linearGradient id="aur-site" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#18181b" />
          <stop offset="1" stopColor="#52525b" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="7" fill="url(#aur-site)" />
      <path d="M5.5 16.5c2-5 4.2-8 6.5-8s4.5 3 6.5 8" stroke="#f59e0b" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function SiteShell({ active, children }: { active?: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 border-b border-zinc-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1120px] items-center justify-between gap-4 px-5">
          <Link href="/about" className="flex items-center gap-2">
            <AuroraLogo size={24} />
            <span className="text-[15px] font-semibold tracking-tight text-zinc-900">Aurora</span>
          </Link>
          <nav className="hidden items-center gap-1 sm:flex" aria-label="Aurora">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active === n.href ? "page" : undefined}
                className={join(
                  "rounded-full px-3.5 py-1 text-[13px] transition",
                  active === n.href ? "bg-zinc-100 font-medium text-zinc-900" : "text-zinc-600 hover:text-zinc-900",
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <Link
            href="/"
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-zinc-900 px-3.5 text-[13px] font-medium text-white transition hover:bg-zinc-700"
          >
            Live demo <span aria-hidden>→</span>
          </Link>
        </div>
        <nav className="flex justify-center gap-1 border-t border-zinc-100 py-1.5 sm:hidden" aria-label="Aurora (mobile)">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={join("rounded-full px-3 py-0.5 text-[13px]", active === n.href ? "bg-zinc-100 font-medium" : "text-zinc-600")}
            >
              {n.label}
            </Link>
          ))}
        </nav>
      </header>
      <main>{children}</main>
      <footer className="border-t border-zinc-200/80 bg-zinc-50">
        <div className="mx-auto flex max-w-[1120px] flex-col gap-3 px-5 py-8 text-[13px] text-zinc-500 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <AuroraLogo size={18} />
            <span>
              Aurora · built by <Link href="/lumi" className="text-zinc-700 hover:underline">Team LUMI</Link> at START Hack
              Munich 2026
            </span>
          </div>
          <span>Soony, Popstar Studios and Grand Heist 6 are fictional.</span>
        </div>
      </footer>
    </div>
  );
}

export function Section({ children, className, tone }: { children: ReactNode; className?: string; tone?: "muted" }) {
  return (
    <section className={join(tone === "muted" && "border-y border-zinc-200/70 bg-zinc-50", className)}>
      <div className="mx-auto max-w-[1120px] px-5 py-16 sm:py-20">{children}</div>
    </section>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-600">{children}</p>;
}

export function H2({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="max-w-2xl">
      <h2 className="text-balance text-[28px] font-semibold leading-tight tracking-tight text-zinc-900 sm:text-[32px]">
        {children}
      </h2>
      {sub && <p className="mt-3 text-pretty text-[16px] leading-relaxed text-zinc-600">{sub}</p>}
    </div>
  );
}

export function PageHero({ eyebrow, title, sub }: { eyebrow: string; title: ReactNode; sub: ReactNode }) {
  return (
    <section className="border-b border-zinc-200/70 bg-gradient-to-b from-zinc-50 to-white">
      <div className="mx-auto max-w-[1120px] px-5 pb-14 pt-16 sm:pt-20">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="mt-3 max-w-3xl text-balance text-[36px] font-semibold leading-[1.1] tracking-tight text-zinc-900 sm:text-[46px]">
          {title}
        </h1>
        <p className="mt-4 max-w-2xl text-pretty text-[17px] leading-relaxed text-zinc-600">{sub}</p>
      </div>
    </section>
  );
}

export function Tile({ title, children, kicker }: { title: ReactNode; children: ReactNode; kicker?: ReactNode }) {
  return (
    <div className="rounded-xl bg-white p-5 ring-1 ring-zinc-200/80 shadow-[0_1px_2px_rgba(24,24,27,0.04)]">
      {kicker && <p className="text-[12px] font-medium text-amber-700">{kicker}</p>}
      <h3 className="mt-1 text-[15px] font-semibold text-zinc-900">{title}</h3>
      <div className="mt-2 text-[14px] leading-relaxed text-zinc-600">{children}</div>
    </div>
  );
}

export function Cta({ title, sub }: { title: ReactNode; sub: ReactNode }) {
  return (
    <section className="bg-zinc-900">
      <div className="mx-auto flex max-w-[1120px] flex-col items-start gap-6 px-5 py-14 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[24px] font-semibold tracking-tight text-white">{title}</h2>
          <p className="mt-1.5 text-[15px] text-zinc-400">{sub}</p>
        </div>
        <Link
          href="/"
          className="inline-flex h-11 items-center gap-2 rounded-full bg-amber-500 px-5 text-[14px] font-semibold text-zinc-950 transition hover:bg-amber-400"
        >
          Open the live launch room <span aria-hidden>→</span>
        </Link>
      </div>
    </section>
  );
}
