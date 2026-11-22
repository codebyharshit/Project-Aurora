import Link from "next/link";
import { cx } from "./ui";

/** Two slanted red bars and SOONY in heavy italic, Soony blue. */
export function SoonyWordmark({ className, size = 17 }: { className?: string; size?: number }) {
  const bar = Math.round(size * 1.05);
  return (
    <span className={cx("inline-flex items-center gap-2", className)} aria-label="Soony">
      <span className="flex items-center gap-[3px]" aria-hidden>
        <span className="block w-[3px] -skew-x-[22deg] rounded-[1px] bg-soony-red" style={{ height: bar }} />
        <span className="block w-[3px] -skew-x-[22deg] rounded-[1px] bg-soony-red" style={{ height: bar }} />
      </span>
      <span
        className="font-extrabold italic leading-none tracking-[-0.045em] text-soony-blue"
        style={{ fontSize: size }}
      >
        SOONY
      </span>
    </span>
  );
}

/** The existing Aurora mark, small, with a quiet "powered by". */
export function AuroraMark({ className }: { className?: string }) {
  return (
    <Link href="/" className={cx("inline-flex items-center gap-1.5 whitespace-nowrap", className)} title="Aurora">
      <Mark className="h-4 w-4" />
      <span className="text-[11px] text-zinc-400">
        powered by <span className="font-medium text-zinc-500">Aurora</span>
      </span>
    </Link>
  );
}

export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cx("h-6 w-6", className)} aria-hidden>
      <defs>
        <linearGradient id="aur" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#18181b" />
          <stop offset="1" stopColor="#52525b" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="7" fill="url(#aur)" />
      <path d="M5.5 16.5c2-5 4.2-8 6.5-8s4.5 3 6.5 8" stroke="#f59e0b" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}
