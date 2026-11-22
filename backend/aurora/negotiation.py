"""Negotiation agent: handles every supplier reply on a case within the approver's mandate.

Split of responsibilities (so money decisions stay auditable):
- AI reads the reply (any language) into terms: intent, quantity, timing, price, questions.
- Code evaluates the terms against the plan and the mandate (customers saved, arrival vs
  last useful moment, cost vs approved budget and policy limit).
- Rules pick the move: accept · counter · answer · escalate · walk away.
- AI writes the message in the supplier's language, quoting the agreed terms exactly.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from aurora.agents import llm
from aurora.store import Store

MAX_AGENT_ROUNDS = 3

TERMS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["intent", "offered_qty", "ready_at", "arrival_at", "deliveries", "price_total_eur", "price_note",
                 "shipment_reference", "questions", "summary_en", "new_risks"],
    "properties": {
        "intent": {"type": "string", "enum": ["confirm", "counter_offer", "question", "refusal", "info"]},
        "offered_qty": {"type": ["number", "null"]},
        "ready_at": {"type": ["string", "null"]},
        "arrival_at": {"type": ["string", "null"]},
        "deliveries": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["qty", "ready_at", "arrival_at"],
            "properties": {"qty": {"type": "number"}, "ready_at": {"type": ["string", "null"]},
                           "arrival_at": {"type": ["string", "null"]}}}},
        "price_total_eur": {"type": ["number", "null"]},
        "price_note": {"type": ["string", "null"]},
        "shipment_reference": {"type": ["string", "null"]},
        "questions": {"type": "array", "items": {"type": "string"}},
        "summary_en": {"type": "string"},
        "new_risks": {"type": "array", "items": {"type": "string"}},
    },
}

TERMS_SYSTEM = """You read a supplier's email reply in a procurement negotiation (any language).
Extract what the supplier states: intent (confirm = accepts our request as asked; counter_offer =
proposes different quantity, timing, split deliveries or price; question = needs information from us; refusal = cannot
or will not; info = other news). If delivery is split, list each part in deliveries (qty + when); otherwise one entry. Quantities as plain numbers ("8.000" = 8000). Times as ISO 8601 with
the year of the conversation. price_total_eur only if they state a total or unit price you can convert
to EUR for the offered quantity; otherwise null and describe it in price_note. shipment_reference: a waybill, CMR, AWB, container or tracking number if the supplier gives one.
Do not invent values."""

DRAFT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["body", "body_en"],
    "properties": {"body": {"type": "string"}, "body_en": {"type": "string"}},
}

DRAFT_SYSTEM = """You are a procurement agent writing to a supplier on behalf of the customer.
Write in the supplier's language, then the same text in English (body_en). Be brief, warm and precise.
State exactly the terms given to you and reference the supplier's own document (their offer/notice).
Never mention our budget, maximum price, internal receipt or batch numbers, or internal values. never promise anything beyond
them (no extra payments, no contract changes). If countering, explain the reason in one sentence
(the launch deadline) and propose the concrete alternative given. Sign with the sender name."""


def mandate_from_option(option: dict, tolerance: float, policy_limit: float | None, gap: int = 0) -> dict:
    """What the approver authorised the agent to agree, on their behalf."""
    cost = option.get("cost_eur") or 0
    max_cost = cost * (1 + tolerance)
    if policy_limit:
        max_cost = min(max_cost, policy_limit)
    gain = sum(v for v in option.get("copies_gained", {}).values() if v > 0)
    return {"qty": option.get("qty"), "max_cost_eur": round(max_cost), "approved_cost_eur": cost,
            "needed_by": option.get("last_useful_moment"), "arrival_planned": option.get("arrival_at"),
            "min_gain": math.floor(gain * 0.5), "approved_gain": gain, "gap": gap,
            "transit_after_ready_h": option.get("transit_after_ready_h", 13)}


def _dt(v: str, tz) -> datetime:
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=tz)


def evaluate(terms: dict, mandate: dict, rate_per_hour: float, qty_per_unit: float,
             pack_hours_after) -> dict:
    """Deterministic: what the supplier's terms are worth against the plan."""
    tz = datetime.fromisoformat(mandate["needed_by"]).tzinfo
    needed = _dt(mandate["needed_by"], tz)
    qty = terms.get("offered_qty") or mandate["qty"] or 0
    if terms.get("arrival_at"):
        arr = _dt(terms["arrival_at"], tz)
    elif terms.get("ready_at"):
        arr = _dt(terms["ready_at"], tz) + timedelta(hours=mandate["transit_after_ready_h"])
    else:
        arr = _dt(mandate["arrival_planned"], tz)
    parts = terms.get("deliveries") or [{"qty": qty, "ready_at": None, "arrival_at": arr.isoformat()}]
    usable, last_arrival, on_time = 0, arr, True
    cap = max(mandate.get("gap", 0), mandate["approved_gain"])
    for part in parts:
        if part.get("arrival_at"):
            a = _dt(part["arrival_at"], tz)
        elif part.get("ready_at"):
            a = _dt(part["ready_at"], tz) + timedelta(hours=mandate["transit_after_ready_h"])
        else:
            a = arr
        units = math.floor(part["qty"] / max(qty_per_unit, 1))
        room = cap - usable
        usable += max(min(units, room if a <= needed else int(rate_per_hour * pack_hours_after(a)), room), 0)
        last_arrival = max(last_arrival, a)
        on_time = on_time and a <= needed
    arr = last_arrival
    cost = terms.get("price_total_eur")
    return {"qty": qty, "arrival_at": arr.isoformat(), "copies_saved": usable,
            "on_time": on_time,
            "cost_eur": cost, "within_budget": cost is None or cost <= mandate["max_cost_eur"],
            "good_enough": usable >= mandate["min_gain"]}


