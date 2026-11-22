"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { useName } from "@/lib/useName";
import type { ChatMessage } from "@/lib/types";
import { DecideForm } from "./Sections";
import { btn, cx, Icon, Spinner } from "./ui";

const STARTERS_CASE = [
  "Why this recommendation?",
  "Who has to sign off, and why?",
  "What if the supplier is 2 days late?",
  "I'd rather do it differently",
];
const STARTERS_GLOBAL = [
  "What needs me most right now?",
  "Will we make the deadline?",
  "Which rules apply to air freight?",
];

/** Ask the agents: read-only answers from the case, playbooks, operating rules and approval policy.
 *  If the colleague wants another course, the agents write it up and hand it to the decide flow. */
export function AskAgents({
  caseId,
  playbook,
  className = "mt-7",
}: {
  caseId: string | null;
  playbook?: { title: string; steps: string[]; tier: string } | null;
  className?: string;
}) {
  const [me] = useName();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [handoff, setHandoff] = useState<string | null>(null);
  const { mutate } = useSWRConfig();

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setErr("");
    setBusy(true);
    try {
      const r = await api.chat({ question: q, asked_by: me || "someone", case_id: caseId, history });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: r.answer, sources: r.sources, suggested_decision: r.suggested_decision },
      ]);
      if (caseId) mutate(`/api/cases/${encodeURIComponent(caseId)}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const last = messages[messages.length - 1];
  const suggestion = caseId && last?.role === "assistant" ? last.suggested_decision : null;
  const starters = caseId ? STARTERS_CASE : STARTERS_GLOBAL;

  return (
    <section className={className}>
      <h3 className="mb-2.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600">
        <Icon name="spark" className="h-3.5 w-3.5 text-zinc-500" />
        Ask the agents
        <span className="font-normal normal-case tracking-normal text-zinc-500">
          · read-only, answers from the case, playbooks and approval policy
        </span>
      </h3>

      {messages.length > 0 && (
        <div className="mb-3 flex flex-col gap-2">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <p
                key={i}
                className="max-w-[85%] self-end whitespace-pre-wrap rounded-lg bg-zinc-900 px-3 py-2 text-[13px] text-white"
              >
                {m.text}
              </p>
            ) : (
              <div
                key={i}
                className="max-w-[92%] rounded-lg bg-zinc-50 px-3 py-2 ring-1 ring-inset ring-zinc-200"
              >
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-800">{m.text}</p>
                {(m.sources?.length ?? 0) > 0 && (
                  <p className="mt-1.5 text-[11px] text-zinc-500">Sources: {m.sources!.join(" · ")}</p>
                )}
              </div>
            ),
          )}
          {busy && (
            <p className="flex items-center gap-2 text-[13px] text-zinc-600">
              <Spinner /> Checking the case, playbooks and policy…
            </p>
          )}
        </div>
      )}

      {suggestion && !handoff && !busy && (
        <div className="mb-3 rounded-lg bg-amber-50 px-3 py-2 ring-1 ring-inset ring-amber-200">
          <p className="text-[12px] font-medium text-amber-900">Your way, written up</p>
          <p className="mt-0.5 text-[13px] text-amber-900">{suggestion}</p>
          <button className={cx(btn.primary, "mt-2")} onClick={() => setHandoff(suggestion)}>
            Record this as my decision
          </button>
        </div>
      )}
      {handoff && caseId && (
        <div className="mb-3">
          <DecideForm caseId={caseId} initialText={handoff} playbook={playbook} onCancel={() => setHandoff(null)} />
        </div>
      )}

      {messages.length === 0 && (
        <div className="mb-2.5 flex flex-wrap gap-1.5">
          {starters.map((s) => (
            <button key={s} className={cx(btn.secondary, "text-[12px]")} onClick={() => send(s)} disabled={busy}>
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={1}
          placeholder={caseId ? "Ask about this case, or say how you'd rather do it…" : "Ask the agents anything about the launch…"}
          className="w-full resize-none rounded-lg border-0 bg-white px-3 py-2 text-sm leading-relaxed text-zinc-900 ring-1 ring-inset ring-zinc-200 outline-none placeholder:text-zinc-400 focus:ring-2 focus:ring-soony-blue"
        />
        <button type="submit" className={btn.primary} disabled={busy || !input.trim()}>
          {busy && messages.length === 0 ? <Spinner /> : "Ask"}
        </button>
      </form>
      {err && <p className="mt-1.5 text-xs text-red-600">{err}</p>}
    </section>
  );
}
