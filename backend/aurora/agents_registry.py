"""The AI team: one specialised agent per business task (Lio's vocabulary), pinned to the
customer's process steps and to the goal. Activity is counted from real artifacts (documents read,
corrections, cases, emails, investigations), so the page shows the team actually working.

Lio's operative layer is "matching · chasing · exception handling": Stock Truth / Order
Confirmation match, Supplier Chaser / Negotiation chase, the Investigator handles exceptions.
"""
from __future__ import annotations

import json

from aurora.config import Tenant
from aurora.store import Store

PROCESS = [
    {"step": 1, "name": "Order", "system_today": "SAP (purchase orders)", "had_system": True,
     "agents": ["approvals", "sourcing", "order_confirmation"]},
    {"step": 2, "name": "Confirm", "system_today": "Email, PDF", "had_system": False,
     "agents": ["order_confirmation", "reader", "chaser"]},
    {"step": 3, "name": "Ship", "system_today": "4 logistics providers", "had_system": False,
     "agents": ["chaser", "negotiator", "sourcing"]},
    {"step": 4, "name": "Track", "system_today": "Spreadsheet", "had_system": False, "agents": ["tracking"]},
    {"step": 5, "name": "Receive", "system_today": "Paper scans", "had_system": False,
     "agents": ["stock_truth", "reader", "release_gate"]},
    {"step": 6, "name": "Pack", "system_today": "Pack-out log", "had_system": True,
     "agents": ["launch_planner", "release_gate"]},
    {"step": 7, "name": "Sell", "system_today": "Deadline Sun 20:00", "had_system": False,
     "agents": ["launch_planner", "decision_copilot", "investigator"]},
]

AGENTS = [
    {"id": "intake", "name": "Data Intake Agent", "lio_equivalent": "Connects to the systems you already know",
     "task": "Watches every source, understands new files nobody configured and maps their columns",
     "trigger": "Every minute; any new or changed file", "acts_alone": "Reads and maps", "needs_human": "Mapping below 80% confidence",
     "kind": "AI + code", "aop_tier": "observe"},
    {"id": "reader", "name": "Document Reader Agent", "lio_equivalent": "Document intake",
     "task": "Reads scans, handwriting and PDFs in any language into facts with confidence",
     "trigger": "New document", "acts_alone": "Reads", "needs_human": "Low reading confidence", "kind": "AI", "aop_tier": "observe"},
    {"id": "order_confirmation", "name": "Order Confirmation Agent", "lio_equivalent": "Order Confirmation Agent",
     "task": "Checks every supplier confirmation against the PO: quantity, date, price, revision",
     "trigger": "New confirmation", "acts_alone": "Asks the supplier", "needs_human": "PO change (buyer)",
     "kind": "code", "aop_tier": "ask"},
    {"id": "stock_truth", "name": "Stock Truth Agent", "lio_equivalent": "Goods Receipt Agent · matching",
     "task": "Matches paperwork with the ERP: wrong receipts, warehouse remarks, goods without an order",
     "trigger": "New receipt or document", "acts_alone": "Corrects the planning view (never the ERP)",
     "needs_human": "ERP correction", "kind": "code + AI", "aop_tier": "commit"},
    {"id": "release_gate", "name": "Release Gate Agent", "lio_equivalent": "Supplier Quality Agent",
     "task": "Keeps unreleased parts out of the box: rejected lots, banned revisions, expired supplier releases",
     "trigger": "Inspection, revision change, supplier status", "acts_alone": "Blocks in the plan",
     "needs_human": "Concession or release", "kind": "code", "aop_tier": "commit"},
    {"id": "tracking", "name": "Tracking Agent", "lio_equivalent": "Tracking Agent · Truck & Port Tracker",
     "task": "Follows every shipment: short shipments, cargo waiting at port, silent carriers, tracker contradictions, deliveries",
     "trigger": "Shipment data, supplier notices", "acts_alone": "Asks carriers and suppliers",
     "needs_human": "Pickup, dock slot, late delivery", "kind": "code + AI", "aop_tier": "ask"},
    {"id": "launch_planner", "name": "Launch Planner Agent", "lio_equivalent": "Supply Chain Forecasting · Inventory",
     "task": "Works backwards from the deadline: what ships, what breaks first, ERP view vs reality",
     "trigger": "Every run", "acts_alone": "Plans", "needs_human": "Never", "kind": "code", "aop_tier": "observe"},
    {"id": "sourcing", "name": "Sourcing Agent", "lio_equivalent": "Sourcing Agent · Scenario Building",
     "task": "Finds the cheapest option that still arrives in time, priced and ranked by customers protected per euro",
     "trigger": "Every gap", "acts_alone": "Proposes", "needs_human": "Approval to commit", "kind": "code", "aop_tier": "commit"},
    {"id": "approvals", "name": "Approvals Agent", "lio_equivalent": "Approvals Agent",
     "task": "Reads the customer's policy and org chart, routes each decision to the right available person, tells them once",
     "trigger": "Every decision", "acts_alone": "Routes and notifies", "needs_human": "Never",
     "kind": "AI + code", "aop_tier": "observe"},
    {"id": "chaser", "name": "Supplier Chaser Agent", "lio_equivalent": "Chasing",
     "task": "Writes to suppliers in their language, reminds once, escalates, reads every reply",
     "trigger": "After approval or an ask", "acts_alone": "Asks; reminds", "needs_human": "First commitment",
     "kind": "AI", "aop_tier": "ask"},
    {"id": "negotiator", "name": "Negotiation Agent", "lio_equivalent": "Negotiation Agent",
     "task": "Accepts, counters, answers or escalates supplier replies within the approver's mandate",
     "trigger": "Supplier reply", "acts_alone": "Inside the mandate", "needs_human": "Outside the mandate",
     "kind": "AI + rules", "aop_tier": "commit"},
    {"id": "investigator", "name": "Investigator", "lio_equivalent": "Exception handling",
     "task": "Investigates new kinds of problems with tools, proposes options and drafts a new operating procedure",
     "trigger": "New kind of problem", "acts_alone": "Investigates", "needs_human": "Decides; can save a playbook",
     "kind": "AI agent (tools)", "aop_tier": "observe"},
    {"id": "decision_copilot", "name": "Decision Copilot", "lio_equivalent": "Procurement Intelligence",
     "task": "Turns each case into one plain sentence with the goal it serves, its cost and its rule",
     "trigger": "Every case", "acts_alone": "Explains", "needs_human": "Never", "kind": "AI + code", "aop_tier": "observe"},
    {"id": "onboarding", "name": "Onboarding Agent", "lio_equivalent": "Supplier & customer onboarding",
     "task": "Proposes a new customer's goal, rules and autonomy from their own files",
     "trigger": "New customer, changed policy", "acts_alone": "Proposes", "needs_human": "Confirms each section",
     "kind": "AI", "aop_tier": "observe"},
]

