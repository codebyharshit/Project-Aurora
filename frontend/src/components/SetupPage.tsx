"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { api, fileUrl, useOverview, useSetup } from "@/lib/api";
import { docName, resolvePath, prettyName } from "@/lib/evidence";
import { eur, num, when, whenLong } from "@/lib/format";
import { useName } from "@/lib/useName";
import { useViewAs } from "@/lib/viewAs";
import type { Setup, SetupSectionKey } from "@/lib/types";
import { Header } from "./Header";
import { btn, Card, cx, Icon, type IconName, Pulse, Spinner, Tip } from "./ui";

const DEFAULT_FLOW: SetupSectionKey[] = ["goal", "rules", "autonomy", "data", "sources"];

/** Who confirms: the person viewing the room, else the remembered name. */
function useConfirmer(): string {
  const [who] = useViewAs();
  const [me] = useName();
  return who || me || "";
}

export function SetupPage() {
  const { data: ov } = useOverview();
  const { data, error } = useSetup();
  const flow = data?.flow?.length ? data.flow : DEFAULT_FLOW;
  const progress = data?.progress ?? {
    confirmed: flow.filter((k) => !!data?.confirmations?.[k]).length,
    total: flow.length,
  };
  const STEP: Record<SetupSectionKey, (p: { d: Setup; n: number }) => React.ReactElement> = {
    goal: GoalStep,
    rules: RulesStep,
    autonomy: AutonomyStep,
    data: DataStep,
    sources: SourcesStep,
  };

  return (
    <div className="min-h-screen">
      <Header ov={ov} />
      <main className="mx-auto max-w-[960px] px-5 pb-20 pt-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-semibold tracking-tight text-soony-ink">How Aurora is set up for Soony</h1>
            <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-zinc-600">
              Goal first, then the rules, then what the agents may do alone. The Onboarding agent read Soony’s own files
              and proposed all of it; confirm each step, or change the source document and Aurora re-reads it.
            </p>
          </div>
          {data && (
            <div className="min-w-[180px]">
              <p className="tnum text-[13px] text-zinc-600">
                <span className={cx("font-semibold", progress.confirmed === progress.total ? "text-emerald-700" : "text-zinc-900")}>
                  {progress.confirmed} of {progress.total}
                </span>{" "}
                confirmed
              </p>
              <div className="mt-1.5 flex gap-1">
                {flow.map((k) => (
                  <span
                    key={k}
                    className={cx("h-1.5 flex-1 rounded-full", data.confirmations?.[k] ? "bg-emerald-500" : "bg-zinc-200")}
                    title={k}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        {error && !data ? (
          <Card className="mt-8 px-6 py-8 text-sm text-zinc-600">Couldn’t load the setup. Is the backend running?</Card>
        ) : !data ? (
          <Card className="mt-8 flex items-center gap-3 px-6 py-8 text-[15px] text-zinc-600">
            <Pulse tone="amber" />
            The Onboarding agent is reading the memo, the approval policy and the org chart…
          </Card>
        ) : (
          <div className="relative mt-8 space-y-6 before:absolute before:bottom-6 before:left-[15px] before:top-6 before:w-px before:bg-zinc-200">
            {flow.map((k, i) => {
              const C = STEP[k];
              return C ? <C key={k} d={data} n={i + 1} /> : null;
            })}
            <Coverage d={data} />
          </div>
        )}
      </main>
    </div>
  );
}

/* ───────── frame ───────── */

function Step({
  n,
  section,
  title,
  explain,
  sources,
  d,
  children,
}: {
  n: number;
  section: SetupSectionKey;
  title: string;
  explain: string;
  sources?: string[];
  d: Setup;
  children: React.ReactNode;
}) {
  return (
    <section id={section} className="relative scroll-mt-20 pl-12">
      <span className="tnum absolute left-0 top-5 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full bg-soony-blue text-[13px] font-semibold text-white ring-4 ring-zinc-50">
        {n}
      </span>
      <Card>
        <div className="px-6 pb-2 pt-5">
          <h2 className="text-[18px] font-semibold tracking-tight text-zinc-900">{title}</h2>
          <p className="mt-0.5 text-[14px] text-zinc-600">{explain}</p>
        </div>
        <div className="px-6 py-4">{children}</div>
        {sources && sources.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-zinc-100 px-6 py-3">
            <span className="mr-1 text-xs text-zinc-500">Read from</span>
            {sources.map((s) => (
              <FileChip key={s} path={s} />
            ))}
          </div>
        )}
        <ConfirmFooter section={section} d={d} />
      </Card>
    </section>
  );
}

function ConfirmFooter({ section, d }: { section: SetupSectionKey; d: Setup }) {
  const conf = d.confirmations?.[section];
  const me = useConfirmer();
  const [typed, setTyped] = useState<string | null>(null);
  const by = typed ?? me;
  const [state, setState] = useState<"idle" | "sending" | "error">("idle");
  const { mutate } = useSWRConfig();

  async function confirm() {
    if (!by.trim()) return;
    setState("sending");
    try {
      await api.confirmSetup(section, by.trim());
      await mutate("/api/setup");
      setState("idle");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-xl border-t border-zinc-100 bg-zinc-50/70 px-6 py-3">
      <p className="flex items-center gap-2 text-[13px] text-zinc-600">
        <Icon name="spark" className="h-3.5 w-3.5 text-zinc-500" />
        Proposed by the Onboarding agent
        {conf && (
          <span className="inline-flex items-center gap-1 text-emerald-700">
            · <Icon name="check" className="h-3.5 w-3.5" /> Confirmed by {conf.by} {when(conf.at)}
          </span>
        )}
      </p>
      {!conf && (
        <div className="flex items-center gap-2">
          {state === "error" && <span className="text-xs text-red-600">Couldn’t confirm</span>}
          <input
            value={by}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="Your name"
            aria-label="Confirm as"
            className="w-36 rounded-lg border-0 bg-white px-2.5 py-1.5 text-[13px] ring-1 ring-inset ring-zinc-200 outline-none placeholder:text-zinc-400 focus:ring-2 focus:ring-soony-blue"
          />
          <button className={btn.primary} onClick={confirm} disabled={state === "sending" || !by.trim()}>
            {state === "sending" ? <Spinner className="border-zinc-500 border-t-white" /> : <Icon name="check" className="h-3.5 w-3.5" />}
            Confirm
          </button>
        </div>
      )}
    </div>
  );
}

/* ───────── 1. Sources ───────── */

const SOURCE_ICON: Record<string, IconName> = { "File portal": "doc", Mailbox: "mail", People: "person" };

function SourcesStep({ d, n }: { d: Setup; n: number }) {
  return (
    <Step
      n={n}
      section="sources"
      d={d}
      title="Sources"
      explain="Where Aurora reads from and who it talks to. Nothing is copied into a new system."
    >
      <ul className="grid gap-3 sm:grid-cols-3">
        {d.sections.sources.items.map((s) => (
          <li key={s.kind} className="rounded-lg p-3.5 ring-1 ring-inset ring-zinc-200">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-[14px] font-medium text-zinc-900">
                <Icon name={SOURCE_ICON[s.kind] || "doc"} className="text-zinc-500" />
                {s.kind}
              </span>
              <span
                className={cx(
                  "rounded-full px-2 py-0.5 text-[11px] font-medium",
                  s.status === "connected" ? "bg-emerald-50 text-emerald-700" : "bg-zinc-100 text-zinc-600",
                )}
              >
                {s.status}
              </span>
            </div>
            <p className="mt-2 truncate text-xs text-zinc-600" title={s.detail}>
              {s.detail.replace(/^https?:\/\//, "")}
            </p>
            {s.note && <p className="mt-1 text-xs text-zinc-500">{s.note}</p>}
          </li>
        ))}
      </ul>
    </Step>
  );
}

/* ───────── 2. Data ───────── */

function DataStep({ d, n }: { d: Setup; n: number }) {
  const data = d.sections.data;
  const docs = data.documents;
  const [tables, setTables] = useState(false);
  const [allLearned, setAllLearned] = useState(false);
  const learned = allLearned ? data.learned_sources : data.learned_sources.slice(0, 4);
  const types = Object.entries(docs.by_type).sort((a, b) => b[1] - a[1]);
  return (
    <Step
      n={n}
      section="data"
      d={d}
      title="Data understood"
      explain="What the agents can read: documents in any language, and ERP exports even when the columns are new."
    >
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <p className="tnum text-[28px] font-semibold tracking-tight text-zinc-900">
          {num(docs.total)} <span className="text-[15px] font-normal text-zinc-600">documents read</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(docs.by_language)
            .sort((a, b) => b[1] - a[1])
            .map(([l, n]) => (
              <span key={l} className="tnum rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-700">
                {l} <span className="text-zinc-500">{n}</span>
              </span>
            ))}
        </div>
      </div>
      <p className="tnum mt-2 text-[13px] text-zinc-600">
        {types.map(([t, n], i) => (
          <span key={t}>
            {i > 0 && " · "}
            {num(n)} {t.replace(/_/g, " ")}
            {n === 1 ? "" : "s"}
          </span>
        ))}
      </p>

      {data.learned_sources.length > 0 && (
        <div className="mt-5 rounded-lg bg-emerald-50/50 p-4 ring-1 ring-inset ring-emerald-200/70">
          <p className="flex items-center gap-2 text-[14px] font-medium text-zinc-900">
            <Icon name="spark" className="h-4 w-4 text-emerald-600" />
            Understood automatically by the Schema Mapper
          </p>
          <ul className="mt-3 space-y-2.5">
            {learned.map((s) => (
              <LearnedRow key={s.path} s={s} />
            ))}
          </ul>
          {data.learned_sources.length > 4 && (
            <button className={cx(btn.quiet, "mt-2 text-xs")} onClick={() => setAllLearned(!allLearned)}>
              {allLearned ? "Show fewer" : `Show all ${data.learned_sources.length} files`}
            </button>
          )}
        </div>
      )}

      {data.pending_confirmation.length > 0 && (
        <div className="mt-4 rounded-lg bg-amber-50/50 p-4 ring-1 ring-inset ring-amber-200/80">
          <p className="flex items-center gap-2 text-[14px] font-medium text-zinc-900">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            Waiting for your confirmation
          </p>
          <ul className="mt-3 space-y-2.5">
            {data.pending_confirmation.map((s) => (
              <LearnedRow key={s.path} s={s} confirm />
            ))}
          </ul>
        </div>
      )}

      <button className={cx(btn.quiet, "mt-4")} onClick={() => setTables(!tables)}>
        <Icon name="chevron" className={cx("h-3.5 w-3.5 transition", tables && "rotate-90")} />
        <span className="text-[13px]">{tables ? "Hide" : "Show"} the {data.tables.length} tables Aurora builds</span>
      </button>
      {tables && (
        <table className="tnum mt-2 w-full animate-fade text-left text-[13px]">
          <thead className="text-[11px] uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="py-1.5 font-medium">Table</th>
              <th className="py-1.5 text-right font-medium">Rows</th>
              <th className="py-1.5 pl-6 font-medium">Files</th>
            </tr>
          </thead>
          <tbody>
            {data.tables.map((t) => (
              <tr key={t.table} className="border-t border-zinc-100 align-top">
                <td className="py-2 text-zinc-800">{t.table.replace(/_/g, " ")}</td>
                <td className="py-2 text-right text-zinc-600">{num(t.rows)}</td>
                <td className="py-2 pl-6 text-xs text-zinc-600">
                  {t.configured.length > 0 && <span>{t.configured.length} configured</span>}
                  {t.configured.length > 0 && t.learned.length > 0 && " · "}
                  {t.learned.length > 0 && (
                    <Tip tip={t.learned.map(prettyName).join(", ")}>
                      <span className="text-emerald-700">{t.learned.length} learned</span>
                    </Tip>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Step>
  );
}

function LearnedRow({ s, confirm }: { s: Setup["sections"]["data"]["learned_sources"][number]; confirm?: boolean }) {
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const me = useConfirmer();
  const { mutate } = useSWRConfig();
  async function go() {
    setState("sending");
    try {
      await api.confirmSource(s.path, me || "Launch team", s.table);
      setState("done");
      mutate("/api/setup");
    } catch {
      setState("error");
    }
  }
  return (
    <li className="flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-x-2 text-[13px]">
          <FileChip path={s.path} />
          <Icon name="arrow" className="h-3 w-3 text-zinc-300" />
          <span className="font-medium text-zinc-800">{s.table.replace(/_/g, " ")}</span>
          <span className={cx("tnum text-xs", s.confidence >= 0.9 ? "text-emerald-700" : "text-amber-700")}>
            {Math.round(s.confidence * 100)}% sure
          </span>
        </p>
        <p className="mt-1 line-clamp-2 text-xs leading-snug text-zinc-600" title={s.reason}>
          {s.reason}
        </p>
      </div>
      {confirm &&
        (state === "done" ? (
          <span className="flex items-center gap-1 text-xs text-emerald-700">
            <Icon name="check" className="h-3.5 w-3.5" /> Confirmed
          </span>
        ) : (
          <button className={btn.secondary} onClick={go} disabled={state === "sending"}>
            {state === "sending" ? "Confirming…" : state === "error" ? "Retry" : "Confirm"}
          </button>
        ))}
    </li>
  );
}

/* ───────── 3. Goal ───────── */

/** "… text. Source: a.docx." → ["… text.", ["a.docx"]] */
function splitSource(s: string): [string, string[]] {
  const m = s.match(/^(.*?)\s*Sources?:\s*(.+?)\.?$/);
  if (!m) return [s, []];
  return [m[1], m[2].split(/;\s*/).filter(Boolean)];
}

function GoalStep({ d, n }: { d: Setup; n: number }) {
  const g = d.sections.goal.proposal;
  const [meaning, meaningSrc] = splitSource(g.deadline_meaning);
  const [metric] = splitSource(g.success_metric);
  const allSources = Array.from(
    new Set([...meaningSrc, ...g.products.flatMap((p) => (p.source || "").split(/;\s*/).filter(Boolean))]),
  );
  return (
    <Step
      n={n}
      section="goal"
      d={d}
      title="Goal"
      explain="What Aurora optimises for, in Soony’s own words."
      sources={allSources}
    >
      <p className="text-[19px] font-medium leading-snug tracking-tight text-zinc-900">{g.objective}</p>

      <dl className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-zinc-500">Deadline</dt>
          <dd className="mt-0.5 text-[15px] font-medium text-zinc-900">{whenLong(g.deadline_at)}</dd>
          <dd className="mt-0.5 text-[13px] leading-snug text-zinc-600">{meaning}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500">Site</dt>
          <dd className="mt-0.5 text-[15px] font-medium text-zinc-900">{g.site}</dd>
          <dt className="mt-3 text-xs text-zinc-500">Success means</dt>
          <dd className="mt-0.5 text-[13px] leading-snug text-zinc-600">{metric}</dd>
        </div>
      </dl>

      <p className="mt-5 text-xs text-zinc-500">Products, in priority order</p>
      <ol className="mt-2 space-y-2">
        {[...g.products]
          .sort((a, b) => a.priority - b.priority)
          .map((p) => (
            <li key={p.id} className="flex gap-3 rounded-lg p-3 ring-1 ring-inset ring-zinc-200">
              <span className="tnum inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-semibold text-zinc-600">
                {p.priority}
              </span>
              <div className="min-w-0">
                <p className="text-[14px] font-medium text-zinc-900">
                  {p.name}
                  {p.demand != null && <span className="tnum ml-2 font-normal text-zinc-500">{num(p.demand)} pre-ordered</span>}
                </p>
                {p.reason && <p className="mt-0.5 text-[13px] leading-snug text-zinc-600">{p.reason}</p>}
              </div>
            </li>
          ))}
      </ol>

      {g.tolerances.length > 0 && (
        <>
          <p className="mt-5 text-xs text-zinc-500">Limits Aurora respects</p>
          <ul className="mt-2 space-y-1.5">
            {g.tolerances.map((t, i) => {
              const [text] = splitSource(t);
              return (
                <li key={i} className="flex items-start gap-2 text-[13px] leading-snug text-zinc-700">
                  <Icon name="shield" className="mt-0.5 h-3.5 w-3.5 text-zinc-500" />
                  {text}
                </li>
              );
            })}
          </ul>
        </>
      )}

      {g.open_questions.length > 0 && (
        <div className="mt-5 rounded-lg bg-amber-50/60 p-4 ring-1 ring-inset ring-amber-200/80">
          <p className="text-[13px] font-medium text-amber-900">Open questions for you</p>
          <ul className="mt-2 space-y-1.5">
            {g.open_questions.map((q, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-snug text-zinc-700">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.sections.goal.checks?.length > 0 && (
        <div className="mt-5">
          <p className="text-xs text-zinc-500">Matches the live config</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {d.sections.goal.checks.map((c) => (
              <Tip
                key={c.item}
                tip={
                  <>
                    Proposed: {fmtVal(c.proposed)}
                    <span className="block">Live: {fmtVal(c.live)}</span>
                  </>
                }
              >
                <li
                  className={cx(
                    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs",
                    c.match ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700",
                  )}
                >
                  <Icon name={c.match ? "check" : "close"} className="h-3 w-3" />
                  {c.item}
                  {!c.match && <span className="text-red-500/80">· {fmtVal(c.proposed)} vs {fmtVal(c.live)}</span>}
                </li>
              </Tip>
            ))}
          </ul>
        </div>
      )}
    </Step>
  );
}

function fmtVal(v: unknown): string {
  if (Array.isArray(v)) return v.join(" → ");
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return whenLong(v);
  return String(v);
}

/* ───────── 4. Rules ───────── */

function RulesStep({ d, n }: { d: Setup; n: number }) {
  const r = d.sections.rules;
  const limits = r.approval_limits;
  return (
    <Step
      n={n}
      section="rules"
      d={d}
      title="Rules"
      explain="Read from your own documents: who may approve what, who is away, and what may never ship."
      sources={r.sources}
    >
      <p className="text-xs text-zinc-500">Approval limits</p>
      <ol className="mt-2 space-y-1">
        {limits.map((l, i) => (
          <li key={i} className="flex items-center gap-3">
            <div
              className="h-7 rounded-md bg-zinc-100"
              style={{ width: `${18 + (i / Math.max(1, limits.length - 1)) * 40}%` }}
            >
              <span className="flex h-full items-center px-2.5 text-[13px] text-zinc-800">{l.role}</span>
            </div>
            <span className="tnum text-[13px] text-zinc-600">
              {l.max_eur_exclusive != null ? `below ${eur(l.max_eur_exclusive)}` : l.jointly_with ? `above that, jointly with the ${l.jointly_with}` : "no limit"}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-zinc-500">
        Exceptions: {r.exception_role}. Final say on quality release: {r.quality_final_say}. Conditional supplier releases
        last {r.conditional_release_days} days.
      </p>

      <p className="mt-6 text-xs text-zinc-500">People</p>
      <ul className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {r.people.map((p) => (
          <li key={p.name + p.role} className="flex items-start gap-2.5">
            <Initials name={p.name} />
            <div className="min-w-0">
              <p className="text-[13px] text-zinc-900">
                <span className="font-medium">{p.name}</span>
                <span className="text-zinc-600">
                  {" "}
                  · {p.role}
                  {p.category ? `, ${p.category}` : ""}
                  {p.site ? ` (${p.site})` : ""}
                </span>
              </p>
              {p.vacant_until_start && (
                <p className="mt-0.5 inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800 ring-1 ring-inset ring-amber-200">
                  Vacant until {p.from_date ? whenDate(p.from_date) : "start"} · stand-in: {r.exception_role}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
      {r.site_leads.length > 0 && (
        <p className="mt-3 text-[13px] text-zinc-600">
          {r.site_leads.map((s) => (
            <span key={s.site}>
              Dock slots at {s.site}: <span className="font-medium text-zinc-900">{s.lead}</span>
              {s.deputy && <span className="text-zinc-600"> (deputy {s.deputy})</span>}
            </span>
          ))}
        </p>
      )}

      <p className="mt-6 text-xs text-zinc-500">Priority and release rules</p>
      <ul className="mt-2 space-y-2">
        {[...r.priority_rules, ...r.release_rules].map((x, i) => (
          <li key={i} className="border-l-2 border-zinc-200 pl-3 text-[13px] leading-snug text-zinc-700">
            “{x.text}”{" "}
            <a
              href={fileUrl(resolvePath(x.source))}
              target="_blank"
              rel="noreferrer"
              className="whitespace-nowrap text-xs text-zinc-500 hover:text-zinc-700 hover:underline"
            >
              {docName(x.source)}
            </a>
          </li>
        ))}
      </ul>
    </Step>
  );
}

function whenDate(iso: string): string {
  const dt = new Date(iso);
  return Number.isNaN(dt.getTime())
    ? iso
    : dt.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "Europe/Berlin" });
}


function Initials({ name }: { name: string }) {
  const i = name
    .replace(/^(Dr\.|Prof\.)\s+/i, "")
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("");
  return (
    <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white text-[10px] font-semibold text-zinc-600 ring-1 ring-zinc-200">
      {i}
    </span>
  );
}

/* ───────── 5. Autonomy ───────── */

const TIERS: { tier: string; title: string; explain: string }[] = [
  { tier: "observe", title: "Observe", explain: "Agents watch and record; nobody is bothered." },
  { tier: "ask", title: "Ask", explain: "Agents may email a supplier with a question on their own." },
  { tier: "commit", title: "Commit", explain: "Agents prepare it; the person the policy names approves with one click." },
  { tier: "never", title: "Never automatic", explain: "Always a human, whatever the track record." },
];

function AutonomyStep({ d, n }: { d: Setup; n: number }) {
  const a = d.sections.autonomy;
  return (
    <Step
      n={n}
      section="autonomy"
      d={d}
      title="Autonomy"
      explain="What the agents may do alone, what needs you, and how they earn more trust over time."
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {TIERS.map((t) => {
          const list = a.playbooks.filter((p) => p.tier === t.tier);
          return (
            <div
              key={t.tier}
              className={cx(
                "rounded-lg p-3.5 ring-1 ring-inset",
                t.tier === "commit" ? "ring-amber-200 bg-amber-50/40" : t.tier === "never" ? "ring-zinc-300" : "ring-zinc-200",
              )}
            >
              <p className="text-[14px] font-medium text-zinc-900">{t.title}</p>
              <p className="text-xs text-zinc-600">{t.explain}</p>
              <ul className="mt-2.5 space-y-1">
                {list.length ? (
                  list.map((p) => (
                    <li key={p.id} className="text-[13px] leading-snug text-zinc-700">
                      {p.title}
                    </li>
                  ))
                ) : (
                  <li className="text-[13px] text-zinc-500">
                    {t.tier === "never" ? a.never.join(", ") : "Nothing yet"}
                  </li>
                )}
              </ul>
            </div>
          );
        })}
      </div>

      <dl className="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2">
        <Fact label="Mandate">
          Agents may negotiate up to +{Math.round(a.mandate_tolerance * 100)}% on the approved price, at most{" "}
          {a.max_agent_rounds} rounds, then they come back to you.
        </Fact>
        <Fact label="Earned autonomy">
          After {a.earned_autonomy_after} approvals without changes, Aurora offers to run that kind of decision by itself.
        </Fact>
        <Fact label="Notifications">{a.notifications.replace(/^./, (c) => c.toUpperCase())}.</Fact>
        <Fact label="Never automatic">{a.never.map((x) => x.replace(/^./, (c) => c.toUpperCase())).join(", ")}.</Fact>
        <Fact label="Unknown problems">{a.unknown_problems}.</Fact>
      </dl>
    </Step>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-0.5 text-[13px] leading-snug text-zinc-700">{children}</dd>
    </div>
  );
}

/* ───────── Coverage ───────── */

function Coverage({ d }: { d: Setup }) {
  const families = d.sections.autonomy.playbooks.map((p) => p.title);
  return (
    <section className="relative pl-12">
      <span className="absolute left-0 top-5 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full bg-white text-zinc-600 ring-1 ring-zinc-200">
        <Icon name="shield" className="h-4 w-4" />
      </span>
      <Card className="px-6 py-5">
        <h2 className="text-[16px] font-semibold text-zinc-900">Coverage</h2>
        <p className="mt-0.5 text-[13px] text-zinc-600">Problem families the agents handle today.</p>
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {families.map((f) => (
            <li key={f} className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs text-zinc-700">
              {f}
            </li>
          ))}
          <li className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-900 ring-1 ring-inset ring-amber-200">
            Unknown problems → review → new playbook
          </li>
        </ul>
        <p className="mt-4 border-t border-zinc-100 pt-3 text-[13px] text-zinc-600">
          Same product, new config: toy maker before Christmas · automotive start of production · pharma launch · retail
          season
        </p>
      </Card>
    </section>
  );
}

function FileChip({ path }: { path: string }) {
  return (
    <a
      href={fileUrl(resolvePath(path))}
      target="_blank"
      rel="noreferrer"
      title={path}
      className="inline-flex max-w-[260px] items-center gap-1 rounded-md bg-white px-1.5 py-0.5 text-xs text-zinc-600 ring-1 ring-inset ring-zinc-200 transition hover:text-zinc-900 hover:ring-zinc-400"
    >
      <Icon name="doc" className="h-3 w-3 text-zinc-500" />
      <span className="truncate">{prettyName(path)}</span>
    </a>
  );
}
