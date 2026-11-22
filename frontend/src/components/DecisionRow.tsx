"use client";

import { useState } from "react";
import { useCaseDetails } from "@/lib/api";
import { chainOf } from "@/lib/people";
import type { ApproveResult, CaseSummary } from "@/lib/types";
import { ApproveButton, consequenceFor } from "./ApproveButton";
import { firstSentence } from "./Flight";
import { GoalLine } from "./GoalLine";
import { DeadlineBadge } from "./Investigation";
import { DecideForm } from "./Sections";
import { humanize, policySentence } from "./Story";
import { btn, Card, cx, Icon, Pulse } from "./ui";

/** One decision, compact: the sentence, the goal line, the rule, one button. */
export function DecisionRow({
  c,
  name,
  onOpen,
  onApproved,
}: {
  c: CaseSummary;
  name: string;
  onOpen: (id: string) => void;
  onApproved: (r: ApproveResult, by: string) => void;
}) {
  const ex = c.explanation;
  const rec = c.recommendation;
  const chain = chainOf(c);
  const escalated = c.status === "ESCALATED";
  const policy = policySentence(chain);

  return (
    <Card className="animate-fade">
      <div className="px-5 pb-3.5 pt-4">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {escalated ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2 py-0.5 font-medium text-red-700">
              <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
              Escalated · no supplier reply
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-800">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              Needs your sign-off
            </span>
          )}
          {c.playbook_title && <span className="truncate">{c.playbook_title}</span>}
        </div>
        <h3 className="mt-2 text-[16px] font-semibold leading-snug tracking-tight text-zinc-900">
          {humanize(ex?.headline || c.title)}
        </h3>
        {rec && (
          <p className="mt-1 flex items-center gap-1.5 text-[13px] text-zinc-600">
            <Icon name="spark" className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
            <span className="truncate">
              Proposed fix: <span className="text-zinc-800">{humanize(rec.title)}</span>
            </span>
          </p>
        )}
        <GoalLine c={c} compact className="mt-2.5" />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 px-5 py-2.5">
        <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-zinc-600">
          {policy || "Aurora found no approval rule for this; anyone on the launch team can sign off."}
        </p>
        <div className="flex shrink-0 items-center gap-1.5">
          <button className={btn.secondary} onClick={() => onOpen(c.id)}>
            {escalated ? "Open case" : "Details"}
          </button>
          {!escalated && (
            <ApproveButton
              caseId={c.id}
              playbookId={c.playbook_id}
              approver={chain}
              optionId={rec?.id}
              consequence={consequenceFor(rec?.kind, chain)}
              label={`Approve as ${name}`}
              placement="up"
              as={name}
              onApproved={onApproved}
            />
          )}
        </div>
      </div>
    </Card>
  );
}

/** A new kind of problem: the Investigator's one-liner, whether Sunday is affected, and the decision form. */
export function DecideRow({ c, onOpen }: { c: CaseSummary; onOpen: (id: string) => void }) {
  const { data: details } = useCaseDetails([c.id]);
  const inv = details?.[0]?.data.investigation || null;
  const affects = inv?.affects_deadline ?? c.affects_deadline;
  const [open, setOpen] = useState(false);

  return (
    <Card className="animate-fade">
      <div className="px-5 pb-3.5 pt-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-800">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            Needs your judgement
          </span>
          <DeadlineBadge affects={affects} />
        </div>
        <h3 className="mt-2 text-[16px] font-semibold leading-snug tracking-tight text-zinc-900">{humanize(c.title)}</h3>
        {inv ? (
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-zinc-600">{firstSentence(inv.summary)}</p>
        ) : details ? (
          <p className="mt-1.5 flex items-center gap-2 text-[13px] text-zinc-500">
            <Pulse tone="amber" /> Investigator is looking into this…
          </p>
        ) : null}
        {inv?.recommendation && !open && (
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-zinc-600">
            <span className="font-medium text-zinc-700">Investigator recommends:</span> {firstSentence(inv.recommendation)}
          </p>
        )}
        <GoalLine c={c} compact className="mt-2.5" />
        {open && (
          <DecideForm
            caseId={c.id}
            initialText={inv?.recommendation || ""}
            playbook={inv?.playbook}
            onCancel={() => setOpen(false)}
          />
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 px-5 py-2.5">
        <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-zinc-600">
          Your call. Save it as a playbook and Aurora handles the next one the same way.
        </p>
        <div className="flex shrink-0 items-center gap-1.5">
          <button className={btn.secondary} onClick={() => onOpen(c.id)}>
            Details
          </button>
          {!open && (
            <button className={btn.primary} onClick={() => setOpen(true)}>
              Decide
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}

/** Small gaps an agent can clear with one email; the person only lets it go. */
export function AskRow({ c, name, onOpen, first }: { c: CaseSummary; name: string; onOpen: (id: string) => void; first: boolean }) {
  const chain = chainOf(c);
  return (
    <li className={cx("flex items-start gap-3 px-5 py-3", !first && "border-t border-zinc-100")}>
      <Icon name="mail" className="mt-1 h-3.5 w-3.5 shrink-0 text-zinc-500" />
      <div className="min-w-0 flex-1">
        <p className="text-[14px] leading-snug text-zinc-800">{humanize(c.explanation?.headline || c.title)}</p>
        {c.supplier_intent && (
          <p className="mt-0.5 line-clamp-1 text-[12.5px] text-zinc-600">
            <span className="text-zinc-500">Would ask:</span> {c.supplier_intent}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button className={btn.quiet} onClick={() => onOpen(c.id)}>
          Details
        </button>
        <ApproveButton
          caseId={c.id}
          playbookId={c.playbook_id}
          approver={chain}
          consequence={consequenceFor("ask_supplier", chain)}
          label="Let the agent ask"
          variant="secondary"
          placement="up"
          as={name}
        />
      </div>
    </li>
  );
}