SIGNAL_AGENT = {
    "qty_contradiction": "stock_truth", "needs_review": "stock_truth", "receipt_without_po": "stock_truth",
    "rejected_lot_in_stock": "release_gate", "banned_revision": "release_gate", "qualification_expired": "release_gate",
    "bank_detail_change": "release_gate",
    "short_shipment": "tracking", "arrived_not_collected": "tracking", "stale_tracking": "tracking",
    "tracking_contradiction": "tracking",
    "confirmation_mismatch": "order_confirmation", "po_unconfirmed": "order_confirmation",
}
STEP_OF = {a["id"]: next((p["step"] for p in PROCESS if a["id"] in p["agents"]), 7) for a in AGENTS}


def agent_for_signal(signal_type: str) -> dict:
    aid = "investigator" if signal_type.startswith("novel") else SIGNAL_AGENT.get(signal_type, "decision_copilot")
    a = next(x for x in AGENTS if x["id"] == aid)
    return {"id": aid, "name": a["name"], "step": STEP_OF[aid]}


def registry(tenant: Tenant, store: Store, overview: dict, goal: dict) -> dict:
    cases = [c for c in store.cases() if c["status"] != "SUPERSEDED"]
    by_agent: dict[str, list[str]] = {}
    for c in cases:
        by_agent.setdefault(agent_for_signal(c["signal_type"] or "")["id"], []).append(c["id"])
    events = [(c, e) for c in store.cases() for e in store.events(c["id"])]
    actor = lambda *names: [e for _, e in events if e["actor"] in names]
    msgs_out = sum(1 for c in store.cases() for m in store.messages(c["id"]) if m["direction"] in ("out", "outbox"))
    sm = tenant.state_dir / "schema_map.json"
    learned = [m for m in json.loads(sm.read_text()).values() if m["status"] in ("auto", "confirmed")] if sm.exists() else []
    ov = overview or {}
    corrections = len(ov.get("corrections", []))
    investigations = sum(1 for c in store.cases() if c["data"].get("investigation"))
    options = sum(len(c["data"].get("options", [])) for c in cases)
    conf_f = tenant.state_dir / "setup_confirmations.json"
    confirmed = len(json.loads(conf_f.read_text())) if conf_f.exists() else 0
    n = lambda aid: len(by_agent.get(aid, []))
    labels = {
        "intake": (len(learned), f"{len(learned)} new data files understood automatically"),
        "reader": (ov.get("documents_read") or 0, f"{ov.get('documents_read') or 0} documents read in 5 languages"),
        "order_confirmation": (n("order_confirmation"), f"{n('order_confirmation')} confirmation differences or unconfirmed orders found"),
        "stock_truth": (corrections, f"{corrections} ERP figures corrected from paperwork · {n('stock_truth')} cases"),
        "release_gate": (n("release_gate"), f"{n('release_gate')} parts or suppliers held back until released"),
        "tracking": (n("tracking") + len(actor("tracker")), f"{n('tracking')} shipment problems · {len(actor('tracker'))} delivery updates"),
        "launch_planner": (1, "Plan recalculated on every new file and decision"),
        "sourcing": (options, f"{options} options priced and ranked"),
        "approvals": (len(actor("notify")) + sum(1 for c in cases if c["data"].get("approver")),
                      f"{sum(1 for c in cases if c['data'].get('approver'))} decisions routed to the right person · {len(actor('notify'))} approval notices"),
        "chaser": (msgs_out, f"{msgs_out} supplier emails" if msgs_out else "Ready: writes in the supplier's language after approval"),
        "negotiator": (len(actor("negotiator")), f"{len(actor('negotiator'))} negotiation moves" if actor("negotiator")
                       else "Ready: accepts, counters or escalates within the approver's mandate"),
        "investigator": (investigations, f"{investigations} new problems investigated with tools"),
        "decision_copilot": (sum(1 for c in cases if c["data"].get("explanation")),
                             f"{sum(1 for c in cases if c['data'].get('explanation'))} cases explained in one sentence"),
        "onboarding": (max(confirmed, 1), f"Goal, rules and autonomy proposed · {confirmed} of 5 confirmed"),
    }
    last = {}
    for _, e in events:
        last[e["actor"]] = max(last.get(e["actor"], ""), e["at"])
    agents = []
    for a in AGENTS:
        count, label = labels.get(a["id"], (0, ""))
        agents.append({**a, "steps": [p["step"] for p in PROCESS if a["id"] in p["agents"]],
                       "activity": {"count": count, "label": label,
                                    "last": last.get({"negotiator": "negotiator", "tracking": "tracker", "chaser": "comms",
                                                      "investigator": "investigator", "approvals": "notify"}.get(a["id"], ""))},
                       "cases": by_agent.get(a["id"], [])})
    open_ids = {c["id"] for c in cases if c["status"] in ("AWAITING_APPROVAL", "AWAITING_HUMAN_REVIEW", "READY_TO_ASK", "ESCALATED")}
    process = [{**p, "open_cases": len({cid for aid in p["agents"] for cid in by_agent.get(aid, []) if cid in open_ids})}
               for p in PROCESS]
    from aurora.pipeline import LIBRARY, learned_playbooks
    import yaml
    lib = yaml.safe_load(LIBRARY.read_text())
    pbs = [{"id": p["id"], "title": p["title"], "tier": p["tier"], "approval": p.get("approval"), "origin": "library"} for p in lib]
    pbs += [{"id": p["id"], "title": p["title"], "tier": p["tier"], "approval": p.get("approval"), "origin": p.get("origin")}
            for p in learned_playbooks(tenant)]
    return {"goal": goal, "process": process, "agents": agents,
            "autonomy": {"tiers": ["observe", "ask", "commit", "never"],
                         "earned_after": tenant.cfg.get("autonomy", {}).get("earned_after_approvals", 3),
                         "never": ["payments", "bank-detail changes", "contract changes"], "playbooks": pbs},
            "operative_layer": {"matching": ["stock_truth", "order_confirmation"], "chasing": ["chaser", "negotiator"],
                                "exception_handling": ["investigator"]},
            "stats": {"documents_read": ov.get("documents_read"), "problems_open": len(open_ids),
                      "last_run": (ov.get("last_run") or {}).get("finished")}}