def decide_move(terms: dict, ev: dict | None, rounds: int) -> tuple[str, str]:
    """Rules, not vibes: returns (move, reason)."""
    if terms["intent"] == "refusal":
        return "walk_away", "Supplier cannot deliver"
    if terms["intent"] == "question" and not terms.get("offered_qty"):
        return "answer", "Supplier needs information to proceed"
    if ev is None:
        return "escalate", "Reply needs a human"
    if not ev["within_budget"]:
        return "escalate", f"Price €{ev['cost_eur']:,.0f} is above the approved budget"
    if ev["good_enough"] and ev["on_time"]:
        return "accept", "Terms are within the mandate and arrive in time"
    if rounds >= MAX_AGENT_ROUNDS:
        return "escalate", "No agreement after the agent's rounds"
    if ev["good_enough"]:
        return "accept", f"Late, but still saves {ev['copies_saved']:,} customers within budget"
    return "counter", f"Offer saves only {ev['copies_saved']:,} customers; asking for an earlier or split delivery"


def read_terms(text: str, subject: str, today: str | None = None) -> dict:
    today = today or datetime.now().astimezone().isoformat(timespec="minutes")
    return llm.structured(system=TERMS_SYSTEM, content=f"Today (sender's local time): {today}\nSubject: {subject}\n\n{text}",
                          schema=TERMS_SCHEMA,
                          role="exec", effort="low")


def safe_terms(mandate: dict | None) -> dict:
    """What the supplier may see: never our budget ceiling or internal value numbers."""
    m = mandate or {}
    by = m.get("needed_by")
    by = datetime.fromisoformat(by).strftime("%A %d %b, %H:%M") if by else None
    return {"quantity": m.get("qty"), "price": "as per your offer (Annex A price)", "must_arrive_by": by}


def draft_move(move: str, context: dict) -> dict:
    instruction = {
        "accept": "Confirm the terms below and thank them; ask for the shipping/AWB reference once dispatched.",
        "counter": "Propose the counter below: ship what is ready now and the rest so it arrives before the "
                   "needed-by time, or advance loading. Keep the quantity and price unchanged.",
        "answer": "Answer their questions using only the facts below; if a fact is missing say we will follow up.",
        "walk_away": "Thank them for the quick answer and say we will source elsewhere for now.",
    }[move]
    return llm.structured(system=DRAFT_SYSTEM, content=f"Task: {instruction}\n\nContext:\n{context}",
                          schema=DRAFT_SCHEMA, role="plan" if move == "counter" else "exec", effort="medium")


def agent_rounds(store: Store, cid: str) -> int:
    return sum(1 for m in store.messages(cid) if m["direction"] == "out" and "negotiation" in (m["parsed"] or ""))
