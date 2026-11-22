// All times are shown in the site's timezone (Hamburg), whatever the viewer's machine says.
const TZ = "Europe/Berlin";

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const pf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export const MINUS = "−";

export function num(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const s = nf.format(Math.abs(n));
  return n < 0 ? `${MINUS}${s}` : s;
}

export function signed(n: number): string {
  return n > 0 ? `+${num(n)}` : num(n);
}

export function eur(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return `€${num(n)}`;
}

export function pct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return `${pf.format(n)}%`;
}

const dayTime = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: TZ,
});
const dayDateTime = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: TZ,
});
const timeOnly = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: TZ,
});

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "Sun 11:26" */
export function when(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? dayTime.format(d).replace(",", "") : "–";
}

/** "Sun 22 Nov 20:00" */
export function whenLong(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? dayDateTime.format(d).replace(/,/g, "") : "–";
}

/** "21:31" */
export function clock(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? timeOnly.format(d) : "–";
}

export function msBetween(a: string | null | undefined, b: string | null | undefined): number | null {
  const da = parse(a);
  const db = parse(b);
  if (!da || !db) return null;
  return db.getTime() - da.getTime();
}

/** "23h 00m", "5h 26m", "40m" */
export function duration(ms: number | null): string {
  if (ms === null) return "–";
  const neg = ms < 0;
  const total = Math.round(Math.abs(ms) / 60000);
  const h = Math.floor(total / 60);
  const m = total % 60;
  const s = h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
  return neg ? `${MINUS}${s}` : s;
}

export function shortEdition(name: string): string {
  return name.replace(/\s+Edition$/i, "");
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${num(n)} ${n === 1 ? one : many}`;
}

/** "Category Lead Collector's Items vacant until …" → is the role vacant? */
export function isVacant(role: string, notes: string[]): boolean {
  return notes.some((n) => n.toLowerCase().includes(role.toLowerCase()) && /vacant/i.test(n));
}
