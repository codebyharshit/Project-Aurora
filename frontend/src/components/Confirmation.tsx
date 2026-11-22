"use client";

import { api } from "@/lib/api";
import type { ApproveResult } from "@/lib/types";
import { btn, Icon } from "./ui";

export interface Confirmation {
  title: string;
  by: string;
  result: ApproveResult;
  steps: string[];
  playbookId: string | null;
  auto?: "saving" | "on" | "dismissed";
}

/** Green banner after an approval: what was sent, what the agents do next, and the earned-autonomy offer. */
export function ConfirmationBanner({ c, setC }: { c: Confirmation; setC: (c: Confirmation | null) => void }) {
  const email = c.result.email;
  const emailLine = email
    ? email.sent
      ? "Email sent to the supplier in their language, with an English copy."
      : email.reason === "gmail_not_configured"
        ? "Supplier email drafted and ready to send (mail isn’t connected yet)."
        : "Supplier email drafted."
    : null;
  const n = c.result.autonomy?.approvals_without_edit ?? 0;

  async function auto() {
    if (!c.playbookId) return;
    setC({ ...c, auto: "saving" });
    try {
      await api.setAuto(c.playbookId, true);
      setC({ ...c, auto: "on" });
    } catch {
      setC({ ...c, auto: undefined });
    }
  }

  return (
    <div className="mt-4 animate-pop rounded-xl bg-emerald-50/70 px-5 py-4 ring-1 ring-inset ring-emerald-200">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white">
          <Icon name="check" className="h-3 w-3" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-medium text-zinc-900">
            Approved by {c.by}: {c.title}
          </p>
          <p className="mt-0.5 text-[13px] text-zinc-600">
            {emailLine ? `${emailLine} ` : ""}
            {c.steps.length > 1 ? `Agents are on it: ${c.steps.slice(emailLine ? 1 : 0).join(" · ")}.` : c.steps[0] ? `Agents are on it: ${c.steps[0]}.` : "Agents are on it."}
          </p>
          {c.result.offer_auto && c.auto !== "dismissed" && (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-[13px]">
              {c.auto === "on" ? (
                <span className="text-emerald-800">Done. Next time Aurora handles this kind of decision itself and tells you after.</span>
              ) : (
                <>
                  <span className="text-zinc-700">
                    You’ve approved this kind of decision {n} times without changes. Let Aurora do this automatically
                    next time?
                  </span>
                  <button className={btn.secondary} onClick={auto} disabled={c.auto === "saving"}>
                    {c.auto === "saving" ? "Saving…" : "Yes, next time"}
                  </button>
                  <button className={btn.quiet} onClick={() => setC({ ...c, auto: "dismissed" })}>
                    Not now
                  </button>
                </>
              )}
            </div>
          )}
        </div>
        <button className={btn.quiet} onClick={() => setC(null)} aria-label="Dismiss">
          <Icon name="close" className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
