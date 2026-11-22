"use client";

import { useState } from "react";
import { useCase } from "@/lib/api";
import { gains } from "@/lib/derive";
import { clock, duration, eur, isVacant, msBetween, num, signed, when } from "@/lib/format";
import type { CaseDetail as Detail, CaseMessage, CaseStatus, Option } from "@/lib/types";
import { ApproveButton, consequenceFor } from "./ApproveButton";
import { Benefit, Facts, humanize, IfNot, NextSteps, policySentence } from "./Story";
import { EvidenceLink, EvidencePanel } from "./Evidence";
import { GoalLine } from "./GoalLine";
import { DecideForm } from "./Sections";
import { InvestigationBrief } from "./Investigation";
import { Avatar, btn, cx, Icon, type IconName, Pulse, Spinner, StatusPill, statusLabel, Tip } from "./ui";

export function CaseDetailView({
  id,
  names,
  layout = "drawer",
}: {
  id: string;
  names: Record<string, string>;
  layout?: "drawer" | "page";
}) {
  const { data, error, isLoading } = useCase(id);

  if (error && !data)
    return (
      <div className="p-8 text-sm text-zinc-600">
        Couldn’t load case {id}. {String(error.message || error)}
      </div>
    );
  if (isLoading || !data)
    return (
      <div className="flex items-center gap-2 p-8 text-sm text-zinc-600">
        <Spinner /> Gathering the evidence for {id}…
      </div>
    );

  return <Body key={data.id} c={data} names={names} layout={layout} />;
}

