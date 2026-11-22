"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import type { ApproveResult, ApproverChain } from "@/lib/types";
import { btn, cx, Icon, Spinner } from "./ui";

type State =
  | { s: "closed" }
  | { s: "confirm" }
  | { s: "sending" }
  | { s: "done"; result: ApproveResult; by: string; auto?: "on" | "dismissed" | "saving" }
  | { s: "error"; message: string };

export interface ApproveButtonProps {
  caseId: string;
  playbookId: string | null;
  approver: ApproverChain | null | undefined;
  optionId?: string;
  /** One sentence: what Aurora does after the click. */
  consequence: string;
  label?: string;
  variant?: "primary" | "secondary" | "quiet";
  placement?: "down" | "up";
  /** Set by the parent when the keyboard shortcut fires. */
  openSignal?: number;
  /** When given, the parent shows the confirmation (popover closes on success). */
  onApproved?: (result: ApproveResult, by: string) => void;
  /** Name to prefill instead of the policy's first approver (the person viewing the room). */
  as?: string;
}

export function ApproveButton({
  caseId,
  playbookId,
  approver,
  optionId,
  consequence,
  label = "Sign off",
  variant = "primary",
  placement = "down",
  openSignal,
  onApproved,
  as,
}: ApproveButtonProps) {
  const first = approver?.approvers?.[0];
  const suggested = as || first?.person || "";
  const [state, setState] = useState<State>({ s: "closed" });
  const [name, setName] = useState(suggested);
  const [note, setNote] = useState("");
  const wrap = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const { mutate } = useSWRConfig();

  useEffect(() => {
    if (openSignal) open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSignal]);

  useEffect(() => {
    if (state.s === "closed") return;
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node) && state.s !== "sending") close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && state.s !== "sending") close();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  });

  function open() {
    setName(suggested);
    setNote("");
    setState({ s: "confirm" });
    setTimeout(() => input.current?.select(), 30);
  }

  function close() {
    const wasDone = state.s === "done";
    setState({ s: "closed" });
    if (wasDone) refresh();
  }

  function refresh() {
    mutate("/api/overview");
    mutate("/api/cases");
    mutate(`/api/cases/${encodeURIComponent(caseId)}`);
  }

  async function submit() {
    const by = name.trim();
    if (!by) return;
    setState({ s: "sending" });
    try {
      const result = await api.approve(caseId, {
        option_id: optionId,
        approved_by: by,
        edited: false,
        note: note.trim() || undefined,
      });
      if (onApproved) {
        setState({ s: "closed" });
        onApproved(result, by);
      } else {
        setState({ s: "done", result, by });
      }
      refresh();
    } catch (e) {
      setState({ s: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  async function enableAuto() {
    if (state.s !== "done" || !playbookId) return;
    setState({ ...state, auto: "saving" });
    try {
      await api.setAuto(playbookId, true);
      setState({ ...state, auto: "on" });
    } catch {
      setState({ ...state, auto: undefined });
    }
  }

  const isOpen = state.s !== "closed";

  return (
    <div ref={wrap} className="relative inline-flex">
      <button
        type="button"
        className={cx(btn[variant], isOpen && variant === "primary" && "bg-soony-blue/80")}
        onClick={() => (isOpen ? close() : open())}
        aria-expanded={isOpen}
      >
        {variant === "primary" && <Icon name="check" className="h-3.5 w-3.5" />}
        {label}
      </button>

      {isOpen && (
        <div
          className={cx(
            "absolute right-0 z-40 w-[320px] rounded-xl bg-white p-4 text-left shadow-[0_12px_40px_-8px_rgba(24,24,27,0.25)] ring-1 ring-zinc-200 animate-pop",
            placement === "down" ? "top-full mt-2" : "bottom-full mb-2",
          )}
          role="dialog"
        >
          {(state.s === "confirm" || state.s === "sending" || state.s === "error") && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
              className="space-y-3"
            >
              <p className="text-[13px] leading-snug text-zinc-600">{consequence}</p>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-zinc-600">Approve as</span>
                <input
                  ref={input}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border-0 bg-zinc-50 px-3 py-2 text-sm text-zinc-900 ring-1 ring-inset ring-zinc-200 outline-none focus:bg-white focus:ring-2 focus:ring-soony-blue"
                  placeholder="Your name"
                  disabled={state.s === "sending"}
                />
                {first && (
                  <span className="mt-1 block text-[11px] leading-snug text-zinc-500">
                    Policy routes this to {first.person || first.role} ({first.role}) · {first.policy_ref}
                  </span>
                )}
              </label>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-lg border-0 bg-transparent px-0 py-1 text-sm text-zinc-700 outline-none placeholder:text-zinc-400"
                placeholder="Add a note (optional)"
                disabled={state.s === "sending"}
              />
              {state.s === "error" && (
                <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                  Couldn’t approve: {state.message}
                </p>
              )}
              <div className="flex items-center justify-end gap-2 pt-1">
                <button type="button" className={btn.quiet} onClick={close} disabled={state.s === "sending"}>
                  Cancel
                </button>
                <button type="submit" className={btn.primary} disabled={!name.trim() || state.s === "sending"}>
                  {state.s === "sending" ? <Spinner className="border-zinc-500 border-t-white" /> : null}
                  {state.s === "sending" ? "Signing off…" : "Confirm sign-off"}
                </button>
              </div>
            </form>
          )}

          {state.s === "done" && <Done state={state} onAuto={enableAuto} onClose={close} setState={setState} />}
        </div>
      )}
    </div>
  );
}

function Done({
  state,
  onAuto,
  onClose,
  setState,
}: {
  state: Extract<State, { s: "done" }>;
  onAuto: () => void;
  onClose: () => void;
  setState: (s: State) => void;
}) {
  const { result, by } = state;
  const email = result.email;
  let line = "Aurora issued the instruction and is tracking it.";
  if (email?.sent) line = "Email sent to the supplier in their language, with an English copy. Aurora is waiting for the reply.";
  else if (email && !email.sent)
    line =
      email.reason === "gmail_not_configured"
        ? "Email drafted and ready to send (mail isn’t connected yet). You’ll find it in the case."
        : `Email drafted but not sent${email.reason ? ` (${email.reason.replace(/_/g, " ")})` : ""}.`;
  const n = result.autonomy?.approvals_without_edit ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-white">
          <Icon name="check" className="h-3 w-3" />
        </span>
        <div>
          <p className="text-sm font-medium text-zinc-900">Approved by {by}</p>
          <p className="mt-0.5 text-[13px] leading-snug text-zinc-600">{line}</p>
        </div>
      </div>

      {result.offer_auto && state.auto !== "dismissed" && (
        <div className="rounded-lg bg-zinc-50 p-3 ring-1 ring-inset ring-zinc-200">
          {state.auto === "on" ? (
            <p className="text-[13px] text-zinc-700">
              Done. Aurora will handle this kind of case by itself and tell you afterwards.
            </p>
          ) : (
            <>
              <p className="text-[13px] leading-snug text-zinc-700">
                You’ve signed off this kind of case {n} times without changes. Let Aurora do this automatically next
                time?
              </p>
              <div className="mt-2 flex justify-end gap-2">
                <button className={btn.quiet} onClick={() => setState({ ...state, auto: "dismissed" })}>
                  Not now
                </button>
                <button className={btn.secondary} onClick={onAuto} disabled={state.auto === "saving"}>
                  {state.auto === "saving" ? "Saving…" : "Yes, next time"}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <button className={btn.quiet} onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

/** What happens after approval, in one sentence, from the option kind. */
export function consequenceFor(kind: string | undefined, approver: ApproverChain | null | undefined): string {
  const who = (approver?.approvers || []).map((a) => a.person || a.role).join(" and ");
  switch (kind) {
    case "accept_offer":
      return "Aurora emails the supplier in their language to confirm the order, then watches for the reply.";
    case "ask_supplier":
      return "Aurora emails the supplier in their language with an English copy, then watches for the reply.";
    default:
      return who
        ? `Aurora issues the instruction to ${who} and tracks it to done.`
        : "Aurora issues the instruction and tracks it to done.";
  }
}
