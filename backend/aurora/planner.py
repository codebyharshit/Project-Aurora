"""Launch Planner: works backwards from the deadline.

For every product it answers "how many units will be packed by the deadline?" twice:
- system view: what the ERP believes (stock as booked + inbound as scheduled)
- truth view:  the same, corrected by what the paperwork says (wrong receipts,
  rejected lots, banned revisions, short shipments, cargo nobody collected)

Every correction is a ledger entry with evidence. Supply that only becomes usable after
someone acts (sort a rejected lot, collect a container, accept an offer) is kept as
*conditional* supply tied to an action, so Plan B can ask "what if we do X?".
Deterministic: no LLM in this module.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from aurora.world import World, _norm_ref, same_ref


@dataclass
class Entry:
    part_id: str
    qty: float
    kind: str            # erp_stock | receipt_correction | rejected_lot | banned_revision | consumed | inbound | short_shipment
    reason: str
    evidence: list[str] = field(default_factory=list)
    system_value: float | None = None
    truth_value: float | None = None


@dataclass
class Conditional:
    action_id: str
    part_id: str
    qty: float
    available_at: str
    title: str
    kind: str            # recover_rejected_lot | collect_at_port | accept_offer
    cost_note: str = ""
    evidence: list[str] = field(default_factory=list)
    owner_hint: str = ""
    basis_qty: float = 0.0   # units the cost applies to (e.g. the whole lot to sort)
    transit_after_ready_h: float = 0.0


@dataclass
class ProductPlan:
    product_id: str
    name: str
    remaining: int
    system_buildable: int
    truth_buildable: int
    capacity_limit: int
    bottleneck: str | None
    short_by_part: dict[str, int]


def _rev(v) -> str | None:
    if not v:
        return None
    m = re.search(r"rev\.?\s*([A-Z0-9]+)", str(v), re.I)
    return (m.group(1) if m else str(v)).upper().strip()


def _ts(v, default_hour: int = 12) -> datetime | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
        return None
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    if t.tzinfo is None:
        t = t.tz_localize("Europe/Berlin")
        if t.hour == 0 and t.minute == 0:
            t = t + pd.Timedelta(hours=default_hour)
    return t.to_pydatetime()


class LaunchPlanner:
    def __init__(self, world: World, as_of: datetime | None = None):
        self.w = world
        self.cfg = world.tenant.cfg
        self.deadline = world.tenant.deadline
        self.products = sorted(self.cfg["products"], key=lambda p: p["priority"])
        self.status = self._status()
        self.book = self._latest_book()
        if self.book and (not self.status.get("as_of") or self.book["as_of"] > self.status["as_of"]):
            self.status = {"remaining": self.book["remaining"], "as_of": self.book["as_of"],
                           "_source": self.book["_source"]}
        env_now = os.environ.get("AURORA_NOW")
        self.as_of = (as_of or (datetime.fromisoformat(env_now) if env_now else None)
                      or self.status.get("as_of") or datetime.now(self.deadline.tzinfo))
        self.ledger: list[Entry] = []
        self.conditional: list[Conditional] = []

    # ---- demand ----------------------------------------------------------------
    def _status(self) -> dict:
        """Latest pack-out status (remaining per product), from any status workbook."""
        out: dict = {}
        root = self.w.tenant.data_root
        files = sorted(root.glob(self.cfg.get("status_files", "__none__")))
        if not files:
            return out
        import openpyxl
        ws = openpyxl.load_workbook(files[-1], data_only=True).worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        title = " ".join(str(c) for c in rows[0] if c) if rows else ""
        hdr_i = next((i for i, r in enumerate(rows) if any(str(c).strip().lower() == "still to pack" for c in r if c)), None)
        if hdr_i is None:
            return out
        hdr = [str(c).strip().lower() if c else "" for c in rows[hdr_i]]
        pi, ri = hdr.index("product"), hdr.index("still to pack")
        for r in rows[hdr_i + 1:]:
            if r[pi]:
                out[str(r[pi])] = int(float(str(r[ri]).replace(".", "").replace(",", "")))
        m = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2}):(\d{2})", title)
        if m:  # "Saturday 13:00" -> the latest such weekday on or before the deadline
            names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            back = (self.deadline.weekday() - names.index(m.group(1))) % 7
            day = self.deadline - timedelta(days=back)
            out["as_of"] = day.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0)
        out["_source"] = str(files[-1].relative_to(root))
        return {"remaining": {k: v for k, v in out.items() if k.startswith("FG")},
                "as_of": out.get("as_of"), "_source": out.get("_source")}

    def _latest_book(self) -> dict | None:
        """Newest book-stock export (per part totals + packed finished goods), if newer than the snapshot."""
        upd = self.w.t("stock_updates")
        if upd.empty or "_as_of" not in upd.columns:
            return None
        src = sorted(upd["_source"].unique())[-1]
        rows = upd[upd["_source"] == src]
        stamps = [x for x in rows["_as_of"] if x]
        if not stamps:
            return None
        as_of = datetime.fromisoformat(max(stamps)).replace(tzinfo=self.deadline.tzinfo)
        snap = self.w.t("stock")
        snap_date = pd.Timestamp(snap["snapshot_date"].max()) if not snap.empty else None
        if snap_date is not None and as_of.date() <= snap_date.date():
            return None
        qty = {r["part_id"]: float(r["quantity"] or 0) for r in rows.to_dict("records")}
        prods = {p["id"] for p in self.products}
        prod = self.w.t("products")
        remaining = {}
        for pid in prods:
            if pid in qty:
                day_one = float(prod.loc[prod["product_id"] == pid, "day_one_qty"].fillna(0).sum())
                remaining[pid] = max(0, int(day_one - qty[pid]))
        return {"as_of": as_of, "stock": qty, "remaining": remaining, "_source": src}

    def remaining(self, product_id: str) -> int:
        if product_id in self.status.get("remaining", {}):
            return self.status["remaining"][product_id]
        return self._snapshot_remaining(product_id)

    def _snapshot_remaining(self, product_id: str) -> int:
        prod = self.w.t("products")
        day_one = float(prod.loc[prod["product_id"] == product_id, "day_one_qty"].fillna(0).sum())
        stock = self.w.t("stock")
        packed = float(stock.loc[stock["part_id"] == product_id, "quantity"].sum())
        return max(0, int(day_one - packed))

    def hours_left(self, start: datetime | None = None) -> float:
        start = start or self.as_of
        total = 0.0
        for sh in self.cfg.get("shifts", []):
            s, e = datetime.fromisoformat(sh["start"]), datetime.fromisoformat(sh["end"])
            lo, hi = max(s, start), min(e, self.deadline)
            total += max(0.0, (hi - lo).total_seconds() / 3600)
        return total

    # ---- supply ledger -----------------------------------------------------------
    def _erp_stock(self, part: str) -> float:
        if self.book and part in self.book["stock"]:
            qty = self.book["stock"][part]
            self.ledger.append(Entry(part, qty, "erp_stock", f"Book stock as of {self.book['as_of']:%a %H:%M}",
                                     [self.book["_source"]]))
            return qty
        batches = self.w.stock_batches(part)
        qty = float(batches["quantity"].sum())
        self.ledger.append(Entry(part, qty, "erp_stock", "Stock as booked in the ERP snapshot",
                                 [f"stock_snapshot: {len(batches)} batches"]))
        return qty

    def _consumed_since_snapshot(self, part: str) -> float:
        if self.book:  # the newer book stock already reflects today's packing
            return 0.0
        used = 0.0
        for p in self.products:
            snap = self._snapshot_remaining(p["id"])
            now = self.remaining(p["id"])
            packed_since = max(0, snap - now)
            used += packed_since * self.w.bom(p["id"]).get(part, 0)
        if used:
            self.ledger.append(Entry(part, -used, "consumed",
                                     "Packed since the stock snapshot (no stock count since)",
                                     [self.status.get("_source", "")]))
        return used

    def _receipt_corrections(self, part: str) -> float:
        """Delivery note says a different quantity than the goods receipt booked."""
        adj = 0.0
        batches = self.w.stock_batches(part)
        for b in batches.itertuples():
            gr = self.w.receipt(b.batch)
            if gr is None or not gr.get("delivery_note"):
                continue
            for doc in self.w.doc_by_number(gr["delivery_note"]):
                for line in doc.get("lines", []):
                    if line.get("part_id") not in (None, part) or line.get("qty_final") is None:
                        continue
                    doc_qty, gr_qty = float(line["qty_final"]), float(gr["qty_received"])
                    diff = doc_qty - gr_qty
                    if abs(diff) < 1:
                        break
                    # A pure power-of-ten mismatch without a visible manual correction is
                    # usually a number-format misread, not a real discrepancy: flag, don't apply.
                    ratio = max(doc_qty, gr_qty) / max(min(doc_qty, gr_qty), 1)
                    format_suspect = abs(math.log10(ratio) - round(math.log10(ratio))) < 1e-6
                    trusted = bool(doc.get("manual_corrections")) or not format_suspect
                    if not trusted or doc.get("confidence", 1) < self.w.tenant.threshold("min_extraction_confidence", 0.7):
                        self.ledger.append(Entry(part, 0, "needs_review",
                                                 f"Receipt {gr['gr_number']} ({int(gr_qty):,}) vs delivery note "
                                                 f"{gr['delivery_note']} ({int(doc_qty):,}) unclear; not applied",
                                                 [doc["_source"]]))
                        break
                    if True:
                        delta = max(diff, -float(b.quantity))
                        adj += delta
                        self.ledger.append(Entry(
                            part, delta, "receipt_correction",
                            f"Receipt {gr['gr_number']} booked {int(gr['qty_received']):,}; delivery note "
                            f"{gr['delivery_note']} says {int(line['qty_final']):,}",
                            [doc["_source"], "goods_receipts.csv"] + doc.get("manual_corrections", [])[:1],
                            system_value=gr_qty, truth_value=doc_qty))
                    break
        return adj

    def _rejected_lots(self, part: str) -> float:
        """Inspection rejected a lot that is still counted as usable stock."""
        adj = 0.0
        batches = self.w.stock_batches(part)
        by_batch = {str(b.batch): float(b.quantity) for b in batches.itertuples()}
        for doc in self.w.docs_of("inspection_report"):
            ins = doc.get("inspection") or {}
            ref = str(ins.get("gr_or_batch") or "")
            if ins.get("result") != "reject" or ref not in by_batch:
                continue
            qty = by_batch[ref]
            adj -= qty
            self.ledger.append(Entry(part, -qty, "rejected_lot",
                                     f"Lot {ref} failed incoming inspection but is booked as usable",
                                     [doc["_source"]]))
            yield_rate = 1 - (ins.get("defects") or 0) / (ins.get("sample_size") or 1)
            self.conditional.append(Conditional(
                action_id=f"recover:{ref}", part_id=part, qty=math.floor(qty * yield_rate),
                available_at=(self.as_of + timedelta(hours=8)).isoformat(),
                title=f"Sort lot {ref} 100% and release the good parts under a concession",
                kind="recover_rejected_lot", cost_note="internal sorting labour",
                evidence=[doc["_source"]], owner_hint=ins.get("required_signoff") or ins.get("disposition") or "",
                basis_qty=qty))
        return adj

    def _remark_adjustments(self, part: str) -> float:
        """Free-text receipt remarks that change the usable quantity (read once by the AI, cached)."""
        from aurora.ingest.remarks import usable_deltas
        adj = 0.0
        for d in usable_deltas(self.w):
            if d["part_id"] == part and d["usable_delta"]:
                adj += d["usable_delta"]
                self.ledger.append(Entry(part, d["usable_delta"], "receipt_remark",
                                         f"Receipt {d['gr_number']}: {d['reason']}", [d["source"], d["delivery_note"]]))
        return adj

    def _po_revision(self, po: str, part: str) -> str | None:
        desc = self.w.part_name(part).lower()[:20]
        for doc in self.w.docs_for_po(po):
            for line in doc.get("lines", []):
                if line.get("part_id") == part or (line.get("description") or "").lower().startswith(desc[:15]):
                    if line.get("revision"):
                        return _rev(line["revision"])
        return None

    def _banned_revisions(self, part: str) -> tuple[float, set[str]]:
        bans = self.w.t("bom_changes")
        if bans.empty:
            return 0.0, set()
        rows = bans[(bans["part_id"] == part) & (bans["use_up_old_rev"].astype(str).str.upper() == "N")]
        if rows.empty:
            return 0.0, set()
        effective = rows["effective_from"].map(lambda d: _ts(d, 0) is None or _ts(d, 0) <= self.deadline)
        rows = rows[effective.astype(bool)]
        banned = {_rev(r) for r in rows["rev_old"]}
        adj = 0.0
        if not banned:
            return 0.0, banned
        for b in self.w.stock_batches(part).itertuples():
            gr = self.w.receipt(b.batch)
            if gr is None:
                continue
            rev = self._po_revision(str(gr["po_number"]), part)
            if rev in banned:
                adj -= float(b.quantity)
                change = rows.iloc[0]
                self.ledger.append(Entry(part, -float(b.quantity), "banned_revision",
                                         f"Batch {b.batch} is rev {rev}; {change['change_id']} bans it: {change['reason']}",
                                         [f"bom_delta ({change['change_id']})", f"order confirmation for PO {gr['po_number']}"]))
        return adj, banned

    def _inbound(self, part: str, banned: set[str]) -> tuple[float, float]:
        """Firm inbound usable before the deadline (truth) and as the ERP schedules it (system)."""
        ships = self.w.t("shipments")
        truth = system = 0.0
        last_mile = self.cfg.get("last_mile_hours", {})
        stale_h = self.w.tenant.threshold("arrived_not_collected_hours", 12)
        for s in ships.itertuples():
            if part not in str(s.material_ids).split("|"):
                continue
            pos = str(s.po_numbers).split("|")
            qty = sum(max(self.w.po_qty(po, part) - self.w.received_qty(po, part), 0) for po in pos)
            eta = _ts(s.eta)
            if not qty or eta is None:
                continue
            if eta.date() <= self.deadline.date():
                system += qty
            if any(self._po_revision(po, part) in banned for po in pos) and banned:
                self.ledger.append(Entry(part, 0, "banned_revision",
                                         f"Inbound {s.shipment_id} carries a banned revision; not counted", []))
                continue
            # supplier documents may override what actually shipped
            for doc in self.w.docs_of("shipping_advice"):
                sh = doc.get("shipment") or {}
                if sh.get("reference") and same_ref(sh["reference"], s.reference) and sh.get("shipped_qty") is not None:
                    ordered = sum(self.w.po_qty(po, part) for po in pos)
                    received = sum(self.w.received_qty(po, part) for po in pos)
                    still_coming = max(float(sh["shipped_qty"]) - received, 0)
                    if float(sh["shipped_qty"]) < ordered and still_coming < qty:
                        self.ledger.append(Entry(part, still_coming - qty, "short_shipment",
                                                 f"{s.shipment_id}: supplier shipped {int(sh['shipped_qty']):,} of {int(ordered):,}"
                                                 f" ({int(received):,} already received); balance ETA {sh.get('balance_eta')}",
                                                 [doc["_source"]], system_value=ordered, truth_value=float(sh["shipped_qty"])))
                        qty = still_coming
            usable = eta + timedelta(hours=float(last_mile.get(s.mode, 24)))
            updated = _ts(s.updated_at)
            if s.status == "arrived_port":
                waited = (self.as_of - (updated or eta)).total_seconds() / 3600
                self.conditional.append(Conditional(
                    action_id=f"collect:{s.shipment_id}", part_id=part, qty=qty,
                    available_at=(self.as_of + timedelta(hours=float(self.cfg.get("port_pickup_hours", 12)))).isoformat(),
                    title=f"Collect {s.reference} from the port and book a dock slot (waiting {waited:.0f} h)",
                    kind="collect_at_port", cost_note="one truck + dock slot",
                    evidence=["open_shipments.csv", s.note or ""], owner_hint="logistics + site lead"))
                continue
            if usable <= self.deadline:
                truth += qty
                self.ledger.append(Entry(part, qty, "inbound", f"{s.shipment_id} ({s.mode}) usable by {usable:%a %H:%M}",
                                         ["open_shipments.csv"]))
        return truth, system

    def _offers(self, part: str) -> None:
        now = self.as_of
        for doc in self.w.docs_of("offer"):
            off = doc.get("offer") or {}
            for it in off.get("items", []):
                if it.get("part_id") != part or not it.get("max_qty"):
                    continue
                hours = float(it.get("ready_in_hours") or 0) + float(off.get("transport_hours") or 24) \
                    + float(self.cfg.get("last_mile_hours", {}).get("road", 4))
                self.conditional.append(Conditional(
                    action_id=f"offer:{_norm_ref(doc.get('document_number') or doc['_source'])[:24]}:{part}",
                    part_id=part, qty=float(it["max_qty"]),
                    available_at=(now + timedelta(hours=hours)).isoformat(),
                    title=f"Accept {doc.get('issuer') or 'supplier'} offer: {int(it['max_qty']):,} × {self.w.part_name(part)}",
                    kind="accept_offer", cost_note=it.get("price_note") or "",
                    evidence=[doc["_source"]], owner_hint="buyer of the category",
                    transit_after_ready_h=hours - float(it.get("ready_in_hours") or 0)))

    # ---- plan ------------------------------------------------------------------
    def supply(self) -> tuple[dict[str, float], dict[str, float]]:
        parts = sorted({pt for p in self.products for pt in self.w.bom(p["id"])})
        truth, system = {}, {}
        for part in parts:
            erp = self._erp_stock(part)
            used = self._consumed_since_snapshot(part)
            corr = self._receipt_corrections(part)
            rej = self._rejected_lots(part)
            ban, banned = self._banned_revisions(part)
            rem = self._remark_adjustments(part)
            in_truth, in_system = self._inbound(part, banned)
            self._offers(part)
            system[part] = erp - used + in_system
            truth[part] = erp - used + corr + rej + ban + rem + in_truth
        return truth, system

    def _allocate(self, avail: dict[str, float]) -> list[ProductPlan]:
        avail = dict(avail)
        plans = []
        for p in self.products:
            bom = self.w.bom(p["id"])
            need = self.remaining(p["id"])
            cap = int(p.get("rate_per_hour", 1e9) * self.hours_left())
            limits = {pt: math.floor(max(avail.get(pt, 0), 0) / q) for pt, q in bom.items()}
            buildable = min([need, cap] + list(limits.values()))
            bottleneck = min(limits, key=limits.get) if limits and min(limits.values()) < need else None
            short = {pt: int(need * q - avail.get(pt, 0)) for pt, q in bom.items() if avail.get(pt, 0) < need * q}
            for pt, q in bom.items():
                avail[pt] = avail.get(pt, 0) - buildable * q
            plans.append(ProductPlan(p["id"], p["name"], need, 0, buildable, cap, bottleneck, short))
        return plans

    def run(self, actions: list[str] | None = None, extra_supply: list[dict] | None = None) -> dict:
        """extra_supply: hypothetical changes [{part_id, qty (+/-), available_at}] for what-if questions."""
        self.ledger, self.conditional = [], []
        truth, system = self.supply()
        for x in extra_supply or []:
            at = datetime.fromisoformat(x["available_at"]) if x.get("available_at") else self.as_of
            if at.tzinfo is None:
                at = at.replace(tzinfo=self.deadline.tzinfo)
            if at <= self.deadline:
                truth[x["part_id"]] = truth.get(x["part_id"], 0) + float(x["qty"])
        enabled = set(actions or [])
        for c in self.conditional:
            if c.action_id in enabled and datetime.fromisoformat(c.available_at) <= self.deadline:
                truth[c.part_id] = truth.get(c.part_id, 0) + c.qty
        t_plans, s_plans = self._allocate(truth), self._allocate(system)
        for tp, sp in zip(t_plans, s_plans):
            tp.system_buildable = sp.truth_buildable
        return {
            "as_of": self.as_of.isoformat(),
            "deadline": self.deadline.isoformat(),
            "hours_left": round(self.hours_left(), 1),
            "products": [asdict(p) for p in t_plans],
            "supply_truth": {k: int(v) for k, v in truth.items()},
            "supply_system": {k: int(v) for k, v in system.items()},
            "ledger": [asdict(e) for e in self.ledger if e.kind != "erp_stock"],
            "conditional": [asdict(c) for c in self.conditional],
            "actions_enabled": sorted(enabled),
        }
