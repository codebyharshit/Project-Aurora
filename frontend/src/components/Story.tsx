"use client";

import { useEffect, useState } from "react";
import { classify, prettyName } from "@/lib/evidence";
import { duration, eur, isVacant, msBetween, num, shortEdition, when } from "@/lib/format";
import type { ApproverChain, CaseSummary, ExplanationFact } from "@/lib/types";
import { cx, Icon, Tip } from "./ui";

export const ESTIMATE_NOTE = "Estimate · value per copy is configured; confirm with the Head of Procurement.";

/** Take IDs out of a sentence meant for people. Keeps the meaning, drops the codes. */
export function humanize(s: string): string {
  return s
    .replace(/\b[A-Z]{4}\d{7}\b/g, "the container")
    .replace(/\b(lot|batch|receipt|PO|po)\s+\d{6,}\b/gi, (_m, w: string) => `the ${w.toLowerCase() === "po" ? "order" : w.toLowerCase()}`)
    .replace(/\b\d{8,}\b/g, "")
    .replace(/\s+Sp\. z o\.o\./g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([,.;:])/g, "$1")
    .trim()
    .replace(/^./, (ch) => ch.toUpperCase());
}

/** Turn "Collector's Edition" keyed maps into a sorted list, Collector's first. */
export function editionList(copies: Record<string, number> | undefined) {
  return Object.entries(copies || {})
    .map(([name, qty]) => ({ name: shortEdition(name), qty }))
    .sort((a, b) => Number(/collector/i.test(b.name)) - Number(/collector/i.test(a.name)));
}

/* ───────── What we found ───────── */

export function Facts({ facts, max = 3 }: { facts: ExplanationFact[]; max?: number }) {
  // "Option: …" facts repeat the recommendation; timing is told in "If you approve".
  const list = facts.filter((f) => !/^option:/i.test(f.text)).slice(0, max);
  if (!list.length) return null;
  return (
    <ul className="space-y-3">
      {list.map((f, i) => (
        <li key={i}>
          {f.system != null && f.truth != null ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Compare label="ERP says" value={f.system} />
              <Icon name="arrow" className="h-3.5 w-3.5 text-zinc-300" />
              <Compare label={paperLabel(f.source)} value={f.truth} strong />
            </div>
          ) : null}
          <p className={cx("text-[14px] leading-relaxed", f.system != null ? "mt-1 text-zinc-500" : "text-zinc-700")}>
            {humanize(f.text)}
          </p>
          <SourceChip source={f.source} className="mt-1.5" />
        </li>
      ))}
    </ul>
  );
}

function Compare({ label, value, strong }: { label: string; value: number; strong?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className={cx("tnum text-lg font-semibold", strong ? "text-zinc-900" : "text-zinc-400 line-through decoration-zinc-300")}>
        {num(value)}
      </span>
    </span>
  );
}

function paperLabel(source: string): string {
  const p = source.toLowerCase();
  if (/receiving|delivery|wz-|sn-/.test(p) && /\.(jpe?g|png)$/.test(p)) return "Delivery note says";
  if (/shipping|advice/.test(p)) return "Shipping advice says";
  if (/inspection/.test(p)) return "Inspection says";
  if (/\.(jpe?g|png)$/.test(p)) return "Scan says";
  if (/\.pdf$/.test(p)) return "Supplier document says";
  return "Paperwork says";
}

/* ───────── Evidence: chip + viewer ───────── */

export function SourceChip({ source, className }: { source: string; className?: string }) {
  const [open, setOpen] = useState(false);
  const item = classify(source);
  if (item.kind === "quote") return null;
  if (item.kind === "ref")
    return (
      <span className={cx("inline-flex items-center gap-1 text-xs text-zinc-400", className)}>
        <Icon name="doc" className="h-3 w-3" />
        {item.label}
      </span>
    );
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={cx(
          "inline-flex max-w-full items-center gap-1.5 rounded-md bg-zinc-50 px-2 py-0.5 text-xs text-zinc-600 ring-1 ring-inset ring-zinc-200 transition hover:bg-white hover:text-zinc-900 hover:ring-zinc-400",
          className,
        )}
        title="Open the document"
      >
        <Icon name={item.kind === "image" ? "image" : "doc"} className="h-3 w-3 text-zinc-400" />
        <span className="truncate">{sourceTitle(item.path)}</span>
      </button>
      {open && <Viewer path={item.path} url={item.url} kind={item.kind} onClose={() => setOpen(false)} />}
    </>
  );
}

function sourceTitle(path: string): string {
  const n = prettyName(path).replace(/\.(jpe?g|png|pdf|csv|json|docx)$/i, "");
  const ext = path.split(".").pop()?.toLowerCase();
  const kind =
    ext === "csv" ? "ERP table" : /^(jpe?g|png)$/.test(ext || "") ? "Scan" : ext === "json" ? "Data" : "Document";
  return `${kind} · ${n}`;
}

function Viewer({
  path,
  url,
  kind,
  onClose,
}: {
  path: string;
  url: string;
  kind: "image" | "pdf" | "file";
  onClose: () => void;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6" role="dialog">
      <div className="absolute inset-0 animate-fade bg-zinc-900/50" onClick={onClose} />
      <div className="relative flex max-h-full w-full max-w-4xl animate-pop flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-100 px-4 py-2.5">
          <span className="truncate text-sm text-zinc-700">{prettyName(path)}</span>
          <span className="flex shrink-0 items-center gap-3 text-xs text-zinc-500">
            <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-zinc-900">
              Open in new tab <Icon name="external" className="h-3 w-3" />
            </a>
            <button onClick={onClose} className="hover:text-zinc-900" aria-label="Close">
              <Icon name="close" />
            </button>
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-zinc-100">
          {kind === "image" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={prettyName(path)} className="mx-auto max-h-[78vh] object-contain" />
          ) : (
            <iframe src={url} title={path} className="h-[78vh] w-full bg-white" />
          )}
        </div>
      </div>
    </div>
  );
}

