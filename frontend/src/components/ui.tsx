"use client";

import type { ReactNode } from "react";
import type { CaseStatus } from "@/lib/types";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={cx(
        "rounded-xl bg-white ring-1 ring-zinc-200/80 shadow-[0_1px_2px_rgba(24,24,27,0.04)]",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function SectionTitle({
  children,
  count,
  accent,
  right,
  hint,
}: {
  children: ReactNode;
  count?: number;
  accent?: boolean;
  right?: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <div className="flex items-baseline gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-500">{children}</h2>
        {count !== undefined && (
          <span
            className={cx(
              "tnum inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1.5 text-[11px] font-semibold",
              accent && count > 0 ? "bg-amber-500 text-white" : "bg-zinc-100 text-zinc-500",
            )}
          >
            {count}
          </span>
        )}
        {hint && <span className="text-xs text-zinc-400">{hint}</span>}
      </div>
      {right}
    </div>
  );
}

/** Small grey tag telling where a number comes from: ERP, Scan, Policy, Plan … */
export function Src({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex items-center rounded px-1 py-px text-[10px] font-medium uppercase tracking-wide text-zinc-400 ring-1 ring-inset ring-zinc-200"
    >
      {children}
    </span>
  );
}

export function Chip({
  children,
  tone = "neutral",
  title,
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "amber" | "green" | "red" | "ghost" | "blue";
  title?: string;
  className?: string;
}) {
  const tones = {
    neutral: "bg-zinc-100 text-zinc-700",
    amber: "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200",
    green: "bg-emerald-50 text-emerald-700",
    red: "bg-red-50 text-red-700",
    ghost: "text-zinc-500 ring-1 ring-inset ring-zinc-200",
    blue: "bg-soony-blue/8 text-soony-blue",
  } as const;
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Hover tooltip, pure CSS. */
export function Tip({ children, tip, className }: { children: ReactNode; tip: ReactNode; className?: string }) {
  return (
    <span className={cx("group/tip relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-0 z-30 mb-2 w-max max-w-[320px] translate-y-1 rounded-lg bg-zinc-900 px-2.5 py-1.5 text-xs leading-snug text-zinc-100 opacity-0 shadow-lg transition group-hover/tip:translate-y-0 group-hover/tip:opacity-100"
      >
        {tip}
      </span>
    </span>
  );
}

export const btn = {
  primary:
    "inline-flex items-center justify-center gap-1.5 rounded-lg bg-soony-blue px-3.5 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-soony-blue/90 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40",
  secondary:
    "inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 ring-1 ring-inset ring-zinc-200 transition hover:bg-zinc-50 hover:text-zinc-900 disabled:opacity-40",
  quiet:
    "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-sm text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40",
  link: "inline-flex items-center gap-1 text-sm text-zinc-500 underline-offset-2 transition hover:text-zinc-900 hover:underline",
};

const STATUS: Record<CaseStatus, { label: string; tone: "neutral" | "amber" | "green" | "red" | "ghost" }> = {
  AWAITING_APPROVAL: { label: "Needs approval", tone: "amber" },
  READY_TO_ASK: { label: "Agent can ask", tone: "ghost" },
  AWAITING_HUMAN_REVIEW: { label: "Needs judgement", tone: "amber" },
  AWAITING_SUPPLIER: { label: "Waiting for supplier", tone: "neutral" },
  EXECUTING: { label: "In progress", tone: "neutral" },
  VERIFIED: { label: "Done · verified", tone: "green" },
  ESCALATED: { label: "Escalated · no supplier reply", tone: "red" },
  DECIDED: { label: "Decided", tone: "green" },
  AGREED: { label: "Agreed · waiting for waybill", tone: "neutral" },
  IN_TRANSIT: { label: "On the way", tone: "neutral" },
  DELIVERED: { label: "Delivered", tone: "green" },
  SUPERSEDED: { label: "Replaced by a newer case", tone: "ghost" },
};

export function StatusPill({ status }: { status: CaseStatus }) {
  const s = STATUS[status] || { label: status, tone: "neutral" as const };
  return <Chip tone={s.tone}>{s.label}</Chip>;
}

export function statusLabel(status: CaseStatus): string {
  return STATUS[status]?.label || status;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        "inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-zinc-300 border-t-zinc-700",
        className,
      )}
    />
  );
}

/** Calm pulsing dot for "agents are working" states. */
export function Pulse({ tone = "zinc" }: { tone?: "zinc" | "amber" | "green" }) {
  const c = tone === "amber" ? "bg-amber-500" : tone === "green" ? "bg-emerald-500" : "bg-zinc-400";
  return (
    <span className="relative inline-flex h-2 w-2">
      <span className={cx("absolute inline-flex h-full w-full animate-ping rounded-full opacity-50", c)} />
      <span className={cx("relative inline-flex h-2 w-2 rounded-full", c)} />
    </span>
  );
}

type IconName =
  | "arrow"
  | "check"
  | "clock"
  | "doc"
  | "image"
  | "mail"
  | "person"
  | "refresh"
  | "chevron"
  | "close"
  | "spark"
  | "shield"
  | "search"
  | "truck"
  | "chart"
  | "bolt"
  | "external"
  | "target"
  | "people"
  | "flag";

const PATHS: Record<IconName, string> = {
  arrow: "M5 12h14M13 6l6 6-6 6",
  check: "M5 12.5l4.5 4.5L19 7",
  clock: "M12 7v5l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  doc: "M7 3h7l5 5v13H7zM14 3v5h5M9.5 13h6M9.5 17h6",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 9.5h.01",
  mail: "M4 6h16v12H4zM4 7l8 6 8-6",
  person: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 20c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5",
  refresh: "M20 11a8 8 0 00-14.5-4.5M4 4v4h4M4 13a8 8 0 0014.5 4.5M20 20v-4h-4",
  chevron: "M9 6l6 6-6 6",
  close: "M6 6l12 12M18 6L6 18",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6",
  shield: "M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  truck: "M3 6h11v10H3zM14 10h4l3 3v3h-7M7 19a2 2 0 100-4 2 2 0 000 4zM17 19a2 2 0 100-4 2 2 0 000 4z",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  target: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8zM12 12h.01",
  people: "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM2.5 20c.8-3.5 3.3-5 6.5-5s5.7 1.5 6.5 5M16 4.5a3.5 3.5 0 010 6.5M21.5 20c-.5-2.8-2-4.3-4.5-4.8",
  flag: "M5 21V4M5 4h13l-2.5 4L18 12H5",
};

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cx("h-4 w-4 shrink-0", className)}
      aria-hidden
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

export function Avatar({ name, size = 18, tone = "zinc" }: { name: string; size?: number; tone?: "zinc" | "blue" }) {
  const initials = name
    .replace(/^(Dr\.|Prof\.)\s+/i, "")
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        tone === "blue" ? "bg-soony-blue text-white" : "bg-white text-zinc-600 ring-1 ring-zinc-200",
      )}
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.38)) }}
    >
      {initials}
    </span>
  );
}

/** Numbered section label: "2 · Your decisions". */
export function StepLabel({ n, children, right }: { n?: number | string; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2.5">
        {n !== undefined && (
          <span className="tnum inline-flex h-5 w-5 items-center justify-center rounded-full bg-soony-ink text-[11px] font-semibold text-white">
            {n}
          </span>
        )}
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-zinc-500">{children}</h2>
      </div>
      {right}
    </div>
  );
}

export type { IconName };
