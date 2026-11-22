"""Plain-language explanation for every case: problem, facts (with sources), benefit if approved,
consequence if not, and what the agents do after approval. Numbers come from code; only the
one-sentence headline is written by the AI (cached)."""
from __future__ import annotations

import hashlib
import json

from aurora.agents import llm
from aurora.world import World

KIND_AFTER = {
    "accept_offer": ["Email the supplier in their language to accept the offer and confirm loading time",
                     "Wait for the reply; one reminder if silent, then escalate to you",
                     "When confirmed, count the parts in the plan and close the case"],
    "collect_at_port": ["Send the pickup instruction to logistics and request a dock slot from the site lead",
                        "Track the delivery; the parts count in the plan once received"],
    "recover_rejected_lot": ["Instruct receiving to sort the lot 100% and keep only good parts",
                             "Record the concession with the named sign-offs; Quality & Compliance has the last word",
                             "Release the good parts to the Collector's cell"],
}


def _name(world: World, pid: str) -> str:
    return next((p["name"] for p in world.tenant.cfg["products"] if p["id"] == pid), pid)


def build(world: World, case: dict, plan: dict) -> dict:
    sig, impact = case["signal"], case.get("impact", {})
    value = world.tenant.cfg.get("value_at_risk_eur", {})
    rec = next((o for o in case.get("options", []) if o["id"] == case.get("recommended_option")), None)
    part = sig["entities"].get("part")

    facts = []
    for e in plan["ledger"]:
        if part and e["part_id"] == part and e["kind"] not in ("consumed", "inbound", "erp_stock") and e["qty"]:
            f = {"text": e["reason"], "source": (e["evidence"] or [None])[0]}
            if e.get("system_value") is not None:
                f.update(system=e["system_value"], truth=e["truth_value"])
            facts.append(f)
    if not facts:
        facts.append({"text": sig["summary"], "source": (sig["evidence"] or [None])[0]})
    for f in (sig["facts"].get("findings") or [])[:3]:
        facts.append({"text": f["raw"], "source": f["source"]})
    if rec:
        facts.append({"text": f"Option: {rec['title']} — ready {rec['arrival_at'][5:16].replace('T', ' ')}, "
                              f"needed by {rec['last_useful_moment'][5:16].replace('T', ' ')}",
                      "source": (rec.get("evidence") or [None])[0]})

    benefit, if_not = None, None
    if rec:
        gains = {k: v for k, v in rec["copies_gained"].items() if v}
        protected = sum(v * value.get(k, 0) for k, v in gains.items() if v > 0)
        trade = sum(-v * value.get(k, 0) for k, v in gains.items() if v < 0)
        benefit = {
            "copies": {_name(world, k): v for k, v in gains.items()},
            "eur_protected": round(protected - trade),
            "cost_eur": rec.get("cost_eur"),
            "return_ratio": round((protected - trade) / rec["cost_eur"], 1) if rec.get("cost_eur") else None,
            "partial": rec.get("partial", False),
            "text": (f"Serves {', '.join(f'{v:,} more {_name(world, k)}' for k, v in gains.items() if v > 0)} copies"
                     + (f"; {', '.join(f'{-v:,} {_name(world, k)}' for k, v in gains.items() if v < 0)} wait for later"
                        f" because shared parts go to the priority edition" if trade else "")
                     + f". Protects about €{protected - trade:,.0f} for €{rec.get('cost_eur') or 0:,}."),
        }
    if impact.get("copies_at_risk"):
        by = impact.get("by_product", {})
        if_not = {"copies": {_name(world, k): v for k, v in by.items()}, "eur_at_risk": impact.get("eur_at_risk"),
                  "text": f"{', '.join(f'{v:,} {_name(world, k)}' for k, v in by.items())} copies miss the deadline "
                          f"(about €{impact.get('eur_at_risk', 0):,} at risk)."}

    after = KIND_AFTER.get(rec["kind"], []) if rec else (
        ["Send the question to the supplier and attach the answer to this case"] if case.get("tier") == "ask"
        else ["Record your decision; you can save it as a new playbook so the next case runs by itself"]
        if case.get("tier") == "review" else ["Issue the instruction to the responsible team and track it"])

    headline = _template_headline(world, case, facts, benefit, if_not) or _headline(world, case, benefit, if_not)
    return {"headline": headline, "facts": facts[:6],
            "benefit": benefit, "if_not": if_not, "after_approve": after}


def _template_headline(world: World, case: dict, facts: list[dict], benefit: dict | None, if_not: dict | None) -> str | None:
    """Known problem types get a headline built only from verified numbers (no AI wording)."""
    sig = case["signal"]
    part = world.part_name(sig["entities"].get("part") or "") if sig["entities"].get("part") else "parts"
    part = part.split(" (")[0].split(" – ")[0]
    f0 = next((f for f in facts if f.get("system") is not None), None)
    why = {
        "qty_contradiction": (f"the ERP counts {int(f0['system']):,} {part} but the delivery note says "
                              f"{int(f0['truth']):,}") if f0 else f"the ERP and the delivery note disagree on {part}",
        "rejected_lot_in_stock": f"a {part} lot that failed inspection is still counted as usable",
        "arrived_not_collected": f"the {part} container is waiting at the port",
        "short_shipment": f"the supplier shipped fewer {part} than ordered",
        "banned_revision": f"{part} in stock carry a revision that may no longer be packed",
        "qualification_expired": "a supplier's conditional release has expired",
        "receipt_without_po": f"{part} arrived without a purchase order",
        "needs_review": f"a delivery note quantity for {part} could not be read with confidence",
    }.get(sig["type"])
    if not why:
        return None
    if if_not and benefit:
        gains = [f"{v:,} {k.replace(' Edition', '')}" for k, v in benefit["copies"].items() if v > 0]
        lost = [f"{v:,} {k.replace(' Edition', '')}" for k, v in if_not["copies"].items()]
        return (f"{' and '.join(lost)} copies miss Sunday because {why}. "
                f"Approving recovers {' and '.join(gains)} for €{benefit.get('cost_eur') or 0:,}.")
    if if_not:
        return f"{' and '.join(f'{v:,} {k}' for k, v in if_not['copies'].items())} copies are at risk because {why}."
    return why[0].upper() + why[1:] + "."


SYSTEM = """Write ONE plain-English sentence (max 28 words) a busy manager at the customer understands
instantly: what is wrong and what fixing it achieves. The reader works at the customer; problems
usually come from a supplier, carrier or warehouse, so name that party as the subject (never the
customer itself). No IDs, order numbers or legal suffixes (GmbH, Co., Ltd., Sp. z o.o.), no jargon;
use the numbers given."""


def _headline(world: World, case: dict, benefit: dict | None, if_not: dict | None) -> str:
    payload = {"customer": world.tenant.cfg["display_name"], "title": case["title"], "summary": case["signal"]["summary"],
               "benefit": (benefit or {}).get("text"), "if_not": (if_not or {}).get("text")}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    cache = world.tenant.state_dir / "headlines.json"
    store = json.loads(cache.read_text()) if cache.exists() else {}
    if key in store:
        return store[key]
    if not llm.available():
        return case["signal"]["summary"]
    line = llm.text(system=SYSTEM, content=json.dumps(payload), role="exec", effort="low", max_tokens=2000).strip()
    store[key] = line
    cache.write_text(json.dumps(store, indent=1))
    return line
