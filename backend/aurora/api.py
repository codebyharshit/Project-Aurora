"""FastAPI app: the Launch Control API plus a background loop (new drops, replies, timers).

Run: cd backend && ../.venv/bin/uvicorn aurora.api:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from aurora import comms
from aurora.config import get_tenant
from aurora.ingest.watcher import PortalWatcher
from aurora.pipeline import Pipeline
from aurora.world import World

tenant = get_tenant()
pipeline = Pipeline(tenant)
store = pipeline.store
_lock = asyncio.Lock()


def _os_env(k: str, default: str) -> str:
    import os
    return os.environ.get(k, default)


async def _run_pipeline(reason: str) -> dict:
    async with _lock:
        return await asyncio.to_thread(pipeline.run, reason)


async def _loop() -> None:
    """Every minute: check the portal for new files, read supplier replies, fire timers."""
    while True:
        try:
            drop = await asyncio.to_thread(PortalWatcher(tenant).poll)
            if not drop.empty:
                store.put("last_drop", {"at": drop.pulled_at, "added": drop.added, "changed": drop.changed})
                await _run_pipeline(f"new drop: {len(drop.added)} added, {len(drop.changed)} changed")
            now = datetime.now().astimezone().isoformat()
            for t in store.due_timers(now):
                case = store.case(t["case_id"])
                store.finish_timer(t["id"])
                if case and t["kind"] == "await_waybill" and case["status"] == "AGREED":
                    if not (case["data"].get("tracking") or {}).get("shipment_reference"):
                        await asyncio.to_thread(comms.follow_up, store, case,
                                                "Thank you for confirming. Please send the waybill / tracking number "
                                                "as soon as the goods are loaded.")
                    continue
                if case and t["kind"] == "await_delivery" and case["status"] == "IN_TRANSIT":
                    store.set_status(case["id"], "ESCALATED", "tracker", "Goods not received by the expected time")
                    from aurora.notify import notify_escalation
                    await asyncio.to_thread(notify_escalation, tenant, store, store.case(case["id"]))
                    continue
                if not case or case["status"] != "AWAITING_SUPPLIER":
                    continue
                if t["kind"] == "await_reply":
                    await asyncio.to_thread(comms.follow_up, store, case)
                    minutes = tenant.cfg.get("comms", {}).get("demo_reply_timeout_minutes", 20)
                    store.add_timer(case["id"], "await_follow_up",
                                    (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat())
                else:
                    store.set_status(case["id"], "ESCALATED", "timer",
                                     "No reply after a follow-up; escalating to the approver")
                    from aurora.notify import notify_escalation
                    await asyncio.to_thread(notify_escalation, tenant, store, store.case(case["id"]))
            if await asyncio.to_thread(comms.poll_replies, store):
                await _run_pipeline("supplier reply")
        except Exception as e:  # keep the loop alive; surface in the run log
            store.put("loop_error", {"at": datetime.now().isoformat(), "error": str(e)})
        await asyncio.sleep(60)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    if not store.get("overview"):
        await _run_pipeline("startup")
    # only one instance may run the loop (it answers supplier emails); AURORA_BACKGROUND=0 disables it
    task = asyncio.create_task(_loop()) if _os_env("AURORA_BACKGROUND", "1") != "0" else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Aurora · Launch Control", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

import os as _os  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

ACCESS_KEY = _os.environ.get("AURORA_ACCESS_KEY")


@app.middleware("http")
async def require_key(request: Request, call_next):
    """Deployed demo: the customer's data is only served with the shared access key."""
    if ACCESS_KEY and request.url.path.startswith("/api") and request.method != "OPTIONS":
        given = request.headers.get("x-aurora-key") or request.query_params.get("key")
        if given != ACCESS_KEY:
            return JSONResponse({"detail": "access key required"}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _summary(c: dict) -> dict:
    d = c["data"]
    from aurora.agents_registry import agent_for_signal
    from aurora.goal import why_for
    ov = store.get("overview") or {}
    rec = next((o for o in d["options"] if o["id"] == d.get("recommended_option")), None)
    return {"id": c["id"], "title": c["title"], "status": c["status"], "playbook_id": c["playbook_id"],
            "playbook_title": d.get("playbook_title"), "tier": d.get("tier"), "rank_score": c["rank_score"],
            "summary": d["signal"]["summary"], "signal_type": d["signal"]["type"], "severity": d["signal"]["severity"],
            "affects_deadline": d["signal"]["facts"].get("affects_deadline", True),
            "impact": d.get("impact", {}), "recommendation": rec, "approver": d.get("approver"),
            "supplier_intent": d.get("supplier_intent"), "also": d.get("also", []),
            "explanation": d.get("explanation"),
            "owners": d.get("owners", []),
            "agent": agent_for_signal(c["signal_type"] or ""),
            "why": why_for(tenant, d, ov.get("goal") or {}, ov.get("rules_in_force", [])),
            "updated_at": c["updated_at"]}


@app.get("/api/overview")
def overview() -> dict:
    ov = store.get("overview") or {}
    cases = store.cases()
    counts: dict[str, int] = {}
    for c in cases:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return {**ov, "counts": counts, "last_run": store.last_run(), "last_drop": store.get("last_drop"),
            "now": datetime.now().astimezone().isoformat()}


@app.get("/api/cases")
def cases(status: str | None = None) -> list[dict]:
    return [_summary(c) for c in store.cases(status)]


@app.get("/api/cases/{cid}")
def case(cid: str) -> dict:
    c = store.case(cid)
    if not c:
        raise HTTPException(404, "case not found")
    return {**_summary(c), "data": c["data"], "events": store.events(cid), "messages": store.messages(cid),
            "actions": store.actions(cid), "autonomy": store.playbook_stats(c["playbook_id"] or "")}


class Approve(BaseModel):
    option_id: str | None = None
    approved_by: str
    edited: bool = False
    note: str = ""


@app.post("/api/cases/{cid}/approve")
def approve(cid: str, body: Approve) -> dict:
    c = store.case(cid)
    if not c:
        raise HTTPException(404, "case not found")
    d = c["data"]
    option = next((o for o in d["options"] if o["id"] == (body.option_id or d.get("recommended_option"))), None)
    store.event(cid, "human", f"Approved by {body.approved_by}: {option['title'] if option else c['title']}"
                + (f" ({body.note})" if body.note else ""))
    stats = store.record_approval(c["playbook_id"] or "manual", body.edited)
    result: dict = {"autonomy": stats}
    kind = option["kind"] if option else None
    if option:
        committed = store.get("committed_actions", [])
        if option["id"] not in committed:
            store.put("committed_actions", committed + [option["id"]])
    if kind == "accept_offer" or (not option and d.get("supplier_intent")):
        world = World.load(tenant, read_documents=False)
        if option:
            from aurora.negotiation import mandate_from_option
            from aurora.policy import PolicyEngine
            role = ((option.get("approver") or {}).get("approvers") or [{}])[0].get("role")
            limit = next((l["max_eur_exclusive"] for l in PolicyEngine.load(world).rules["approval_limits"]
                          if l["role"] == role and l.get("max_eur_exclusive")), None)
            mandate = mandate_from_option(option, tenant.cfg.get("comms", {}).get("negotiation_tolerance", 0.10),
                                          (limit - 1) if limit else None,
                                          gap=sum((d.get("impact") or {}).get("by_product", {}).values()))
            mandate["approved_by"] = body.approved_by
            store.update_data(cid, mandate=mandate)
            store.event(cid, "human", f"Mandate for the agent: up to €{mandate['max_cost_eur']:,}, "
                                      f"needed by {mandate['needed_by'][5:16].replace('T', ' ')}")
        msg = comms.draft(world, c, option)
        store.add_action(cid, "supplier_email", "commit", "approved", msg)
        result["email"] = comms.send_for_case(store, cid, msg, body.approved_by)
        store.set_status(cid, "AWAITING_SUPPLIER", "comms", f"Waiting for {msg['supplier']}")
        minutes = tenant.cfg.get("comms", {}).get("demo_reply_timeout_minutes", 20)
        store.add_timer(cid, "await_reply", (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat())
    else:
        who = ", ".join(a["person"] or a["role"] for a in (option or d).get("approver", {}).get("approvers", []))
        store.add_action(cid, "internal_instruction", "commit", "done", {"option": option, "to": who})
        store.set_status(cid, "EXECUTING", "agent", f"Instruction issued: {option['title'] if option else c['title']}")
    pipeline.run(f"approved {cid}")
    threshold = tenant.cfg.get("autonomy", {}).get("earned_after_approvals", 3)
    result["offer_auto"] = stats["approvals_without_edit"] >= threshold and not stats["auto_enabled"]
    return result


class Decide(BaseModel):
    decision: str
    decided_by: str
    save_as_playbook: bool = False


@app.post("/api/cases/{cid}/decide")
def decide(cid: str, body: Decide) -> dict:
    c = store.case(cid)
    if not c:
        raise HTTPException(404, "case not found")
    store.event(cid, "human", f"Decision by {body.decided_by}: {body.decision}")
    store.set_status(cid, "DECIDED", "human", body.decision[:120])
    saved = None
    inv = c["data"].get("investigation")
    if body.save_as_playbook and inv:
        import re as _re
        import yaml as _yaml
        from aurora.config import ROOT
        draft = inv["playbook"]
        pb = {"id": "learned_" + _re.sub(r"[^a-z0-9]+", "_", draft["title"].lower()).strip("_")[:50],
              "title": draft["title"], "signal_type": c["data"]["signal"]["type"], "tier": draft["tier"],
              "approval": "none", "option_kinds": [], "trigger_keywords": draft["trigger_keywords"],
              "also": draft["steps"], "origin": f"decision on {cid} by {body.decided_by}: {body.decision[:160]}"}
        f = ROOT / "tenants" / tenant.name / "playbooks_learned.yaml"
        existing = _yaml.safe_load(f.read_text()) or [] if f.exists() else []
        existing = [p for p in existing if p["id"] != pb["id"]] + [pb]
        f.write_text(_yaml.safe_dump(existing, sort_keys=False, allow_unicode=True))
        store.event(cid, "human", f"Saved as playbook '{pb['title']}': the next similar case follows these steps")
        saved = pb["id"]
    return {"ok": True, "saved_playbook": saved}


@app.post("/api/playbooks/{pid}/auto")
def set_auto(pid: str, on: bool = True) -> dict:
    store.set_auto(pid, on)
    return store.playbook_stats(pid)


@app.post("/api/run")
async def run(reason: str = "manual") -> dict:
    return await _run_pipeline(reason)


@app.post("/api/poll")
async def poll() -> dict:
    drop = await asyncio.to_thread(PortalWatcher(tenant).poll)
    report = await _run_pipeline("poll") if not drop.empty else None
    replies = await asyncio.to_thread(comms.poll_replies, store)
    return {"drop": drop.__dict__, "report": report, "replies": replies}


@app.get("/api/people")
def people() -> list[dict]:
    """Team members for 'view as': role, and how many open items need them."""
    from aurora.policy import PolicyEngine
    rules = PolicyEngine.load(World.load(tenant, read_documents=False)).rules
    open_cases = [c for c in store.cases() if c["status"] in ("AWAITING_APPROVAL", "AWAITING_HUMAN_REVIEW", "READY_TO_ASK", "ESCALATED")]
    out = []
    for p in rules.get("people", []):
        mine = [c["id"] for c in open_cases if p["name"] in c["data"].get("owners", [])]
        g = _inbox_groups(p["name"])
        stand_in = sorted({a.get("fallback_for") for c in open_cases for a in (c["data"].get("approver") or {}).get("approvers", [])
                           if a.get("person") == p["name"] and a.get("fallback_for")})
        top = next((c for c in g["approve"] + g["decide"] + g["ask"]), None)
        out.append({"name": p["name"], "role": p["role"], "category": p.get("category"),
                    "from_date": p.get("from_date"), "open_items": len(mine), "case_ids": mine,
                    "scope": p["role"] + (f" · {p['category']}" if p.get("category") else ""),
                    "inbox": {"approve": len(g["approve"]), "decide": len(g["decide"]), "ask": len(g["ask"])},
                    "in_flight": len(g["in_flight"]), "stand_in_for": stand_in,
                    "email_configured": p["name"] in (tenant.cfg.get("people") or {}),
                    "top": {"case_id": top["id"], "line": ((top["data"].get("explanation") or {}).get("headline") or top["title"])[:140]}
                    if top else None})
    out.sort(key=lambda x: -x["open_items"])
    return out


@app.get("/api/agents")
def agents() -> dict:
    """The AI team: goal → process steps → business-use-case agents, with live activity."""
    from aurora.agents_registry import registry
    ov = overview()
    return registry(tenant, store, ov, ov.get("goal"))


@app.get("/api/goal")
def goal() -> dict:
    return (store.get("overview") or {}).get("goal") or {}


def _inbox_groups(name: str) -> dict:
    groups = {"approve": [], "decide": [], "ask": [], "in_flight": [], "done": []}
    for c in store.cases():
        mine = name in c["data"].get("owners", [])
        approved_by_me = any(e["text"].startswith(f"Approved by {name}") for e in store.events(c["id"]))
        st = c["status"]
        if mine and st in ("AWAITING_APPROVAL", "ESCALATED"):
            groups["approve"].append(c)
        elif mine and st == "AWAITING_HUMAN_REVIEW":
            groups["decide"].append(c)
        elif mine and st == "READY_TO_ASK":
            groups["ask"].append(c)
        elif (mine or approved_by_me) and st in ("AWAITING_SUPPLIER", "AGREED", "IN_TRANSIT", "EXECUTING"):
            groups["in_flight"].append(c)
        elif (mine or approved_by_me) and st in ("DELIVERED", "VERIFIED", "DECIDED"):
            groups["done"].append(c)
    return groups


@app.get("/api/people/{name}/inbox")
def inbox(name: str) -> dict:
    from aurora.policy import PolicyEngine
    rules = PolicyEngine.load(World.load(tenant, read_documents=False)).rules
    person = next((p for p in rules.get("people", []) if p["name"] == name), None)
    if not person:
        raise HTTPException(404, "unknown person")
    g = _inbox_groups(name)
    first = name.replace("Dr. ", "").split()[0]
    copies, cost, edition = 0, 0, None
    for c in g["approve"]:
        w = _summary(c)["why"]
        for sv in w["serves"]:
            copies += sv["copies"]
            edition = edition or sv["name"]
        cost += w.get("cost_eur") or 0
    n = len(g["approve"]) + len(g["decide"])
    if n:
        headline = (f"{first}, {n} decision{'s' if n > 1 else ''} need{'' if n > 1 else 's'} you."
                    + (f" Approving protects {copies:,} {edition} copies for €{cost:,.0f}." if copies else ""))
    else:
        headline = f"{first}, nothing needs you. Agents are handling {len(g['in_flight']) + len(g['ask'])} items for you."
    agents_for_you = []
    for c in g["approve"] + g["in_flight"]:
        d = c["data"]
        rec = next((o for o in d.get("options", []) if o["id"] == d.get("recommended_option")), None)
        if rec and rec["kind"] == "accept_offer":
            m = d.get("mandate") or {}
            agents_for_you.append({"agent": "chaser", "name": "Supplier Chaser + Negotiation", "case_id": c["id"],
                                   "text": "After your approval: email the supplier in their language; agree up to +10% "
                                           f"(€{m.get('max_cost_eur') or round((rec.get('cost_eur') or 0) * 1.1):,}), never above your limit; "
                                           "escalate to you if silent."})
        elif rec and rec["kind"] == "collect_at_port":
            agents_for_you.append({"agent": "tracking", "name": "Tracking Agent", "case_id": c["id"],
                                   "text": "After your approval: pickup instruction to logistics, dock slot, track until received."})
        if c["status"] in ("AWAITING_SUPPLIER", "AGREED", "IN_TRANSIT"):
            agents_for_you.append({"agent": "tracking", "name": "Tracking Agent", "case_id": c["id"],
                                   "text": f"{c['title'][:80]}: {c['status'].replace('_', ' ').lower()}"})
    scope = f"{person['role']}" + (f" · {person['category']}" if person.get("category") else "")
    return {"person": {**person, "scope": scope}, "headline": headline,
            **{k: [_summary(c) for c in v] for k, v in g.items()}, "agents_for_you": agents_for_you}


@app.post("/api/admin/reset-demo")
async def reset_demo() -> dict:
    """Undo all decisions (protected by the access key like every /api route)."""
    res = store.reset_decisions()
    await _run_pipeline("demo reset")
    return res


@app.get("/api/setup")
def setup() -> dict:
    """How Aurora is set up for this customer: sources, data, goal, rules, autonomy."""
    from aurora.onboard import Onboarding
    return Onboarding(tenant, World.load(tenant, read_documents=False)).build()


class Confirm(BaseModel):
    section: str
    by: str


@app.post("/api/setup/confirm")
def setup_confirm(body: Confirm) -> dict:
    from aurora.onboard import Onboarding
    return Onboarding(tenant, World.load(tenant, read_documents=False)).confirm(body.section, body.by)


class SourceConfirm(BaseModel):
    path: str
    by: str
    table: str | None = None


@app.post("/api/sources/confirm")
def source_confirm(body: SourceConfirm) -> dict:
    from aurora.ingest.schema_mapper import SchemaMapper
    return SchemaMapper(tenant).confirm(body.path, body.by, body.table)


@app.get("/api/files/{path:path}")
def file(path: str) -> FileResponse:
    root = tenant.data_root.resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(target)
