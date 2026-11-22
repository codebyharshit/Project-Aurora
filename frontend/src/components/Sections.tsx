"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { CORRECTION_KIND } from "@/lib/derive";
import { classify, prettyName, resolvePath } from "@/lib/evidence";
import { fileUrl } from "@/lib/api";
import { num } from "@/lib/format";
import { useName } from "@/lib/useName";
import type { CaseSummary, Correction, Rule } from "@/lib/types";
import { EvidenceLink } from "./Evidence";
import { btn, Card, cx, Icon, Pulse, SectionTitle, StatusPill, Tip } from "./ui";

/* ───────────── Needs your judgement ───────────── */

export function Judgement({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  if (!cases.length) return null;
  return (
    <Card>
      <div className="px-4 pb-2 pt-4">
        <SectionTitle count={cases.length} accent>
          Needs your judgement
        </SectionTitle>
        <p className="mt-1 text-xs text-zinc-500">New problems the agents found that no playbook covers yet.</p>
      </div>
      <ul>
        {cases.map((c) => (
          <ReviewItem key={c.id} c={c} onOpen={onOpen} />
        ))}
      </ul>
    </Card>
  );
}

function ReviewItem({ c, onOpen }: { c: CaseSummary; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-t border-zinc-100 px-4 py-3.5">
      <div className="flex items-start gap-2">
        <span
          className={cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", c.affects_deadline ? "bg-amber-500" : "bg-zinc-300")}
        />
        <div className="min-w-0 flex-1">
          <button
            onClick={() => onOpen(c.id)}
            className="text-left text-sm font-medium leading-snug text-zinc-900 hover:underline hover:decoration-zinc-300 hover:underline-offset-4"
          >
            {c.title}
          </button>
          <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-zinc-600" title={c.summary}>
            {c.summary}
          </p>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-xs text-zinc-500">
              {c.affects_deadline ? "Could affect Sunday" : "After launch · no effect on Sunday"}
            </span>
            {!open && (
              <button className={btn.secondary} onClick={() => setOpen(true)}>
                Decide
              </button>
            )}
          </div>
          {open && <DecideForm caseId={c.id} onCancel={() => setOpen(false)} />}
        </div>
      </div>
    </li>
  );
}

export function DecideForm({
  caseId,
  onCancel,
  initialText = "",
  playbook,
}: {
  caseId: string;
  onCancel?: () => void;
  initialText?: string;
  playbook?: { title: string; steps: string[]; tier: string } | null;
}) {
  const [me, setMe] = useName();
  const [who, setWho] = useState<string | null>(null);
  const [text, setText] = useState(initialText);
  const [save, setSave] = useState(true);
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [saved, setSaved] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const { mutate } = useSWRConfig();
  const name = who ?? me;

  async function submit() {
    if (!text.trim() || !name.trim()) return;
    setState("sending");
    try {
      const r = await api.decide(caseId, { decision: text.trim(), decided_by: name.trim(), save_as_playbook: save });
      const sp = r?.saved_playbook;
      setSaved(sp ? (typeof sp === "string" ? sp : sp.title || sp.id || playbook?.title || "new playbook") : null);
      setMe(name.trim());
      setState("done");
      mutate("/api/overview");
      mutate("/api/cases");
      mutate(`/api/cases/${encodeURIComponent(caseId)}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }

  if (state === "done")
    return (
      <p className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800">
        <Icon name="check" className="h-3.5 w-3.5" />
        Decision recorded.
        {saved ? <> Saved as playbook ‹{saved}›; next time Aurora follows these steps.</> : null}
      </p>
    );

  return (
    <form
      className="mt-3 space-y-3 animate-fade"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label className="block">
        {initialText && <span className="mb-1 block text-xs text-zinc-600">Your decision (prefilled with the Investigator’s recommendation, edit freely)</span>}
        <textarea
          autoFocus={!!onCancel}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={initialText ? 4 : 3}
          placeholder="What should happen? e.g. Confirm EXW Boise in writing and book our forwarder."
          className="w-full resize-y rounded-lg border-0 bg-white px-3 py-2 text-sm leading-relaxed text-zinc-900 ring-1 ring-inset ring-zinc-200 outline-none placeholder:text-zinc-400 focus:ring-2 focus:ring-soony-blue"
        />
      </label>

      <div className="rounded-lg bg-white p-3 ring-1 ring-inset ring-zinc-200">
        <label className="flex cursor-pointer select-none items-center gap-2.5 text-[13px] text-zinc-700">
          <button
            type="button"
            role="switch"
            aria-checked={save}
            onClick={() => setSave(!save)}
            className={cx("relative h-4 w-7 shrink-0 rounded-full transition", save ? "bg-soony-blue" : "bg-zinc-300")}
          >
            <span
              className={cx(
                "absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all",
                save ? "left-3.5" : "left-0.5",
              )}
            />
          </button>
          <span>
            <span className="font-medium text-zinc-900">Save as playbook</span> — next time Aurora follows these steps
          </span>
        </label>
        {save && playbook && (
          <div className="mt-3 border-t border-zinc-100 pt-3">
            <p className="flex flex-wrap items-center gap-2 text-[13px] font-medium text-zinc-900">
              {playbook.title}
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-normal text-zinc-600">
                {TIER_WORD[playbook.tier] || playbook.tier}
              </span>
            </p>
            <ol className="mt-2 space-y-1">
              {playbook.steps.map((st, i) => (
                <li key={i} className="flex gap-2 text-xs leading-snug text-zinc-600">
                  <span className="tnum w-4 shrink-0 text-right text-zinc-500">{i + 1}.</span>
                  {st}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          value={name}
          onChange={(e) => setWho(e.target.value)}
          placeholder="Your name"
          aria-label="Decided by"
          className="min-w-0 flex-1 rounded-lg border-0 bg-white px-3 py-1.5 text-sm ring-1 ring-inset ring-zinc-200 outline-none focus:ring-2 focus:ring-soony-blue"
        />
        {onCancel && (
          <button type="button" className={btn.quiet} onClick={onCancel}>
            Cancel
          </button>
        )}
        <button type="submit" className={btn.primary} disabled={!text.trim() || !name.trim() || state === "sending"}>
          {state === "sending" ? "Recording…" : "Record decision"}
        </button>
      </div>
      {state === "error" && <p className="text-xs text-red-600">Couldn’t record the decision: {err}</p>}
    </form>
  );
}

const TIER_WORD: Record<string, string> = {
  observe: "agents only watch",
  ask: "agents may ask suppliers alone",
  commit: "needs an approval each time",
  never: "never automatic",
};

/* ───────────── Waiting / in progress ───────────── */

export function InFlight({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  return (
    <Card>
      <div className="px-4 pb-2 pt-4">
        <SectionTitle count={cases.length}>Waiting / in progress</SectionTitle>
      </div>
      {cases.length === 0 ? (
        <p className="flex items-center gap-2 border-t border-zinc-100 px-4 py-3.5 text-[13px] text-zinc-600">
          <Pulse />
          Nothing in flight. Approved decisions show up here while agents carry them out.
        </p>
      ) : (
        <ul>
          {cases.map((c) => (
            <li key={c.id} className="border-t border-zinc-100">
              <button
                onClick={() => onOpen(c.id)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-zinc-50"
              >
                <span className="min-w-0 flex-1 truncate text-[13px] text-zinc-800">{c.title}</span>
                {c.status === "AWAITING_SUPPLIER" && <Pulse />}
                <StatusPill status={c.status} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* ───────────── Agents can ask ───────────── */

export function AgentsCanAsk({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string) => void }) {
  if (!cases.length) return null;
  return (
    <div>
      <div className="px-1 pb-2">
        <SectionTitle count={cases.length}>Agents can ask</SectionTitle>
        <p className="mt-1 text-xs text-zinc-500">Small gaps an agent can clear with one email. Open one to send.</p>
      </div>
      <ul className="space-y-1">
        {cases.map((c) => (
          <li key={c.id}>
            <button
              onClick={() => onOpen(c.id)}
              className="group flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-white hover:ring-1 hover:ring-zinc-200"
            >
              <Icon name="mail" className="mt-0.5 h-3.5 w-3.5 text-zinc-500" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-zinc-700">{c.title}</span>
                <span className="block truncate text-xs text-zinc-500">{c.summary}</span>
              </span>
              <Icon name="chevron" className="mt-0.5 h-3.5 w-3.5 text-zinc-300 transition group-hover:text-zinc-500" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ───────────── Rules in force ───────────── */

const KEY_RULE = /\b(must|first|only|no copy|not|final decision|requires)\b/i;

export function RulesInForce({ rules, bare }: { rules: Rule[]; bare?: boolean }) {
  const [all, setAll] = useState(false);
  const ranked = [...rules].sort((a, b) => Number(KEY_RULE.test(b.text)) - Number(KEY_RULE.test(a.text)));
  const shown = all ? ranked : ranked.slice(0, 4);
  if (bare)
    return (
      <ul className="space-y-2.5">
        {ranked.map((r, i) => (
          <li key={i} className="flex items-start gap-2.5">
            <Icon name="shield" className="mt-0.5 h-3.5 w-3.5 text-zinc-500" />
            <span className="min-w-0 text-[13px] leading-snug text-zinc-700">
              {r.text}{" "}
              <a
                href={fileUrl(resolvePath(r.source))}
                target="_blank"
                rel="noreferrer"
                className="whitespace-nowrap text-xs text-zinc-500 underline-offset-2 hover:text-zinc-700 hover:underline"
              >
                {/policy|pp-07/i.test(r.source) ? "Approval policy" : /memo/i.test(r.source) ? "Launch memo" : prettyName(r.source)}
              </a>
            </span>
          </li>
        ))}
      </ul>
    );
  return (
    <div>
      <div className="px-1 pb-2">
        <SectionTitle
          count={rules.length}
          hint="Read from memos and policy"
          right={
            rules.length > 4 && (
              <button className={cx(btn.quiet, "text-xs")} onClick={() => setAll(!all)}>
                {all ? "Show fewer" : "Show all"}
              </button>
            )
          }
        >
          Rules in force
        </SectionTitle>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {shown.map((r, i) => (
          <Tip
            key={i}
            tip={
              <>
                “{r.text}”<span className="mt-1 block text-zinc-500">Source: {prettyName(r.source)}</span>
              </>
            }
          >
            <a
              href={fileUrl(resolvePath(r.source))}
              target="_blank"
              rel="noreferrer"
              className="inline-flex max-w-[300px] items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-xs text-zinc-700 ring-1 ring-inset ring-zinc-200 transition hover:ring-zinc-400"
            >
              <Icon name="shield" className="h-3 w-3 text-zinc-500" />
              <span className="truncate">{r.text.replace(/\.$/, "")}</span>
            </a>
          </Tip>
        ))}
      </div>
    </div>
  );
}

/* ───────────── What we corrected and why ───────────── */

export function CorrectionsList({ items, parts }: { items: Correction[]; parts: Record<string, string> }) {
  return (
    <ul className="animate-fade">
      {items.map((c, i) => (
        <li key={i} className="border-t border-zinc-100 px-4 py-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[13px] font-medium text-zinc-900">{parts[c.part_id] || c.part_id}</span>
            <span
              className={cx(
                "tnum shrink-0 text-[13px] font-medium",
                c.qty < 0 ? "text-red-600" : c.qty > 0 ? "text-emerald-700" : "text-zinc-500",
              )}
            >
              {c.qty === 0 ? "held for review" : c.qty < 0 ? `ERP had ${num(-c.qty)} too many` : `ERP had ${num(c.qty)} too few`}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-zinc-600">
            <span className="text-zinc-700">{CORRECTION_KIND[c.kind] || c.kind.replace(/_/g, " ")}</span> · {c.reason}
          </p>
          {c.evidence.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {c.evidence.map((e, j) => {
                const item = classify(e);
                return item.kind === "quote" ? (
                  <Tip key={j} tip={item.text}>
                    <span className="cursor-default text-xs italic text-zinc-500">“{item.text.slice(0, 48)}…”</span>
                  </Tip>
                ) : (
                  <EvidenceLink key={j} raw={e} />
                );
              })}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function Corrections({ items, parts }: { items: Correction[]; parts: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const applied = items.filter((c) => c.qty !== 0);
  return (
    <Card>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
        aria-expanded={open}
      >
        <div>
          <p className="flex items-center gap-2 text-[15px] font-semibold text-zinc-900">
            What we corrected in the ERP, and why
            <span className="tnum text-[13px] font-normal text-zinc-500">{items.length}</span>
          </p>
          <p className="mt-0.5 text-[13px] text-zinc-600">
            {applied.length} stock figures replaced by what the paperwork says; the rest held for review.
          </p>
        </div>
        <Icon name="chevron" className={cx("h-4 w-4 text-zinc-500 transition", open && "rotate-90")} />
      </button>
      {open && <CorrectionsList items={items} parts={parts} />}
    </Card>
  );
}

