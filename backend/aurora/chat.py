"""Ask the agents: a colleague asks a question (about one case or the launch as a whole) and gets an
answer grounded in the knowledge base: case evidence, playbooks, operating rules, approval policy, plan.

Read-only: one structured call with the knowledge stuffed in, plus at most one re-plan (what-if)
and a second call when the question needs it. Nothing here approves, sends or changes data.
"""
from __future__ import annotations

import json

from aurora.agents import llm
from aurora.config import ROOT
from aurora.pipeline import learned_playbooks, load_playbooks
from aurora.policy import PolicyEngine
from aurora.store import Store
from aurora.world import World

S = {"type": ["string", "null"]}
N = {"type": ["number", "null"]}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


# what_if is an object with nullable fields (strict schemas reject anyOf on some models); part null = none
SCHEMA = _obj({
    "answer": {"type": "string"},
    "sources": {"type": "array", "items": {"type": "string"}},
    "suggested_decision": S,
    "what_if": _obj({"part": S, "qty_change": N, "available_at": S}),
})

SYSTEM = """You are Aurora's agent team answering a question from a colleague at {customer}. The deadline: {deadline_name} at {deadline_at}.
Answer ONLY from the knowledge below (case, playbooks, operating rules, approval policy, plan). If it is not there, say so; never invent numbers, names or documents. List what you used in `sources` (file names, playbook ids, 'OPERATING_RULES.md', 'approval policy', 'plan').
You are read-only: you cannot approve, send, order, email, change the ERP or commit the company to anything. Never phrase an answer as if something has been done.
If the colleague prefers a different course than the recommendation, help them make it concrete: what to do, who must sign off under the policy (approval limits; a vacant role goes to the exception role), timing against the last useful moment, and what it costs or risks for the deadline. Be honest about the risk, but respect that it is their call. Then write THEIR preferred course (not the recommendation) as one short, actionable paragraph in `suggested_decision`, naming the sign-off and the accepted risk (they can record it as their decision and save it as a playbook). Otherwise set suggested_decision to null.
Set `what_if.part` only when the question needs a re-plan with a concrete supply change (a part id or a few words of its description, a +/- quantity, optionally available_at as ISO time); prefer a re-plan over saying you cannot quantify; otherwise set all what_if fields to null. If a what-if result is already in the knowledge, use it and set them null.
Plain English, at most ~150 words: a busy manager must get it at a glance. Use the numbers given."""

OPTION_KEYS = ("id", "title", "kind", "cost_eur", "arrival_at", "last_useful_moment", "feasible", "copies_gained",
               "supplier", "approver")
INVESTIGATION_KEYS = ("summary", "root_cause", "options", "recommendation", "questions_for_human", "playbook")
POLICY_KEYS = ("approval_limits", "people", "site_leads", "exception_role", "quality_final_say_role", "air_freight",
               "release_rules", "priority_rules")
OVERVIEW_KEYS = ("verdict", "hours_left", "deadline", "editions", "rules_in_force", "goal")


def _block(title: str, value) -> str:
    body = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    return f"### {title}\n{body[:12000]}"


def _case_block(store: Store, cid: str) -> list[str]:
    c = store.case(cid)
    d = c["data"]
    sig = d.get("signal") or {}
    inv = d.get("investigation") or {}
    case = {"id": c["id"], "title": c["title"], "status": c["status"], "tier": d.get("tier"),
            "playbook": d.get("playbook_title"), "summary": sig.get("summary"),
            "findings": (sig.get("facts") or {}).get("findings", [])[:6], "impact": d.get("impact"),
            "options": [{k: o.get(k) for k in OPTION_KEYS if o.get(k) is not None} for o in d.get("options", [])],
            "recommended_option": d.get("recommended_option"), "approver": d.get("approver"),
            "also": d.get("also"), "supplier_intent": d.get("supplier_intent"), "explanation": d.get("explanation"),
            "investigation": {k: inv.get(k) for k in INVESTIGATION_KEYS if inv.get(k)} or None}
    events = [f"{e['at'][:16]} {e['actor']}: {e['text']}" for e in store.events(cid)[-15:]]
    emails = [{"subject": m.get("subject"), "direction": m.get("direction"),
               "body": (m.get("body_en") or m.get("body") or "")[:400]} for m in store.messages(cid)]
    playbook = load_playbooks().get(sig.get("type") or c.get("signal_type") or "")
    return [_block(f"Case {cid}", case), _block("What has happened", "\n".join(events) or "nothing yet"),
            _block("Supplier emails", emails or "none"), _block("Playbook for this case", playbook or "none (novel case)")]


def knowledge(tenant, store: Store, world: World, case_id: str | None) -> str:
    if case_id:
        parts = _case_block(store, case_id)
    else:
        parts = [_block("Open cases", [{"id": c["id"], "title": c["title"], "status": c["status"],
                                        "summary": (c["data"].get("signal") or {}).get("summary")}
                                       for c in store.cases() if c["status"] != "SUPERSEDED"]),
                 _block("Playbook library", list(load_playbooks().values()))]
    rules = PolicyEngine.load(world).rules
    ov = store.get("overview") or {}
    rules_md = ROOT / "docs" / "OPERATING_RULES.md"
    parts += [_block("Learned playbooks (from earlier human decisions)", learned_playbooks(tenant) or "none"),
              _block("OPERATING_RULES.md", rules_md.read_text() if rules_md.exists() else "missing"),
              _block("Approval policy", {k: rules[k] for k in POLICY_KEYS if k in rules}),
              _block("Plan (current)", {k: ov[k] for k in OVERVIEW_KEYS if k in ov})]
    return "\n\n".join(parts)


def answer(tenant, store: Store, *, case_id: str | None, question: str, history: list[dict], asked_by: str) -> dict:
    world = World.load(tenant, read_documents=False)
    dl = tenant.cfg.get("deadline", {})
    system = SYSTEM.format(customer=tenant.cfg.get("display_name", tenant.name),
                           deadline_name=dl.get("name", "the deadline"), deadline_at=dl.get("at", "?"))
    convo = "\n".join(f"{'User' if m['role'] == 'user' else 'Agents'}: {m['text']}" for m in history[-10:])
    content = "\n\n".join([knowledge(tenant, store, world, case_id),
                           _block("Conversation so far", convo or "(new conversation)"),
                           f"### Question from {asked_by}\n{question}"])
    res = llm.structured(system=system, content=content, schema=SCHEMA, role="exec", effort="low", max_tokens=4000)
    wi = None
    if (res.get("what_if") or {}).get("part") and res["what_if"].get("qty_change") is not None:
        from aurora.investigator import Toolbox
        try:
            w = res["what_if"]
            wi = Toolbox(world, store).what_if(w["part"], w["qty_change"], w.get("available_at"))
        except Exception as e:  # a failed re-plan must not lose the answer
            wi = {"error": str(e)}
        res = llm.structured(system=system, content=content + "\n\n" + _block("What-if result (re-plan)", wi),
                             schema=SCHEMA, role="exec", effort="low", max_tokens=4000)
    return {"answer": res["answer"], "sources": res["sources"], "suggested_decision": res.get("suggested_decision"),
            "what_if": wi}