/* ───────── If you approve / if you do nothing ───────── */

export function Benefit({ c }: { c: CaseSummary }) {
  const b = c.explanation?.benefit;
  const rec = c.recommendation;
  if (!b) return null;
  const list = editionList(b.copies);
  const up = list.filter((x) => x.qty > 0);
  const down = list.filter((x) => x.qty < 0);
  const missing = editionList(c.explanation?.if_not?.copies);
  const late = msBetween(rec?.last_useful_moment, rec?.arrival_at);

  return (
    <div>
      {up.map((x) => (
        <p key={x.name} className="tnum text-[28px] font-semibold leading-none tracking-tight text-emerald-700">
          +{num(x.qty)}
          <span className="ml-2 text-[15px] font-medium tracking-normal text-zinc-700">{x.name} customers served</span>
        </p>
      ))}
      <p className="tnum mt-2.5 text-[14px] text-zinc-600">
        Protects about{" "}
        <Tip tip={ESTIMATE_NOTE}>
          <span className="cursor-help font-medium text-zinc-900 underline decoration-zinc-300 decoration-dotted underline-offset-4">
            {eur(b.eur_protected)}
          </span>
        </Tip>{" "}
        for{" "}
        <Tip tip={rec?.cost_note ? `Cost source: ${rec.cost_note}` : "Estimated cost"}>
          <span className="cursor-help font-medium text-zinc-900">{eur(b.cost_eur)}</span>
        </Tip>
      </p>
      {rec?.arrival_at && (
        <p className={cx("mt-1.5 text-[13px]", b.partial || (late !== null && late > 0) ? "text-amber-700" : "text-zinc-500")}>
          {late !== null && late > 0 ? (
            <>
              Arrives {when(rec.arrival_at)}, {duration(late)} after the ideal time
              {up[0] && missing.find((m) => m.name === up[0].name) && (
                <>
                  {" "}
                  — still saves {num(up[0].qty)} of {num(missing.find((m) => m.name === up[0].name)!.qty)}
                </>
              )}
              .
            </>
          ) : (
            <>
              Ready {when(rec.arrival_at)}, in time
              {rec.last_useful_moment && <> (needed by {when(rec.last_useful_moment)})</>}.
            </>
          )}
        </p>
      )}
      {down.length > 0 && (
        <p className="mt-1.5 text-[13px] text-zinc-400">
          {down.map((x) => `${num(-x.qty)} ${x.name}`).join(", ")} copies wait for later: shared parts go to{" "}
          {up[0]?.name || "the priority edition"} first.
        </p>
      )}
    </div>
  );
}

export function IfNot({ c }: { c: CaseSummary }) {
  const n = c.explanation?.if_not;
  if (!n)
    return <p className="text-[14px] text-zinc-500">No direct effect on Sunday’s numbers, but the records stay wrong.</p>;
  const list = editionList(n.copies);
  return (
    <p className="tnum text-[14px] leading-relaxed text-zinc-700">
      {list.map((x, i) => (
        <span key={x.name}>
          {i > 0 && " and "}
          <span className="font-semibold text-red-600">{num(x.qty)}</span> {x.name}
        </span>
      ))}{" "}
      copies miss the trucks
      {n.eur_at_risk ? (
        <>
          {" "}
          <Tip tip={ESTIMATE_NOTE}>
            <span className="cursor-help text-zinc-500 underline decoration-zinc-300 decoration-dotted underline-offset-4">
              (about {eur(n.eur_at_risk)} at risk)
            </span>
          </Tip>
        </>
      ) : null}
      .
    </p>
  );
}

/* ───────── What happens next ───────── */

export function NextSteps({ steps }: { steps: string[] }) {
  if (!steps.length) return null;
  return (
    <ol className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="flex items-start gap-2.5 text-[14px] leading-snug text-zinc-700">
          <span className="tnum mt-px inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-[11px] font-medium text-zinc-500">
            {i + 1}
          </span>
          {s}
        </li>
      ))}
    </ol>
  );
}

/* ───────── Who approves and why, in words ───────── */

export function policySentence(chain: ApproverChain | null | undefined): string | null {
  const list = chain?.approvers || [];
  if (!list.length) return null;
  const [a, ...rest] = list;
  const who = a.person || a.role;
  let s: string;
  if (a.fallback_for) {
    const vacant = isVacant(a.fallback_for, chain?.notes || []);
    s = `${who} (${a.role}) approves as stand-in${vacant ? `, because the ${a.fallback_for} role is vacant` : ` for the ${a.fallback_for}`}`;
  } else {
    s = `${who} (${a.role}) approves this: ${lowerFirst(a.reason)}`;
  }
  if (rest.length) s += `. ${rest.map((r) => `${r.person || r.role} (${r.role})`).join(" and ")} also signs`;
  return s + ".";
}

function lowerFirst(s: string): string {
  return s && s.length > 1 && s[1] === s[1].toLowerCase() ? s[0].toLowerCase() + s.slice(1) : s;
}