function Body({ c, names, layout }: { c: Detail; names: Record<string, string>; layout: "drawer" | "page" }) {
  const d = c.data;
  const ex = c.explanation;
  const recId = d.recommended_option;
  const [selected, setSelected] = useState<string | null>(null);
  const [details, setDetails] = useState(false);
  const optionId = selected ?? recId ?? undefined;
  const option = d.options.find((o) => o.id === optionId) || null;
  const chain = option?.approver || d.approver || c.approver;
  const evidence = [...(d.signal?.evidence || []), ...(option?.evidence || [])];
  const findings = d.signal?.facts?.findings || [];
  const story = !!(ex?.benefit || ex?.if_not);
  const following = !["AWAITING_APPROVAL", "READY_TO_ASK", "AWAITING_HUMAN_REVIEW"].includes(c.status);

  const found = (
    <Section title="What we found" icon="search">
      {ex?.facts?.length ? (
        <Facts facts={ex.facts} max={4} />
      ) : (
        <p className="text-[14px] leading-relaxed text-zinc-700">{humanize(d.signal?.summary || c.summary)}</p>
      )}
    </Section>
  );

  const outcome = story && (
    <>
      {ex?.benefit && (
        <Section title={following ? "What this decision protects" : "If you approve"} icon="check">
          <Benefit c={c} />
        </Section>
      )}
      <Section title={following ? "Without it" : "If you do nothing"} icon="clock">
        <IfNot c={c} />
      </Section>
    </>
  );

  const next = (ex?.after_approve?.length ?? 0) > 0 && !following && (
    <Section title="What happens next · the agents take it from here" icon="bolt">
      <NextSteps steps={ex!.after_approve} />
    </Section>
  );

  const progress = (
    <>
      {(following || c.messages.length > 0) && (
        <Section title="Emails" icon="mail">
          {c.messages.length ? (
            <div className="space-y-3">
              {c.messages.map((m) => (
                <Email key={m.id} m={m} />
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-zinc-500">No supplier emails on this case.</p>
          )}
        </Section>
      )}
      {(following || c.events.length > 0) && (
        <Section title="What has happened" icon="clock">
          <Timeline events={c.events} status={c.status} />
        </Section>
      )}
    </>
  );

  return (
    <div className={cx(layout === "page" ? "" : "pb-10")}>
      <Head c={c} />
      {d.investigation ? (
        <>
          <InvestigationBrief inv={d.investigation} />
          <ActionBar c={c} option={option} chain={chain} />
        </>
      ) : (
        <>
          {c.status === "AWAITING_HUMAN_REVIEW" && (
            <p className="mx-6 mt-5 flex items-center gap-2 text-[13px] text-zinc-600">
              <Pulse tone="amber" /> Investigator is looking into this: checking the plan, documents and who approves…
            </p>
          )}
          <ActionBar c={c} option={option} chain={chain} />
        </>
      )}
      {(["AGREED", "IN_TRANSIT", "DELIVERED"].includes(c.status) || d.tracking) && <Tracker c={c} />}
      <div className={cx("px-6", layout === "page" && "grid grid-cols-1 gap-x-10 lg:grid-cols-2")}>
        <div>
          {!d.investigation && found}
          {layout === "drawer" && outcome}
          {layout === "drawer" && next}
        </div>
        {layout === "page" && (
          <div>
            {outcome}
            {next}
          </div>
        )}
      </div>
      <div className="px-6">{progress}</div>

      <div className="mx-6 mt-8 border-t border-zinc-100 pt-4">
        <button className={btn.quiet} onClick={() => setDetails(!details)} aria-expanded={details}>
          <Icon name="chevron" className={cx("h-3.5 w-3.5 transition", details && "rotate-90")} />
          <span className="text-[13px]">
            {details ? "Hide details" : "Details: all documents, options, sign-offs, follow-up steps"}
          </span>
        </button>
      </div>
      {details && (
        <div className={cx("animate-fade px-6", layout === "page" && "grid grid-cols-1 gap-x-10 lg:grid-cols-2")}>
          <div>
            {findings.length > 0 && (
              <Section title="What the agents read" icon="doc">
                <ul className="space-y-2">
                  {findings.map((f, i) => (
                    <li key={i} className="rounded-lg bg-zinc-50 px-3 py-2 ring-1 ring-inset ring-zinc-200">
                      <p className="text-[13px] text-zinc-800">{f.title}</p>
                      <p className="mt-0.5 text-xs italic text-zinc-600">“{f.raw}”</p>
                      <div className="mt-1.5">
                        <EvidenceLink raw={f.source} />
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            <Section title="All evidence" icon="doc">
              <EvidencePanel items={evidence} />
            </Section>
          </div>
          <div>
            {d.options.length > 0 && (
              <Section title="Options" icon="chart" hint="most customers protected per euro first">
                <OptionsTable
                  options={d.options}
                  recId={recId}
                  selected={optionId}
                  onSelect={c.status === "AWAITING_APPROVAL" ? setSelected : undefined}
                  names={names}
                />
              </Section>
            )}
            {chain && chain.approvers.length > 0 && (
              <Section title="Who signs off" icon="shield" hint="from approval policy PP-07">
                <ApproverList chain={chain} />
              </Section>
            )}
            {d.also.length > 0 && (
              <Section title="Agents also do" icon="check" hint="no approval needed">
                <ul className="space-y-1.5">
                  {d.also.map((a) => (
                    <li key={a} className="flex items-start gap-2 text-[13px] text-zinc-700">
                      <span className="mt-[3px] inline-flex h-3.5 w-3.5 shrink-0 rounded border border-zinc-300" />
                      {a}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {!following && c.events.length === 0 && (
              <Section title="What has happened" icon="clock">
                <Timeline events={c.events} status={c.status} />
              </Section>
            )}
          </div>
        </div>
      )}
      <Autonomy c={c} />
    </div>
  );
}

const TRACK_STEPS = [
  { status: "AGREED", label: "Agreed" },
  { status: "IN_TRANSIT", label: "On the way" },
  { status: "DELIVERED", label: "Delivered" },
] as const;

/** Agreed → On the way → Delivered, current step highlighted. */
function Tracker({ c }: { c: Detail }) {
  const t = c.data.tracking || {};
  const idx = Math.max(
    0,
    TRACK_STEPS.findIndex((s) => s.status === c.status),
  );
  const sub = [
    t.agreed_at ? `${when(t.agreed_at)}${t.qty ? ` · ${num(t.qty)} pcs` : ""}` : t.qty ? `${num(t.qty)} pcs` : "",
    t.shipment_reference
      ? `Waybill ${t.shipment_reference}${t.expected_arrival ? ` · expected ${when(t.expected_arrival)}` : ""}`
      : t.expected_arrival
        ? `Expected ${when(t.expected_arrival)}`
        : "Waiting for the waybill",
    t.received
      ? `${t.received.qty != null ? `${num(t.received.qty)} received` : "Received"}${t.received.delivery_note ? ` · note ${t.received.delivery_note}` : ""}`
      : "Watching for the goods receipt",
  ];
  return (
    <ol className="mx-6 mt-5 grid grid-cols-3 gap-2">
      {TRACK_STEPS.map((s, i) => {
        const done = i < idx || c.status === "DELIVERED";
        const current = i === idx && c.status !== "DELIVERED";
        return (
          <li key={s.status} className="relative">
            <div className={cx("h-1 rounded-full", done ? "bg-emerald-500" : current ? "bg-zinc-900" : "bg-zinc-200")} />
            <p
              className={cx(
                "mt-2 flex items-center gap-1.5 text-[13px]",
                done ? "text-emerald-700" : current ? "font-medium text-zinc-900" : "text-zinc-500",
              )}
            >
              {done ? <Icon name="check" className="h-3.5 w-3.5" /> : current ? <Pulse /> : null}
              {s.label}
            </p>
            <p className={cx("tnum mt-0.5 text-xs", i <= idx ? "text-zinc-600" : "text-zinc-400")}>{sub[i]}</p>
          </li>
        );
      })}
    </ol>
  );
}

function ApproverList({ chain }: { chain: NonNullable<Detail["approver"]> }) {
  return (
    <>
      <ol className="space-y-2">
        {chain.approvers.map((a, i) => {
          const vacant = a.fallback_for ? isVacant(a.fallback_for, chain.notes) : false;
          return (
            <li key={i} className="flex items-start gap-3">
              <Avatar name={a.person || a.role} size={28} />
              <div className="min-w-0">
                <p className="text-sm text-zinc-900">
                  <span className="font-medium">{a.person || "Unassigned"}</span>
                  <span className="text-zinc-600"> · {a.role}</span>
                </p>
                {a.fallback_for && (
                  <p className="text-xs text-amber-700">
                    Stands in for {vacant ? "the vacant " : ""}
                    {a.fallback_for}
                  </p>
                )}
                <p className="text-xs text-zinc-600">{a.reason}</p>
              </div>
            </li>
          );
        })}
      </ol>
      {chain.notes.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-zinc-100 pt-2.5">
          {chain.notes.map((n) => (
            <li key={n} className="text-xs text-zinc-600">
              {n}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Head({ c }: { c: Detail }) {
  return (
    <div className="px-6 pt-6">
      <div className="flex items-center gap-2 text-xs text-zinc-500">
        <StatusPill status={c.status} />
        {c.playbook_title && <span>{c.playbook_title}</span>}
      </div>
      <h1 className="mt-3 text-[22px] font-semibold leading-snug tracking-tight text-zinc-900">
        {humanize(c.explanation?.headline || c.title)}
      </h1>
      {c.recommendation && (
        <p className="mt-2 flex items-start gap-1.5 text-[14px] text-zinc-600">
          <Icon name="spark" className="mt-1 h-3.5 w-3.5 shrink-0 text-zinc-500" />
          <span>Proposed fix: <span className="text-zinc-800">{humanize(c.recommendation.title)}</span></span>
        </p>
      )}
      <GoalLine c={c} className="mt-3" />
    </div>
  );
}

function ActionBar({
  c,
  option,
  chain,
}: {
  c: Detail;
  option: Option | null;
  chain: Detail["approver"];
}) {
  const d = c.data;
  if (c.status === "AWAITING_APPROVAL" || c.status === "ESCALATED") {
    const first = chain?.approvers?.[0];
    return (
      <div className="mx-6 mt-5 flex flex-col items-stretch justify-between gap-3 rounded-xl sm:flex-row sm:items-center sm:gap-4 bg-amber-50/60 px-4 py-3 ring-1 ring-inset ring-amber-200/70">
        <p className="min-w-0 text-[13px] leading-snug text-zinc-600">
          {c.status === "ESCALATED" ? (
            <>
              <span className="font-medium text-red-700">Escalated · no supplier reply. </span>
              Aurora sent the email and one reminder. Contact the supplier directly, or pick another option under Details.
            </>
          ) : (
            policySentence(chain) || "Anyone on the launch team can approve this."
          )}
        </p>
        {c.status === "AWAITING_APPROVAL" && <ApproveButton
          caseId={c.id}
          playbookId={c.playbook_id}
          approver={chain}
          optionId={option?.id}
          consequence={consequenceFor(option?.kind, chain)}
          label={first?.person ? `Sign off as ${first.person}` : "Sign off"}
        />}
      </div>
    );
  }
  if (c.status === "READY_TO_ASK") {
    return (
      <div className="mx-6 mt-5 flex flex-col items-stretch justify-between gap-3 rounded-xl sm:flex-row sm:items-center sm:gap-4 bg-zinc-50 px-4 py-3 ring-1 ring-inset ring-zinc-200">
        <p className="min-w-0 text-[13px] leading-snug text-zinc-700">
          {d.supplier_intent ? (
            <>
              <span className="font-medium text-zinc-900">Aurora would ask: </span>
              {d.supplier_intent}
            </>
          ) : (
            "Aurora is gathering what it needs to ask. Nothing for you yet."
          )}
        </p>
        {d.supplier_intent && (
          <ApproveButton
            caseId={c.id}
            playbookId={c.playbook_id}
            approver={chain}
            consequence={consequenceFor("ask_supplier", chain)}
            label="Send the question"
          />
        )}
      </div>
    );
  }
  if (c.status === "AWAITING_HUMAN_REVIEW") {
    return (
      <div className="mx-6 mt-5 rounded-xl bg-amber-50/60 px-4 py-3 ring-1 ring-inset ring-amber-200/70">
        <p className="text-[13px] font-medium text-zinc-900">
          {d.investigation ? "Your call. What should happen?" : "No playbook covers this yet. What should happen?"}
        </p>
        <p className="text-xs text-zinc-600">
          {(d.investigation?.affects_deadline ?? c.affects_deadline)
            ? "It could affect Sunday’s launch."
            : "It does not affect Sunday’s launch."}{" "}
          Save your
          decision as a playbook and Aurora handles the next one the same way.
        </p>
        <DecideForm
          caseId={c.id}
          initialText={d.investigation?.recommendation || ""}
          playbook={d.investigation?.playbook}
        />
      </div>
    );
  }
  const text: Partial<Record<CaseStatus, string>> = {
    AWAITING_SUPPLIER: "Waiting for the supplier’s reply. Aurora follows up once, then escalates to the approver.",
    EXECUTING: "Approved. Agents are carrying it out and will verify the result.",
    VERIFIED: "Done and verified against the supplier’s confirmation.",
    ESCALATED: "No supplier reply after a follow-up. Escalated to the approver; see the email thread below.",
    DECIDED: "Decided. Aurora is following your decision.",
    AGREED: "Deal agreed. The tracker is waiting for the supplier’s waybill.",
    IN_TRANSIT: "On the way. The tracker watches for the goods receipt.",
    DELIVERED: "Delivered and booked in. Case closed.",
    SUPERSEDED: "Replaced by a newer case about the same problem.",
  };
  return (
    <div className="mx-6 mt-5 flex items-center gap-2.5 rounded-xl bg-zinc-50 px-4 py-3 text-[13px] text-zinc-600 ring-1 ring-inset ring-zinc-200">
      {["AWAITING_SUPPLIER", "EXECUTING", "AGREED", "IN_TRANSIT"].includes(c.status) ? (
        <Pulse />
      ) : (
        <Icon name="check" className="text-emerald-600" />
      )}
      {text[c.status] || statusLabel(c.status)}
    </div>
  );
}

function OptionsTable({
  options,
  recId,
  selected,
  onSelect,
  names,
}: {
  options: Option[];
  recId: string | null;
  selected?: string;
  onSelect?: (id: string) => void;
  names: Record<string, string>;
}) {
  const sorted = [...options].sort((a, b) => (b.id === recId ? 1 : 0) - (a.id === recId ? 1 : 0) || b.score - a.score);
  return (
    <ul className="divide-y divide-zinc-100 overflow-hidden rounded-lg ring-1 ring-zinc-200">
      {sorted.map((o) => {
        const g = gains(o, names);
        const spare = msBetween(o.arrival_at, o.last_useful_moment);
        const isRec = o.id === recId;
        const isSel = o.id === selected;
        const selectable = !!onSelect && o.feasible && sorted.length > 1;
        return (
          <li
            key={o.id}
            onClick={selectable ? () => onSelect!(o.id) : undefined}
            className={cx(
              "px-3 py-2.5",
              !o.feasible && "text-zinc-500",
              selectable && "cursor-pointer hover:bg-zinc-50",
              isSel && selectable && "bg-zinc-50 ring-1 ring-inset ring-zinc-300",
            )}
          >
            <div className="flex items-start gap-1.5 text-[13px]">
              {isRec ? (
                <Tip tip="Recommended: most customers protected per euro, in time">
                  <span className="text-amber-500">★</span>
                </Tip>
              ) : (
                <span className="w-3" />
              )}
              <span className={cx(o.feasible ? "text-zinc-800" : "line-through")}>{o.title}</span>
              {isRec && <span className="ml-auto shrink-0 text-[11px] text-zinc-500">Recommended</span>}
            </div>
            <dl className="tnum mt-2 grid grid-cols-3 gap-3 pl-[18px] text-[13px]">
              <div>
                <dt className="text-[10px] uppercase tracking-wide text-zinc-500">Gain</dt>
                <dd>
                  {g.up.map((x) => (
                    <div key={x.product} className="font-medium text-emerald-700">
                      {signed(x.qty)} <span className="text-xs font-normal">{x.name}</span>
                    </div>
                  ))}
                  {g.down.map((x) => (
                    <div key={x.product} className="text-xs text-zinc-500">
                      {num(x.qty)} {x.name}
                    </div>
                  ))}
                  {!g.up.length && !g.down.length && <span className="text-zinc-500">–</span>}
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wide text-zinc-500">Cost</dt>
                <dd className="text-zinc-900">
                  {eur(o.cost_eur)}
                  {o.cost_note && <div className="text-[11px] text-zinc-500">{o.cost_note}</div>}
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wide text-zinc-500">Ready / needed by</dt>
                <dd className="text-zinc-900">
                  {when(o.arrival_at)}
                  <span className="text-zinc-500"> / {when(o.last_useful_moment)}</span>
                  {spare !== null && (
                    <div className={cx("text-[11px]", spare >= 0 ? "text-emerald-700" : "text-red-600")}>
                      {spare >= 0 ? `${duration(spare)} to spare` : `${duration(-spare)} too late`}
                    </div>
                  )}
                  {!o.feasible && <div className="text-[11px] text-red-600">Not feasible</div>}
                </dd>
              </div>
            </dl>
          </li>
        );
      })}
    </ul>
  );
}

const ACTOR: Record<string, { icon: IconName; label: string }> = {
  detector: { icon: "search", label: "Detector" },
  planner: { icon: "chart", label: "Planner" },
  policy: { icon: "shield", label: "Policy" },
  planb: { icon: "spark", label: "Plan B" },
  comms: { icon: "mail", label: "Supplier Comms" },
  human: { icon: "person", label: "You" },
  agent: { icon: "bolt", label: "Agent" },
  timer: { icon: "clock", label: "Timer" },
  investigator: { icon: "search", label: "Investigator" },
  notify: { icon: "mail", label: "Aurora" },
  negotiator: { icon: "spark", label: "Negotiator" },
  tracker: { icon: "truck", label: "Tracker" },
};

function Timeline({ events, status }: { events: Detail["events"]; status: CaseStatus }) {
  if (!events.length)
    return (
      <p className="flex items-center gap-2 text-[13px] text-zinc-500">
        <Pulse />
        {status === "AWAITING_APPROVAL" || status === "READY_TO_ASK"
          ? "Found and priced by the agents. Nothing has been sent yet."
          : "No events yet."}
      </p>
    );
  return (
    <ol className="relative space-y-3 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-px before:bg-zinc-200">
      {events.map((e) => {
        const a = ACTOR[e.actor] || { icon: "bolt" as IconName, label: e.actor };
        const m = e.text.match(/^([A-Z_]{4,}):\s*(.*)$/);
        return (
          <li key={e.id} className="relative flex gap-3">
            <span
              className={cx(
                "relative z-10 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white ring-1",
                e.actor === "human" ? "text-zinc-900 ring-zinc-400" : "text-zinc-600 ring-zinc-200",
              )}
            >
              <Icon name={a.icon} className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-[13px] leading-snug text-zinc-800">
                {m ? (
                  <>
                    <span className="font-medium">{statusLabel(m[1] as CaseStatus)}</span>
                    {m[2] && <span className="text-zinc-600"> · {m[2]}</span>}
                  </>
                ) : (
                  e.text
                )}
              </p>
              <p className="tnum text-[11px] text-zinc-500">
                {a.label} · {when(e.at)}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Email({ m }: { m: CaseMessage }) {
  const hasEn = !!m.body_en && m.body_en.trim() !== m.body.trim();
  const [lang, setLang] = useState<"orig" | "en">("orig");
  const dir =
    m.direction === "in"
      ? { label: `From ${m.counterpart}`, tone: "text-zinc-900" }
      : m.direction === "out"
        ? { label: `To ${m.counterpart}`, tone: "text-zinc-900" }
        : { label: `Draft to ${m.counterpart} · ready to send`, tone: "text-amber-700" };
  return (
    <article
      className={cx(
        "overflow-hidden rounded-lg ring-1",
        m.direction === "in" ? "bg-zinc-50 ring-zinc-200" : "bg-white ring-zinc-200",
        m.direction === "outbox" && "ring-amber-200",
      )}
    >
      <header className="flex items-start justify-between gap-3 border-b border-zinc-100 px-3 py-2">
        <div className="min-w-0">
          <p className={cx("truncate text-xs font-medium", dir.tone)}>{dir.label}</p>
          <p className="truncate text-[13px] text-zinc-700">{m.subject}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {hasEn && (
            <div className="flex rounded-md bg-zinc-100 p-0.5 text-[11px]">
              {(["orig", "en"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLang(l)}
                  className={cx(
                    "rounded px-1.5 py-0.5 transition",
                    lang === l ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-600",
                  )}
                >
                  {l === "orig" ? "Original" : "English"}
                </button>
              ))}
            </div>
          )}
          <span className="tnum text-[11px] text-zinc-500">{clock(m.at)}</span>
        </div>
      </header>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap px-3 py-2.5 font-sans text-[13px] leading-relaxed text-zinc-700">
        {lang === "en" && hasEn ? m.body_en : m.body}
      </pre>
    </article>
  );
}

function Autonomy({ c }: { c: Detail }) {
  const a = c.autonomy;
  if (!a?.playbook_id) return null;
  return (
    <p className="tnum mx-6 mt-6 border-t border-zinc-100 pt-3 text-xs text-zinc-500">
      Playbook “{c.playbook_title || a.playbook_id}”: approved {a.approvals}× ({a.approvals_without_edit} without
      changes).{" "}
      {a.auto_enabled ? (
        <span className="text-emerald-700">Runs automatically.</span>
      ) : (
        "Aurora offers to run it automatically after a few clean approvals."
      )}
    </p>
  );
}

function Section({
  title,
  icon,
  hint,
  children,
}: {
  title: string;
  icon: IconName;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-7">
      <h3 className="mb-2.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600">
        <Icon name={icon} className="h-3.5 w-3.5 text-zinc-500" />
        {title}
        {hint && <span className="font-normal normal-case tracking-normal text-zinc-500">· {hint}</span>}
      </h3>
      {children}
    </section>
  );
}

