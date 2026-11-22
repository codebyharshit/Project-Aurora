import Link from "next/link";

// Local copy: ui.tsx is a client module, and this file renders on the server.
const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

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

/** The Aurora mark, small, with a quiet "powered by". */
export function AuroraMark({ className }: { className?: string }) {
  return (
    <Link href="/about" className={cx("inline-flex items-center gap-1.5 whitespace-nowrap", className)} title="About Aurora">
      <Mark style={{ height: 11 }} strokeWidth={2.4} />
      <span className="text-[11px] text-zinc-500">
        powered by <span className="font-medium text-zinc-600">aurora</span>
      </span>
    </Link>
  );
}

export const AURORA_GOLD = "#C98A1C";
export const AURORA_NAVY = "#0F1B2A";

/** The Aurora logo: a gold sun rising over a split horizon line. */
export function Mark({
  className,
  style,
  strokeWidth = 2.6,
}: {
  className?: string;
  style?: React.CSSProperties;
  strokeWidth?: number;
}) {
  return (
    <svg viewBox="0 0 48 26" className={cx("w-auto", className)} style={{ height: 24, ...style }} aria-hidden fill="none" strokeLinecap="round">
      <path d="M7 19.5A17 17 0 0 1 41 19.5" stroke={AURORA_GOLD} strokeWidth={strokeWidth} />
      <path d="M2 23.5H22.4M25.6 23.5H46" stroke={AURORA_NAVY} strokeWidth={strokeWidth} />
    </svg>
  );
}

/** Mark + lowercase "aurora", as in the logo. */
export function AuroraWordmark({ className, size = 15 }: { className?: string; size?: number }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)} aria-label="Aurora">
      <Mark style={{ height: size * 1.1 }} />
      <span className="font-medium leading-none tracking-[-0.01em]" style={{ fontSize: size * 1.15, color: AURORA_NAVY }}>
        aurora
      </span>
    </span>
  );
}
