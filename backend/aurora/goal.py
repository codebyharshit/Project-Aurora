"""The goal as a first-class object: what the agents optimise, and why each suggestion serves it.

Built from the customer's config (deadline, priorities, tolerances, value per unit), the Onboarding
agent's proposal (objective, reasons, sources), the parsed policy (priority rules) and the live plan.
Every case gets a `why`: which goal it serves, what it protects vs costs, which rule applies.
"""
from __future__ import annotations

import json

from aurora.config import Tenant


def _proposal(tenant: Tenant) -> dict:
    files = sorted(tenant.state_dir.glob("goal_proposal_*.json"), key=lambda f: f.stat().st_mtime)
    return json.loads(files[-1].read_text()) if files else {}


def _confirmed(tenant: Tenant) -> dict | None:
    f = tenant.state_dir / "setup_confirmations.json"
    return json.loads(f.read_text()).get("goal") if f.exists() else None


def build_goal(tenant: Tenant, overview: dict, cases: list[dict], policy_rules: dict | None = None) -> dict:
    cfg = tenant.cfg
    prop = _proposal(tenant)
    reasons = {p.get("id"): p for p in prop.get("products", [])}
    value = cfg.get("value_at_risk_eur", {})
    priorities = []
    for p in sorted(cfg["products"], key=lambda x: x["priority"]):
        r = reasons.get(p["id"], {})
        priorities.append({"product_id": p["id"], "name": p["name"], "priority": p["priority"],
                           "tolerance_pct": p.get("max_shortfall_pct_of_launch", 0),
                           "customer_weight": p.get("customer_weight", 1), "value_per_unit_eur": value.get(p["id"]),
                           "why": r.get("reason", ""), "source": (r.get("source") or "").split(";")[0].strip()})
    verdict = (overview or {}).get("verdict") or {}
    eds = {e["product_id"]: e for e in (overview or {}).get("editions", [])}
    prods = []
    for p in priorities:
        cur = next((x for x in verdict.get("products", []) if x["product_id"] == p["product_id"] and x["view"] == "current"), {})
        allv = next((x for x in verdict.get("products", []) if x["product_id"] == p["product_id"] and x["view"] == "with_all"), {})
        pct = (eds.get(p["product_id"]) or {}).get("day_one_pct", {})
        prods.append({"product_id": p["product_id"], "name": p["name"], "launch_pct_now": pct.get("current"),
                      "launch_pct_with_all": pct.get("what_if"), "short_now": cur.get("short"), "short_with_all": allv.get("short"),
                      "tolerance_pct": p["tolerance_pct"], "within_now": cur.get("within"), "within_with_all": allv.get("within")})
    waiting = [c for c in cases if c["status"] == "AWAITING_APPROVAL"]
    people = {o for c in waiting for o in c["data"].get("owners", [])}
    cost = sum((next((o for o in c["data"].get("options", []) if o["id"] == c["data"].get("recommended_option")), {})
                .get("cost_eur") or 0) for c in waiting)
    first, second = (priorities + [None, None])[:2]
    objective = prop.get("objective") or (
        f"Ship {cfg['deadline']['name']} on time: " + "; ".join(
            f"{p['name']} within {p['tolerance_pct']:g}% of launch" for p in priorities) + ".")
    sources = sorted({p["source"] for p in priorities if p["source"]}
                     | set((policy_rules or {}).get("_sources", [])[:3]))
    return {
        "objective": objective,
        "deadline": {"name": cfg["deadline"]["name"], "at": cfg["deadline"]["at"], "site": cfg["deadline"].get("site"),
                     "meaning": prop.get("deadline_meaning") or cfg["deadline"].get("description"),
                     "pack_hours_left": (overview or {}).get("pack_hours_left")},
        "priorities": priorities,
        "ranking_rule": (f"Euros at risk per hour until the last useful moment; {first['name']} copies weigh "
                         f"{first['customer_weight'] // max(second['customer_weight'], 1) if second else 1}× "
                         f"{second['name'] if second else ''}; items that do not touch the deadline rank 10× lower.")
        if first else "",
        "status": {"on_time_now": verdict.get("on_time_now"), "on_time_with_all": verdict.get("on_time_with_all"),
                   "text": verdict.get("text"), "products": prods},
        "decisions": {"waiting": len(waiting), "people": len(people), "cost_eur": round(cost)},
        "sources": sources,
        "proposed_by": "Onboarding agent",
        "confirmed": _confirmed(tenant),
    }


def why_for(tenant: Tenant, data: dict, goal: dict, rules_in_force: list[dict]) -> dict:
    """One line of reasons for a case: goal served, protected vs cost, rule, evidence."""
    exp = data.get("explanation") or {}
    ben = exp.get("benefit") or {}
    by_name = {p["name"]: p for p in goal.get("priorities", [])}
    serves, trades = [], []
    for name, copies in (ben.get("copies") or {}).items():
        p = by_name.get(name, {})
        (serves if copies > 0 else trades).append({"product_id": p.get("product_id"), "name": name, "copies": copies})
    if serves:
        top = min((by_name.get(s["name"]) or {"name": s["name"], "priority": 9} for s in serves),
                  key=lambda p: p.get("priority", 9))
        short = top["name"].replace(" Edition", "")
        label = (f"{short} first" if top.get("priority") == 1
                 else f"{short} within {top.get('tolerance_pct', 0):g}%" if "tolerance_pct" in top else f"Serves {short}")
    elif data.get("tier") in ("ask", "observe", "review"):
        label = "Keep the plan true"
    else:
        label = "Keep records right"
    approvers = (data.get("approver") or {}).get("approvers", [])
    rule = None
    if approvers:
        a = approvers[0]
        rule = {"text": a.get("reason"), "ref": a.get("policy_ref"),
                "source": tenant.cfg.get("policies", {}).get("approval"), "stand_in": a.get("fallback_for")}
    pr = None
    for r in rules_in_force:
        if serves and any(s["name"].split()[0].lower() in r["text"].lower() for s in serves):
            pr = {"text": r["text"], "source": r.get("source")}
            break
    inn = exp.get("if_not") or {}
    lost = next(iter((inn.get("copies") or {}).items()), None)
    return {"goal": label, "serves": serves, "trades": trades,
            "protects_eur": ben.get("eur_protected"), "cost_eur": ben.get("cost_eur"), "return_ratio": ben.get("return_ratio"),
            "if_not": {"name": lost[0], "copies": lost[1], "eur": inn.get("eur_at_risk")} if lost else None,
            "rule": rule, "priority_rule": pr, "evidence_count": len(data.get("signal", {}).get("evidence", [])),
            "touches_deadline": bool(data.get("signal", {}).get("facts", {}).get("affects_deadline", True))}
