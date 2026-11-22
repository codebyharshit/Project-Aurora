"""Generic detectors. Each returns Signals: typed findings with entities and evidence.

Rule families (no customer-specific values):
- truth-ledger findings from the planner (document vs ERP, rejected lots, banned revisions,
  short shipments, cargo not collected)
- master-data and policy rules (qualification expiry, receipts without PO, bank changes)
- an AI catch-all over every document's `supply_risks` and external news, which classifies
  anything not already covered, so unknown problems still surface
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from aurora.agents import llm
from aurora.world import World


@dataclass
class Signal:
    type: str
    title: str
    summary: str
    entities: dict
    evidence: list[str] = field(default_factory=list)
    severity: float = 0.5
    facts: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        key = self.type + json.dumps(self.entities, sort_keys=True)
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {**asdict(self), "fingerprint": self.fingerprint}


LEDGER_TO_SIGNAL = {
    "receipt_correction": ("qty_contradiction", "Document and ERP disagree on a received quantity"),
    "rejected_lot": ("rejected_lot_in_stock", "Rejected lot counted as usable stock"),
    "banned_revision": ("banned_revision", "Banned revision in stock or inbound"),
    "short_shipment": ("short_shipment", "Supplier shipped less than ordered"),
    "needs_review": ("needs_review", "Document quantity unclear"),
}


def from_plan(world: World, plan: dict) -> list[Signal]:
    out = []
    for e in plan["ledger"]:
        if e["kind"] not in LEDGER_TO_SIGNAL or (e["kind"] == "banned_revision" and e["qty"] == 0):
            continue
        stype, title = LEDGER_TO_SIGNAL[e["kind"]]
        ref = e["reason"].split(";")[0].split(" booked")[0].split(":")[0]
        out.append(Signal(stype, f"{title}: {world.part_name(e['part_id'])}", e["reason"],
                          {"part": e["part_id"], "ref": ref}, e["evidence"],
                          severity=0.9 if e["qty"] else 0.3, facts={"delta_qty": e["qty"]}))
    for c in plan["conditional"]:
        if c["kind"] == "collect_at_port":
            out.append(Signal("arrived_not_collected", f"Cargo waiting at the port: {world.part_name(c['part_id'])}",
                              c["title"], {"part": c["part_id"], "action": c["action_id"]}, c["evidence"],
                              severity=0.8, facts={"qty": c["qty"]}))
    return out


def qualification_expired(world: World, policy_rules: dict, as_of: datetime) -> list[Signal]:
    days = policy_rules.get("conditional_release_days")
    out = []
    sup = world.t("suppliers")
    if sup.empty or not days:
        return out
    po = world.t("po_lines")
    for s in sup.to_dict("records"):
        if str(s.get("qualification_status", "")).lower() != "conditional":
            continue
        start = pd.Timestamp(s.get("qualification_released_on") or s.get("supplier_since"))
        if pd.isna(start):
            continue
        expiry = start + pd.Timedelta(days=days)
        if expiry.date() < as_of.date():
            held = po[(po["supplier_id"] == s["supplier_id"]) & (po["status"].astype(str).str.contains("await", case=False))]
            out.append(Signal("qualification_expired", f"Conditional release expired: {s['name']}",
                              f"Released {start.date()} for {days:.0f} days → expired {expiry.date()}; "
                              f"{len(held)} PO lines awaiting approval",
                              {"supplier": s["supplier_id"]}, [str(s["_source"])], 0.6,
                              {"expired_on": str(expiry.date()), "held_po_lines": held["po_number"].astype(str).tolist()}))
    return out


def receipts_without_po(world: World) -> list[Signal]:
    r = world.t("receipts")
    parts = set(world.t("parts")["part_id"])
    bad = r[(r["po_number"].astype(str).str.strip().isin(["", "nan", "None"])) | (~r["part_id"].isin(parts))]
    out = []
    for part, grp in bad.groupby("part_id"):
        out.append(Signal("receipt_without_po", f"Goods received without a purchase order: {part}",
                          f"{len(grp)} receipts, {int(grp['qty_received'].sum()):,} units, from "
                          f"{', '.join(world.supplier_name(x) for x in grp['supplier_id'].unique())}; booked outside the BOM",
                          {"part": part}, ["goods_receipts.csv"] + grp["delivery_note"].astype(str).tolist()[:3], 0.4,
                          {"qty": int(grp["qty_received"].sum()), "receipts": grp["gr_number"].astype(str).tolist()}))
    return out


def bank_changes(world: World) -> list[Signal]:
    return [Signal("bank_detail_change", f"Bank details change from {d.get('issuer')}", d.get("summary_en", ""),
                   {"doc": d["_sha256"][:12]}, [d["_source"]], 0.9, d.get("bank_details") or {})
            for d in world.documents if d.get("bank_details") and (d["bank_details"] or {}).get("new_iban")]


# ---- AI catch-all ----------------------------------------------------------------
TRIAGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "relevant", "kind", "topic", "title", "hypothesis", "severity", "affects_deadline", "supplier", "part"],
        "properties": {
            "index": {"type": "integer"}, "relevant": {"type": "boolean"},
            "kind": {"type": "string", "enum": ["covered", "external_risk", "contract_or_terms", "capacity",
                                                "quality", "logistics", "commercial", "other"]},
            "topic": {"type": "string"}, "title": {"type": "string"}, "hypothesis": {"type": "string"},
            "severity": {"type": "number"}, "affects_deadline": {"type": "boolean"},
            "supplier": {"type": ["string", "null"]}, "part": {"type": ["string", "null"]}}}}}}

TRIAGE_SYSTEM = """You triage possible supply risks for a procurement team with a hard deadline.
For each numbered candidate decide whether it is a real, actionable risk for the open orders or
the deadline. Ignore boilerplate (Incoterms explanations, generic payment terms, dates long in the
past) unless something concrete is blocked, contradicted or changed. Mark items that only repeat a
problem listed under ALREADY KNOWN as kind "covered". Orders confirmed for dates after the
deadline are normal replenishment, not a risk, unless something about them changed or is blocked.
affects_deadline is true only if the item changes what can be packed or shipped before the
deadline; later risks (e.g. next month's supply) are relevant but affects_deadline=false.
topic: a short lowercase label for the underlying issue, shared by all items about the same thing
(e.g. "rare-earth magnet export licence", "karton shutdown", "boise incoterms hold"). severity 0-1. Write title and hypothesis in
plain English, one sentence each, naming supplier, part and PO when known."""


def ai_catch_all(world: World, known: list[Signal], as_of: datetime) -> list[Signal]:
    po = world.t("po_lines")
    open_pos = set(po[po["status"].astype(str).str.lower().isin(["open", "awaiting_approval"])]["po_number"].astype(str))
    cands = []
    for d in world.documents:
        risks = d.get("supply_risks") or []
        pos = set(d.get("po_numbers") or [])
        if not risks:
            continue
        if d.get("doc_type") == "order_confirmation" and not (pos & open_pos):
            continue  # confirmations of delivered orders: history, not risk
        for r in risks:
            cands.append({"source": d["_source"], "doc_type": d["doc_type"], "issuer": d.get("issuer"),
                          "pos": sorted(pos), "risk": r})
    news = world.t("news")
    for n in news.to_dict("records") if not news.empty else []:
        cands.append({"source": n["_source"], "doc_type": "news", "issuer": n.get("source", ""),
                      "pos": [], "risk": f"{n['headline']}: {n['summary']}"})
    if not cands or not llm.available():
        return []
    known_sources = {e for k in known for e in k.evidence}
    results: list[dict] = []
    batch = 25
    for start in range(0, len(cands), batch):
        chunk = cands[start:start + batch]
        key = hashlib.sha256(json.dumps([chunk, [k.title for k in known]], sort_keys=True).encode()).hexdigest()[:16]
        cache = world.tenant.state_dir / f"triage_{key}.json"
        if cache.exists():
            res = json.loads(cache.read_text())
        else:
            context = (f"Deadline: {world.tenant.cfg['deadline']['name']} at {world.tenant.deadline:%a %d %b %H:%M}. "
                       f"Now: {as_of:%a %d %b %H:%M}.\nALREADY KNOWN:\n" + "\n".join(f"- {k.title}: {k.summary}" for k in known)
                       + f"\n\nCANDIDATES (return exactly one item per index, {len(chunk)} items):\n"
                       + "\n".join(f"[{i}] ({c['doc_type']}, {c['issuer']}, POs {c['pos']}) {c['risk']}"
                                    for i, c in enumerate(chunk)))
            res = llm.structured(system=TRIAGE_SYSTEM, content=context, schema=TRIAGE_SCHEMA, role="exec",
                                 effort="medium", max_tokens=16000)
            cache.write_text(json.dumps(res, indent=1))
        for it in res["items"]:
            if 0 <= it["index"] < len(chunk):
                results.append({**it, "_cand": chunk[it["index"]]})
    # one novel signal per underlying topic, carrying all its findings
    groups: dict[str, list[dict]] = {}
    for it in results:
        c = it["_cand"]
        if not it["relevant"] or it["kind"] == "covered" or it["severity"] < 0.4 or c["source"] in known_sources:
            continue
        who = (it["supplier"] or "").lower()
        who = re.sub(r"[^a-z ]", "", who).split()
        key = who[0] if who and who[0] not in ("soony", "unknown") else it["topic"].strip().lower()
        groups.setdefault(key, []).append(it)
    # merge groups that describe the same issue (word overlap of titles/hypotheses)
    stop = {"the", "a", "of", "to", "and", "for", "may", "could", "is", "are", "says", "new", "in", "on", "by", "with", "from", "until"}
    def words(items):
        return {w for i in items for w in re.findall(r"[a-z]{4,}", (i["title"] + " " + i["topic"]).lower())} - stop
    merged: list[list[dict]] = []
    for items in groups.values():
        for m in merged:
            a, b = words(m), words(items)
            if a and b and len(a & b) / min(len(a), len(b)) >= 0.35:
                m.extend(items)
                break
        else:
            merged.append(list(items))
    groups = {i[0]["topic"]: i for i in merged}
    out = []
    for topic, items in groups.items():
        items.sort(key=lambda i: (-i["affects_deadline"], -i["severity"]))
        lead = items[0]
        out.append(Signal(f"novel:{lead['kind']}", lead["title"],
                          " ".join(dict.fromkeys(i["hypothesis"] for i in items)),
                          {"topic": topic, "kind": "novel"},
                          list(dict.fromkeys(i["_cand"]["source"] for i in items)),
                          max(i["severity"] for i in items),
                          {"affects_deadline": any(i["affects_deadline"] for i in items),
                           "findings": [{"title": i["title"], "kind": i["kind"], "source": i["_cand"]["source"],
                                         "raw": i["_cand"]["risk"]} for i in items]}))
    return out


# ---- Order Confirmation Agent ---------------------------------------------------------
def _rev(v) -> str | None:
    import re as _re
    if not v:
        return None
    m = _re.search(r"rev\.?\s*([A-Z0-9]+)", str(v), _re.I)
    return (m.group(1) if m else str(v)).upper().strip()


def confirmation_mismatches(world: World, as_of: datetime) -> list[Signal]:
    """Supplier order confirmation vs our PO: quantity, date, price and revision — grouped per supplier."""
    po = world.t("po_lines")
    open_po = po[po["status"].astype(str).str.lower().isin(["open", "awaiting_approval"])]
    if open_po.empty:
        return []
    deadline = world.tenant.deadline
    bans = world.t("bom_changes")
    required = {}
    if not bans.empty:
        for b in bans.to_dict("records"):
            if str(b.get("use_up_old_rev", "")).upper() == "N":
                required[b["part_id"]] = (_rev(b["rev_old"]), _rev(b["rev_new"]), b.get("change_id"))
    launch_parts = {pt for p in world.tenant.cfg["products"] for pt in world.bom(p["id"])}
    findings: dict[tuple, list[dict]] = {}
    for d in world.docs_of("order_confirmation"):
        for pon in d.get("po_numbers") or []:
            lines = open_po[open_po["po_number"].astype(str) == str(pon)]
            if lines.empty:
                continue
            for oa in d.get("lines", []):
                cand = lines[lines["part_id"] == oa.get("part_id")] if oa.get("part_id") else lines[
                    lines["part_id"].map(lambda pid: (oa.get("description") or "").lower()[:15]
                                         in world.part_name(pid).lower())]
                if cand.empty:
                    continue
                if oa.get("qty_final") and len(cand) > 1:   # several lines for the same part: compare the closest
                    cand = cand.iloc[(cand["quantity"].astype(float) - float(oa["qty_final"])).abs().argsort()]
                pl = cand.iloc[0]
                sup = pl["supplier_id"]
                needed = pd.Timestamp(pl.get("requested_date")) if pd.notna(pl.get("requested_date")) else None
                matters = needed is not None and needed.date() <= deadline.date() and pl["part_id"] in launch_parts
                if oa.get("qty_final") and pl["quantity"] and abs(float(oa["qty_final"]) - float(pl["quantity"])) / float(pl["quantity"]) > 0.01:
                    findings.setdefault((sup, "quantity"), []).append(
                        {"po": pon, "part": pl["part_id"], "ours": float(pl["quantity"]), "theirs": float(oa["qty_final"]),
                         "source": d["_source"], "matters": matters})
                if oa.get("confirmed_date") and needed is not None:
                    conf = pd.Timestamp(str(oa["confirmed_date"])[:10])
                    if not pd.isna(conf) and (conf - needed).days > 3:
                        findings.setdefault((sup, "date"), []).append(
                            {"po": pon, "part": pl["part_id"], "ours": str(needed.date()), "theirs": str(conf.date()),
                             "source": d["_source"], "matters": matters and conf.date() > deadline.date()})
                if oa.get("unit_price") and pl.get("unit_price") and (oa.get("currency") in (None, pl.get("currency"))):
                    ours, theirs = float(pl["unit_price"]), float(oa["unit_price"])
                    if ours and abs(theirs - ours) / ours > 0.02:
                        findings.setdefault((sup, "price"), []).append(
                            {"po": pon, "part": pl["part_id"], "ours": ours, "theirs": theirs, "source": d["_source"],
                             "matters": False})
                req = required.get(pl["part_id"])
                if req and _rev(oa.get("revision")) == req[0]:
                    findings.setdefault((sup, "revision"), []).append(
                        {"po": pon, "part": pl["part_id"], "ours": f"rev {req[1]} ({req[2]})", "theirs": f"rev {req[0]}",
                         "source": d["_source"], "matters": True})
    out = []
    label = {"quantity": "confirmed a different quantity", "date": "confirmed later than requested",
             "price": "confirmed a different price", "revision": "confirmed a revision that may no longer be packed"}
    for (sup, kind), items in findings.items():
        name = world.supplier_name(sup)
        hot = [i for i in items if i["matters"]]
        if kind in ("date", "price", "quantity") and not hot and len(items) < 2:
            continue  # one-off history noise
        ex = items[0]
        out.append(Signal("confirmation_mismatch", f"{name} {label[kind]} on {len(items)} order line{'s' if len(items) > 1 else ''}",
                          f"Example: PO {ex['po']} {world.part_name(ex['part'])}: we ordered {ex['ours']}, the confirmation says "
                          f"{ex['theirs']}." + (f" {len(hot)} affect the deadline." if hot else ""),
                          {"supplier": sup, "kind": kind}, list(dict.fromkeys(i["source"] for i in items))[:4],
                          0.8 if kind == "revision" or hot else 0.4,
                          {"lines": items[:12], "affects_deadline": bool(hot),
                           "owner_person": _buyer(open_po, sup)}))
    # open orders due soon that nobody confirmed at all
    confirmed_pos = {str(p) for d in world.docs_of("order_confirmation", "shipping_advice") for p in d.get("po_numbers") or []}
    notices = {d.get("issuer", "").split()[0].lower() for d in world.docs_of("capacity_notice", "supplier_notice") if d.get("issuer")}
    soon = open_po[(pd.to_datetime(open_po["requested_date"], errors="coerce") <= pd.Timestamp(as_of.date()) + pd.Timedelta(days=14))
                   & (pd.to_datetime(open_po["order_date"], errors="coerce") <= pd.Timestamp(as_of.date()) - pd.Timedelta(days=3))
                   & ~open_po["po_number"].astype(str).isin(confirmed_pos)]
    for sup, grp in soon.groupby("supplier_id"):
        name = world.supplier_name(sup)
        warned = name.split()[0].lower() in notices
        pos = sorted(grp["po_number"].astype(str).unique())
        out.append(Signal("po_unconfirmed", f"{name} has not confirmed {len(pos)} order{'s' if len(pos) > 1 else ''} due within 14 days",
                          f"PO {', '.join(pos)}: {', '.join(f'{int(q):,} {world.part_name(pt)}' for pt, q in grp.groupby('part_id')['quantity'].sum().items())}"
                          + (f". {name} also announced reduced capacity." if warned else "."),
                          {"supplier": sup, "kind": "unconfirmed"}, ["soony/erp/purchase_orders_2025H2-2026.csv"],
                          0.8 if warned else 0.6,
                          {"pos": pos, "affects_deadline": bool((pd.to_datetime(grp["requested_date"]) <= pd.Timestamp(deadline.date())).any()),
                           "owner_person": _buyer(grp, sup)}))
    return out


def _buyer(po_lines: pd.DataFrame, supplier: str) -> str | None:
    b = po_lines[po_lines["supplier_id"] == supplier]["buyer"].dropna().astype(str)
    b = b[b.str.contains(" ")]   # full names only (legacy exports use short codes)
    return b.mode().iloc[0] if len(b) else None


# ---- Tracking Watchdog -------------------------------------------------------------
_ADVANCE = {"booked": 0, "in transit": 1, "in_transit": 1, "delayed": 1, "arrived_port": 2, "arrived at port": 2,
            "in_delivery": 3, "delivered": 4, "arrived": 4}


def tracking_watchdog(world: World, as_of: datetime) -> list[Signal]:
    """Shipments whose status went quiet, and sources that disagree about where a shipment is."""
    ships = world.t("shipments")
    if ships.empty:
        return []
    out = []
    tracker = world.t("shipments_tracker")
    tmap = {str(r["shipment_id"]): r for r in tracker.to_dict("records")} if not tracker.empty else {}
    hours = world.tenant.threshold("stale_tracking_hours", 12)
    stamps = pd.to_datetime(ships["updated_at"], errors="coerce", utc=True)
    newest = stamps.max()
    deadline = world.tenant.deadline
    launch_parts = {pt for p in world.tenant.cfg["products"] for pt in world.bom(p["id"])}
    contradictions = []
    for r, ts in zip(ships.to_dict("records"), stamps):
        eta = pd.to_datetime(r.get("eta"), errors="coerce")
        relevant = pd.notna(eta) and eta.date() <= (deadline + timedelta(days=2)).date() \
            and bool(set(str(r.get("material_ids", "")).split("|")) & launch_parts)
        t = tmap.get(str(r["shipment_id"]))
        if t is not None:
            a = _ADVANCE.get(str(r.get("status", "")).lower().strip())
            b = _ADVANCE.get(str(t.get("status", "")).lower().strip())
            if a is not None and b is not None and a != b and relevant:
                contradictions.append((r, t))
        if relevant and pd.notna(ts) and pd.notna(newest) and (newest - ts).total_seconds() / 3600 > hours \
                and str(r.get("status")) in ("in_transit", "delayed", "booked"):
            out.append(Signal("stale_tracking", f"No tracking update for {r['shipment_id']} ({world.part_name(str(r['material_ids']).split('|')[0])})",
                              f"Last update {ts:%a %H:%M}, {int((newest - ts).total_seconds() // 3600)} h older than the newest "
                              f"carrier update; ETA {eta.date()} is before the deadline.",
                              {"shipment": r["shipment_id"]}, [str(r.get("_source", "open_shipments.csv"))], 0.6,
                              {"affects_deadline": True, "owner_role": "Logistics Planner"}))
    if contradictions:
        ex_r, ex_t = contradictions[0]
        out.append(Signal("tracking_contradiction", f"Shipment tracker and ERP disagree on {len(contradictions)} shipment"
                          f"{'s' if len(contradictions) > 1 else ''} before the deadline",
                          f"Example: {ex_r['shipment_id']}: ERP says '{ex_r['status']}', tracker says '{ex_t['status']}'. "
                          f"People working from the tracker act on the wrong status.",
                          {"kind": "tracker_vs_erp"},
                          list(dict.fromkeys([str(ex_r.get("_source", "")), str(ex_t.get("_source", ""))])), 0.5,
                          {"shipments": [{"id": r["shipment_id"], "erp": r["status"], "tracker": t["status"]}
                                         for r, t in contradictions], "affects_deadline": True,
                           "owner_role": "Logistics Planner"}))
    return out


def run_all(world: World, plan: dict, policy_rules: dict, as_of: datetime) -> list[Signal]:
    signals = from_plan(world, plan)
    signals += confirmation_mismatches(world, as_of)
    signals += tracking_watchdog(world, as_of)
    signals += qualification_expired(world, policy_rules, as_of)
    signals += receipts_without_po(world)
    signals += bank_changes(world)
    signals += ai_catch_all(world, signals, as_of)
    return signals
