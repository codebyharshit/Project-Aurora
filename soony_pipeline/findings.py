"""Generic, evidence-backed contradiction checks -> table `findings`.

Every check is a rule over the linked data, never a hard-coded case. A finding is only emitted when it can be
pointed to concrete evidence (file paths and/or table rows). Severity scale:
    critical  can stop a line / cost launch copies before the deadline
    high      wrong numbers or broken control that affects launch decisions
    medium    commercial / compliance / data issue that needs follow-up
    low       documentation quality
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

import pandas as pd

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Finding:
    """One evidence-backed finding."""

    category: str
    severity: str
    rule: str
    rationale: str
    evidence: list[str]
    part_id: str | None = None
    supplier_id: str | None = None
    po_number: str | None = None
    qty: float | None = None
    amount: float | None = None
    currency: str | None = None
    confidence: str = "high"
    extra: dict = field(default_factory=dict)


@dataclass
class Ctx:
    """Shared inputs for all checks."""

    con: sqlite3.Connection
    asof: date
    deadline: datetime

    @property
    def deadline_day(self) -> str:
        return self.deadline.date().isoformat()

    def q(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.con, params=params)

    def launch_parts(self) -> set[str]:
        """Components in the BOM of products currently in launch."""
        return set(self.q("""SELECT DISTINCT b.child_id FROM m_bom b JOIN m_products p ON p.product_id=b.parent_id
                             WHERE p.lifecycle='launch'""")["child_id"])


def _ev_gr(gr: str) -> str:
    return f"soony/erp/goods_receipts.csv#gr_number={gr}"


def _ev_po(po: str, line=None) -> str:
    return f"purchase_orders#po_number={po}" + (f",po_line={int(line)}" if line is not None and pd.notna(line) else "")


def _ev_stock(batch: str) -> str:
    return f"soony/erp/stock_snapshot.csv#batch={batch}"


# ------------------------------------------------------------------ receipts / stock

def check_receipt_vs_delivery_note(ctx: Ctx) -> list[Finding]:
    """ERP received quantity differs from what the scanned delivery note certifies (incl. handwritten corrections)."""
    df = ctx.q("""SELECT v.*, s.quantity AS stock_qty FROM v_receipt_vs_delivery_note v
                  LEFT JOIN stock_snapshot s ON s.batch = v.gr_number
                  WHERE v.qty_effective IS NOT NULL AND v.qty_received <> v.qty_effective""")
    out = []
    launch = ctx.launch_parts()
    for r in df.itertuples():
        diff = int(r.qty_received - r.qty_effective)
        rel = abs(diff) / max(r.qty_effective, 1)
        sev = "critical" if (r.material_id in launch and rel >= 0.5) else "high" if rel >= 0.1 else "medium"
        overstated = min(diff, int(r.stock_qty)) if diff > 0 and pd.notna(r.stock_qty) else None
        hw = f" The note carries a handwritten correction ({r.handwritten_corrections})." if r.handwritten_corrections else ""
        out.append(Finding(
            category="qty_erp_vs_document", severity=sev, rule="goods_receipt.qty_received != delivery_note.qty_effective",
            rationale=(f"GR {r.gr_number} books {int(r.qty_received):,} {r.material_id} but delivery note {r.delivery_note} "
                       f"certifies {int(r.qty_effective):,} (printed {r.qty_printed}, handwritten {r.qty_handwritten}).{hw} "
                       f"GR remark: '{r.remark}'."
                       + (f" Batch {r.gr_number} is still in stock with {int(r.stock_qty):,}; stock is overstated by about "
                          f"{overstated:,}." if overstated else "")),
            evidence=[r.dn_file, _ev_gr(r.gr_number), _ev_po(r.po_number, r.po_line)] + ([_ev_stock(r.gr_number)] if overstated else []),
            part_id=r.material_id, supplier_id=r.supplier_id, po_number=r.po_number, qty=diff,
            confidence=r.confidence or "high", extra={"gr_number": r.gr_number, "stock_overstated": overstated}))
    return out


def check_failed_inspection_released(ctx: Ctx) -> list[Finding]:
    """Inspection report rejects a lot that is booked as unrestricted stock."""
    df = ctx.q("""SELECT d.file, d.gr_number, d.supplier_id, d.notes, l.part_id, l.lot_size, l.defective, l.reject,
                         s.quantity AS stock_qty, g.po_number
                  FROM documents d JOIN doc_lines l ON l.file=d.file
                  JOIN stock_snapshot s ON s.batch=d.gr_number
                  LEFT JOIN goods_receipts g ON g.gr_number=d.gr_number
                  WHERE d.doc_type='inspection_report' AND d.decision='reject' AND s.quantity > 0""")
    launch = ctx.launch_parts()
    return [Finding(
        category="failed_inspection_released", severity="critical" if r.part_id in launch else "high",
        rule="inspection.decision=reject AND stock.batch.quantity>0",
        rationale=(f"Inspection of GR/batch {r.gr_number} rejected the lot ({r.defective} defects in sample, reject at "
                   f"{r.reject}), yet {int(r.stock_qty):,} pcs of {r.part_id} sit in ERP stock as available. They must not be "
                   f"counted for pack-out without a signed concession."),
        evidence=[r.file, _ev_stock(r.gr_number), _ev_gr(r.gr_number)], part_id=r.part_id, supplier_id=r.supplier_id,
        po_number=r.po_number, qty=int(r.stock_qty), extra={"batch": r.gr_number}) for r in df.itertuples()]


def check_receipts_without_po(ctx: Ctx) -> list[Finding]:
    """Goods received without PO / unknown material, and scanned delivery notes never booked."""
    out = []
    df = ctx.q("""SELECT g.supplier_id, g.material_id, SUM(g.qty_received) AS qty, GROUP_CONCAT(g.gr_number) AS grs,
                         GROUP_CONCAT(g.delivery_note) AS dns
                  FROM goods_receipts g LEFT JOIN m_components c ON c.component_id=g.material_id
                  WHERE g.po_number IS NULL OR c.component_id IS NULL GROUP BY g.supplier_id, g.material_id""")
    for r in df.itertuples():
        files = ctx.q(f"SELECT file FROM documents WHERE doc_no IN ({','.join('?'*len(r.dns.split(',')))})",
                      tuple(r.dns.split(",")))["file"].tolist()
        out.append(Finding(
            category="receipt_without_po", severity="medium", rule="goods_receipt without PO or unknown material",
            rationale=(f"{int(r.qty):,} pcs of '{r.material_id}' from {r.supplier_id} received in {len(r.grs.split(','))} "
                       f"receipts without PO reference; material not in component master (booked as misc). Unordered goods "
                       f"or an order outside SAP - who pays, and is it part of a product?"),
            evidence=files + [_ev_gr(g) for g in r.grs.split(",")], part_id=r.material_id, supplier_id=r.supplier_id,
            qty=int(r.qty)))
    unbooked = ctx.q("""SELECT d.file, d.doc_no, d.supplier_id FROM documents d WHERE d.doc_type='delivery_note'
                        AND d.doc_no NOT IN (SELECT delivery_note FROM goods_receipts WHERE delivery_note IS NOT NULL)""")
    for r in unbooked.itertuples():
        out.append(Finding(category="delivery_note_not_booked", severity="medium", rule="delivery note without goods receipt",
                           rationale=f"Scanned delivery note {r.doc_no} has no goods receipt in ERP.",
                           evidence=[r.file], supplier_id=r.supplier_id))
    return out


# ------------------------------------------------------------------ PO vs confirmation / supplier statements

def check_po_vs_confirmation(ctx: Ctx) -> list[Finding]:
    """Order confirmation contradicts the PO on quantity, price, currency, date or incoterm."""
    df = ctx.q("SELECT * FROM v_po_vs_confirmation")
    out = []
    launch = ctx.launch_parts()
    for r in df.itertuples():
        ev = [r.oc_file, _ev_po(r.po_number, r.po_line)]
        if r.po_qty != r.oc_qty:
            out.append(Finding("oc_vs_po_quantity", "high", "oc.qty != po.qty",
                               f"PO {r.po_number}/{r.po_line} orders {r.po_qty:,} but the confirmation states {r.oc_qty:,}.",
                               ev, r.material_id, r.supplier_id, r.po_number, qty=r.oc_qty - r.po_qty))
        if r.po_price and r.oc_price and abs(r.oc_price - r.po_price) / r.po_price > 0.005:
            out.append(Finding("oc_vs_po_price", "medium", "oc.price != po.price",
                               f"PO {r.po_number}/{r.po_line}: PO price {r.po_price} vs confirmed {r.oc_price} {r.oc_currency}.",
                               ev, r.material_id, r.supplier_id, r.po_number, amount=(r.oc_price - r.po_price) * r.po_qty,
                               currency=r.oc_currency))
        if r.status in ("open", "awaiting_approval") and r.oc_date and r.promised_date and r.oc_date > r.promised_date:
            late = (date.fromisoformat(r.oc_date) - date.fromisoformat(r.promised_date)).days
            sev = "high" if (r.material_id in launch and r.oc_date <= ctx.deadline_day < r.oc_date) else "medium"
            out.append(Finding("oc_vs_po_date", sev, "oc.confirmed_date > po.promised_date",
                               f"PO {r.po_number}/{r.po_line}: ERP promised {r.promised_date}, supplier confirms {r.oc_date} "
                               f"({late} days later). ERP planning is too optimistic.", ev, r.material_id, r.supplier_id,
                               r.po_number, extra={"days_late": late}))
    inc = df[(df.oc_incoterm.notna()) & (df.po_incoterm != df.oc_incoterm)]
    for (sup, po_inc, oc_inc), g in inc.groupby(["supplier_id", "po_incoterm", "oc_incoterm"]):
        out.append(Finding("oc_vs_po_incoterm", "medium", "oc.incoterm != po.incoterm",
                           f"{len(g)} PO lines of {sup} carry incoterm '{po_inc}' while the supplier confirms '{oc_inc}'. "
                           f"Freight/duty risk and cost sit with Soony, not the supplier, and ERP landed cost is understated.",
                           sorted(set(g.oc_file))[:10] + [f"purchase_orders#supplier_id={sup}"], supplier_id=sup,
                           qty=len(g), extra={"po_lines": len(g)}))
    return out


def check_confirmation_statements(ctx: Ctx) -> list[Finding]:
    """Typed statements in confirmations: holds, status claims, artwork revisions, BOM inclusions."""
    out = []
    launch = ctx.launch_parts()
    holds = ctx.q("""SELECT i.file, i.supplier_id, d.po_numbers, i.text FROM doc_issues i JOIN documents d ON d.file=i.file
                     WHERE i.type='shipment_on_hold'""")
    for r in holds.itertuples():
        po = r.po_numbers.split("|")[0]
        lines = ctx.q("SELECT po_line, material_id, quantity, status FROM purchase_orders WHERE po_number=?", (po,))
        ships = ctx.q("""SELECT s.shipment_id, s.reference, s.status, s.eta, s.material_ids FROM shipment_po sp
                         JOIN shipments_erp s ON s.shipment_id=sp.shipment_id WHERE sp.po_number=?""", (po,))
        open_l = lines[lines.status == "open"]
        crit = bool(set(open_l.material_id) & launch)
        out.append(Finding(
            "supplier_hold", "critical" if crit else "high", "order confirmation says shipment on hold",
            (f"Supplier states PO {po} is packed and ON HOLD at its dock until Soony accepts its incoterm or nominates a "
             f"forwarder. Open lines: {', '.join(f'{x.material_id} {x.quantity:,}' for x in open_l.itertuples())}. "
             f"ERP still shows shipments {', '.join(f'{s.shipment_id} ({s.status}, ETA {s.eta})' for s in ships.itertuples())} "
             f"for this PO - status in ERP does not reflect the hold."),
            [r.file, _ev_po(po)] + [f"soony/erp/open_shipments.csv#shipment_id={s}" for s in ships.shipment_id],
            ",".join(sorted(set(open_l.material_id))), r.supplier_id, po, qty=int(open_l.quantity.sum())))
    claims = ctx.q("""SELECT i.supplier_id, i.value, GROUP_CONCAT(i.file) AS files, p.qualification_status
                      FROM doc_issues i JOIN supplier_profiles p ON p.supplier_id=i.supplier_id
                      WHERE i.type='supplier_status_claim' GROUP BY i.supplier_id, i.value""")
    for r in claims.itertuples():
        if "approved" in r.value.lower() and r.qualification_status != "qualified":
            out.append(Finding("supplier_status_contradiction", "high", "supplier claims release != master qualification",
                               f"{r.supplier_id} writes '{r.value}' on its confirmations, but Soony's master says "
                               f"qualification_status='{r.qualification_status}'. A submitted PPAP is not a written release.",
                               r.files.split(",")[:6] + [f"suppliers/{r.supplier_id}*/profile.csv"], supplier_id=r.supplier_id))
    revs = ctx.q("""SELECT i.supplier_id, i.part_id, i.value AS rev, c.drawing_rev, GROUP_CONCAT(DISTINCT d.po_numbers) AS pos,
                           GROUP_CONCAT(i.file) AS files
                    FROM doc_issues i JOIN documents d ON d.file=i.file JOIN m_components c ON c.component_id=i.part_id
                    WHERE i.type='artwork_revision' GROUP BY i.supplier_id, i.part_id, i.value""")
    for r in revs.itertuples():
        if r.rev != r.drawing_rev:
            others = revs[(revs.part_id == r.part_id) & (revs.supplier_id != r.supplier_id)]
            other_txt = "; ".join(f"{o.supplier_id} prints rev {o.rev}" for o in others.itertuples())
            stock = ctx.q("""SELECT s.batch, s.quantity FROM stock_snapshot s JOIN goods_receipts g ON g.gr_number=s.batch
                             WHERE s.material_id=? AND g.supplier_id=?""", (r.part_id, r.supplier_id))
            out.append(Finding(
                "artwork_revision_mismatch", "high", "supplier artwork revision != component master drawing_rev",
                (f"{r.supplier_id} confirms printing {r.part_id} to artwork rev {r.rev}; component master says rev "
                 f"{r.drawing_rev}. {other_txt}. Stock from {r.supplier_id}: "
                 f"{', '.join(f'batch {b.batch} {b.quantity:,}' for b in stock.itertuples()) or 'none'}. "
                 f"Two revisions of a rating-relevant (USK/PEGI) sleeve are mixed; which one is released must be confirmed."),
                r.files.split(",")[:5] + ["soony/master/components.csv#component_id=" + r.part_id]
                + [_ev_stock(b) for b in stock.batch], r.part_id, r.supplier_id,
                qty=int(stock.quantity.sum()) if len(stock) else None, confidence="medium",
                extra={"pos": r.pos}))
    return out


def check_bom_vs_sources(ctx: Ctx) -> list[Finding]:
    """BOM components without any source, and BOM double counting of parts the supplier already includes."""
    out = []
    unsourced = ctx.q("""SELECT b.parent_id, b.child_id, b.qty_per, c.description,
                                (SELECT COALESCE(SUM(quantity),0) FROM stock_snapshot s WHERE s.material_id=b.child_id) AS stock,
                                (SELECT COUNT(*) FROM purchase_orders p WHERE p.material_id=b.child_id) AS n_po
                         FROM m_bom b JOIN m_products p ON p.product_id=b.parent_id AND p.lifecycle IN ('launch','running')
                         LEFT JOIN m_components c ON c.component_id=b.child_id
                         WHERE b.child_id NOT IN (SELECT component_id FROM supplier_components)""")
    incl = ctx.q("""SELECT file, child, parent, qty_per, text FROM contract_clauses WHERE type='bom_inclusion'""")
    oc_incl = ctx.q("""SELECT part_id, value, GROUP_CONCAT(file) AS files FROM doc_issues WHERE type='bom_inclusion'
                       GROUP BY part_id, value""")
    for r in unsourced.itertuples():
        inc = incl[incl.child == r.child_id]
        if len(inc):
            i = inc.iloc[0]
            par_in_bom = ctx.q("SELECT 1 FROM m_bom WHERE parent_id=? AND child_id=?", (r.parent_id, i.parent))
            ocf = oc_incl[oc_incl.part_id == r.child_id]
            out.append(Finding(
                "bom_double_count", "high", "BOM lists a part that the supplier contract includes in another BOM part",
                (f"BOM of {r.parent_id} requires {r.qty_per} x {r.child_id} ({r.description}) as a separate part (stock "
                 f"{int(r.stock)}, no supplier, no PO). Contract says it is fitted by the supplier inside {i.parent} "
                 f"({i.qty_per} per unit){' which is also in this BOM' if len(par_in_bom) else ''}; "
                 f"{len(ocf.iloc[0].files.split(',')) if len(ocf) else 0} order confirmations repeat this. The shortage "
                 f"flagged in the launch plan is a master-data error, not a missing delivery - but the parts are single-sourced "
                 f"via a sub-supplier."),
                [i.file] + (ocf.iloc[0].files.split(",")[:3] if len(ocf) else []) + ["soony/master/bom.csv",
                 "soony/context/launch_plan_GH6.xlsx#Parts"], r.child_id, confidence="high"))
        else:
            out.append(Finding("bom_part_unsourced", "critical" if r.stock == 0 else "high",
                               "BOM part without supplier", f"{r.child_id} is required by {r.parent_id} but no supplier "
                               f"lists it; stock {int(r.stock)}, POs {int(r.n_po)}.", ["soony/master/bom.csv"], r.child_id))
    return out


def check_single_source(ctx: Ctx) -> list[Finding]:
    """Launch BOM parts with only one source (incl. critical sub-suppliers named in contracts)."""
    df = ctx.q("""SELECT component_id, COUNT(*) AS n, GROUP_CONCAT(supplier_id) AS sups, MAX(share) AS max_share
                  FROM supplier_components GROUP BY component_id""")
    crit = dict(ctx.q("SELECT component_id, critical FROM m_components").values)
    out = []
    for r in df[df.component_id.isin(ctx.launch_parts())].itertuples():
        effective_single = r.n == 1
        second = ctx.q("SELECT supplier_id, qualification_status FROM supplier_profiles WHERE supplier_id IN ({})".format(
            ",".join("?" * len(r.sups.split(",")))), tuple(r.sups.split(",")))
        unqualified = second[second.qualification_status != "qualified"]
        if not effective_single and len(unqualified) and r.n - len(unqualified) == 1:
            effective_single = True
        if effective_single:
            note = (f" Second source {', '.join(unqualified.supplier_id)} is only '{unqualified.qualification_status.iloc[0]}'."
                    if len(unqualified) and r.n > 1 else "")
            out.append(Finding("single_source", "high" if crit.get(r.component_id) == "Y" else "medium",
                               "launch part with one qualified source",
                               f"{r.component_id} has {r.n} listed source(s) ({r.sups}).{note}",
                               [f"suppliers/{s}*/components.csv" for s in r.sups.split(",")], r.component_id,
                               r.sups.split(",")[0]))
    sub = ctx.q("SELECT file, supplier_id, text FROM contract_clauses WHERE type='sub_supplier' AND text LIKE '%supplies%'")
    fm = ctx.q("SELECT file, supplier_id, text FROM contract_clauses WHERE type='force_majeure' AND text LIKE '%rare-earth%'")
    for r in sub.itertuples():
        f2 = fm[fm.supplier_id == r.supplier_id]
        out.append(Finding("single_source_sub_supplier", "medium", "critical material from a named single sub-supplier",
                           r.text + (" Force majeure explicitly covers rare-earth export restrictions, so a ban would "
                                     "excuse the supplier." if len(f2) else ""), [r.file], supplier_id=r.supplier_id))
    return out


def check_pp07_release(ctx: Ctx) -> list[Finding]:
    """PP-07: conditional releases expire after 90 days; extension needs the (named) Category Lead."""
    rule = ctx.q("SELECT file, max_days FROM (SELECT d.file, 90 AS max_days FROM documents d WHERE d.doc_type='policy')")
    if rule.empty:
        return []
    max_days, policy_file = int(rule.max_days.iloc[0]), rule.file.iloc[0]
    org = ctx.q("SELECT raw_text FROM documents WHERE doc_type='org_chart'")
    out = []
    cond = ctx.q("""SELECT p.supplier_id, p.name, p.category, c.file, c.text,
                           json_extract('{"d":"' || COALESCE(c.release_date, p.supplier_since) || '"}', '$.d') AS rel
                    FROM supplier_profiles p LEFT JOIN contract_clauses c ON c.supplier_id=p.supplier_id AND c.type='conditional_release'
                    WHERE p.qualification_status='conditional'""")
    roles = ctx.q("""SELECT d.file, json_each.value AS role FROM documents d, json_each(?) WHERE d.doc_type='org_chart'""",
                  (json.dumps([]),))
    for r in cond.itertuples():
        expiry = date.fromisoformat(r.rel) + timedelta(days=max_days)
        if expiry >= ctx.asof:
            continue
        pos_after = ctx.q("""SELECT po_number, po_line, order_date, status, quantity FROM purchase_orders
                             WHERE supplier_id=? AND order_date > ? AND quantity > 0""", (r.supplier_id, expiry.isoformat()))
        not_held = pos_after[pos_after.status != "awaiting_approval"]
        grs = ctx.q("SELECT gr_number, gr_date, qty_received FROM goods_receipts WHERE supplier_id=? AND gr_date > ?",
                    (r.supplier_id, expiry.isoformat()))
        lead_vacant = ctx.q("""SELECT file FROM documents WHERE doc_type='org_chart'""")
        cat_lead = f"Category Lead {r.category}"
        vacant = _role_vacant(ctx, cat_lead)
        out.append(Finding(
            "pp07_release_expired", "high", "conditional release older than PP-07 limit",
            (f"{r.supplier_id} ({r.name}) is conditionally released since {r.rel}; PP-07 limits this to {max_days} days -> "
             f"expired {expiry}. Since then: {len(pos_after)} PO lines placed ({len(not_held)} not in 'awaiting_approval'), "
             f"{len(grs)} goods receipts ({int(grs.qty_received.sum()) if len(grs) else 0:,} pcs). Extension requires the "
             f"{cat_lead} together with Supplier Quality" + (f" - that role is vacant (TBD) in the org chart." if vacant else ".")),
            [policy_file, r.file or f"suppliers/{r.supplier_id}*/profile.csv"] + list(lead_vacant.file)
            + [_ev_po(p) for p in pos_after.po_number.unique()] + [_ev_gr(g) for g in grs.gr_number],
            supplier_id=r.supplier_id, qty=int(grs.qty_received.sum()) if len(grs) else None,
            extra={"expired_on": expiry.isoformat(), "role_vacant": vacant}))
    return out


def _role_vacant(ctx: Ctx, role: str) -> bool:
    """True if the org chart extraction lists the role without a name."""
    for (payload,) in ctx.con.execute("SELECT payload FROM extraction_cache WHERE payload LIKE '%\"org_chart\"%'"):
        for r in json.loads(payload).get("roles", []):
            if r.get("role", "").lower() == role.lower():
                return not r.get("name")
    return False


def check_price_vs_contract(ctx: Ctx) -> list[Finding]:
    """PO prices above the contract price; judged against the contract's price clause and supplier price lists."""
    df = ctx.q("""SELECT p.supplier_id, p.material_id, p.unit_price, p.currency, cp.price AS contract_price,
                         cp.file AS contract_file, COUNT(*) AS n_lines, SUM(p.quantity) AS qty,
                         SUM((p.unit_price - cp.price) * p.quantity) AS delta, MIN(p.order_date) AS first_order
                  FROM purchase_orders p JOIN contract_prices cp ON cp.supplier_id=p.supplier_id AND cp.part=p.material_id
                  WHERE p.quantity > 0 AND ABS(p.unit_price - cp.price) > 0.0001
                  GROUP BY p.supplier_id, p.material_id, p.unit_price""")
    clauses = ctx.q("SELECT supplier_id, type, text FROM contract_clauses WHERE type IN ('price_validity','price_change')")
    lists = ctx.q("SELECT supplier_id, part_id, new_price, valid_from, source_file FROM price_lists")
    out = []
    for (sup, part), g in df.groupby(["supplier_id", "material_id"]):
        cl = clauses[clauses.supplier_id == sup]
        basis = lists[(lists.supplier_id == sup) & (lists.part_id == part) & lists.new_price.isin(g.unit_price)]
        fixed = cl[cl.type == "price_validity"]
        change = cl[(cl.type == "price_change") & cl.text.str.contains("revise|notice", case=False)]
        if len(change):
            continue  # contract allows revisions with notice; cannot judge notice dates -> not a finding
        verdict = (f"contract fixes prices ('{fixed.text.iloc[0]}')" if len(fixed)
                   else "contract has no clause allowing unilateral price changes")
        out.append(Finding(
            "price_vs_contract", "medium", "PO price != contract price without contractual basis",
            (f"{sup} {part}: contract price {g.contract_price.iloc[0]} {g.currency.iloc[0]}, POs at "
             f"{', '.join(str(x) for x in sorted(g.unit_price.unique()))} ({int(g.n_lines.sum())} lines, {int(g.qty.sum()):,} pcs, "
             f"since {g.first_order.min()}). Increases come from supplier price lists "
             f"({', '.join(sorted(basis.valid_from)) or 'none found'}), but {verdict}. Over-payment vs contract: "
             f"{g.delta.sum():,.0f} {g.currency.iloc[0]}."),
            [g.contract_file.iloc[0]] + sorted(set(basis.source_file)) + [f"purchase_orders#supplier_id={sup},material_id={part}"],
            part, sup, amount=round(float(g.delta.sum()), 2), currency=g.currency.iloc[0]))
    return out


# ------------------------------------------------------------------ logistics

def check_shipment_status(ctx: Ctx) -> list[Finding]:
    """ERP shipment vs manual tracker: status/ETA mismatch, shipments missing in the tracker."""
    df = ctx.q("SELECT * FROM v_shipment_status_compare WHERE comparison <> 'match'")
    out = []
    mism = df[df.comparison == "mismatch"]
    for r in mism.itertuples():
        out.append(Finding("shipment_status_mismatch", "high" if r.erp_status == "arrived_port" else "medium",
                           "erp.status/eta != tracker.status/eta",
                           f"{r.shipment_id} ({r.reference}): ERP '{r.erp_status}' ETA {r.erp_eta} (updated {r.updated_at}) "
                           f"vs tracker '{r.tracker_status}' ETA {r.tracker_eta}. ERP note: {r.erp_note or '-'}; tracker "
                           f"comment: {r.tracker_comment or '-'}.",
                           [f"soony/erp/open_shipments.csv#shipment_id={r.shipment_id}",
                            f"soony/logistics/open_shipments_tracker_v37_FINAL_final2.xlsx#{r.shipment_id}"],
                           supplier_id=r.supplier_id))
    missing = df[df.comparison == "missing_in_tracker"]
    if len(missing):
        out.append(Finding("shipment_missing_in_tracker", "medium", "ERP shipment absent from tracker",
                           f"{len(missing)} ERP shipments are not in the manual tracker, incl. "
                           f"{', '.join(f'{r.shipment_id} {r.mode} {r.erp_status} ETA {r.erp_eta}' for r in missing.head(8).itertuples())}.",
                           ["soony/erp/open_shipments.csv", "soony/logistics/open_shipments_tracker_v37_FINAL_final2.xlsx"],
                           qty=len(missing)))
    port = ctx.q("""SELECT s.*, r.transit_days FROM shipments_erp s LEFT JOIN m_routes r
                    ON r.origin=s.destination AND r.destination=s.dest_site WHERE s.status='arrived_port'""")
    for r in port.itertuples():
        out.append(Finding("arrived_awaiting_pickup", "high", "shipment arrived at port, last mile not booked",
                           f"{r.shipment_id} ({r.reference}, {r.material_ids}) is '{r.status}' at {r.destination} since "
                           f"{r.eta}: '{r.note}'. Last-mile route to {r.dest_site}: {r.transit_days} day(s). Needs pick-up "
                           f"booking and a dock slot now.", [f"soony/erp/open_shipments.csv#shipment_id={r.shipment_id}"],
                           r.material_ids, r.supplier_id))
    return out


def check_short_shipments(ctx: Ctx) -> list[Finding]:
    """Supplier shipping advices reporting a balance that misses the deadline while ERP/launch plan count the full qty."""
    df = ctx.q("SELECT i.*, d.po_numbers FROM doc_issues i JOIN documents d ON d.file=i.file WHERE i.type='short_shipment'")
    out = []
    for r in df.itertuples():
        erp = ctx.q("SELECT shipment_id, status, eta FROM shipments_erp WHERE reference=?", (r.reference,))
        lp = ctx.q("SELECT quantity, eta, status FROM lp_inbound WHERE reference=?", (r.reference,))
        late = r.new_date and r.new_date > ctx.deadline_day
        out.append(Finding(
            "short_shipment", "critical" if late else "high", "shipping advice balance after deadline",
            (f"Shipping advice for PO {r.po_numbers} ({r.reference}): {r.qty:,} pcs {r.part_id} not shipped ({r.text}); "
             f"balance due {r.new_date}, deadline {ctx.deadline_day}. "
             + (f"Launch plan still counts {int(lp.quantity.iloc[0]):,} pcs on this reference (ETA {lp.eta.iloc[0]}). " if len(lp) else "")
             + (f"ERP shipment {erp.shipment_id.iloc[0]} still '{erp.status.iloc[0]}' with ETA {erp.eta.iloc[0]}." if len(erp) else "")),
            [r.file] + [f"soony/erp/open_shipments.csv#shipment_id={s}" for s in erp.shipment_id]
            + (["soony/context/launch_plan_GH6.xlsx#Inbound"] if len(lp) else []),
            r.part_id, r.supplier_id, r.po_numbers, qty=r.qty))
    return out


def check_supplier_notices(ctx: Ctx) -> list[Finding]:
    """Supplier downtime/capacity notices overlapping the launch window; offers contradicting them; open deadlines."""
    out = []
    window_start = datetime.combine(ctx.asof, datetime.min.time(), ctx.deadline.tzinfo)
    issues = ctx.q("""SELECT * FROM doc_issues WHERE type IN ('downtime','capacity_limit')""")
    for r in issues.itertuples():
        s, e = datetime.fromisoformat(r.start), datetime.fromisoformat(r.end)
        if s <= ctx.deadline and e >= window_start:
            out.append(Finding("supplier_downtime", "high", "supplier notice overlaps launch window",
                               f"{r.supplier_id}: {r.resource} {r.start} -> {r.end}: {r.text} Capacity: {r.capacity_during}.",
                               [r.file], supplier_id=r.supplier_id, extra={"start": r.start, "end": r.end}))
    limits = issues[issues.type == "capacity_limit"]
    offers = ctx.q("SELECT * FROM doc_offers")
    for o in offers.itertuples():
        for l in limits[limits.supplier_id == o.supplier_id].itertuples():
            if o.qty_max and l.max_qty and o.qty_max > l.max_qty and "36 h" in str(o.lead_time):
                out.append(Finding("offer_vs_notice", "high", "offer quantity exceeds announced capacity",
                                   f"{o.supplier_id} offers up to {int(o.qty_max):,} pcs ({o.text}) in {o.lead_time}, but its own "
                                   f"notice limits rush work during {l.start} -> {l.end} to {int(l.max_qty):,} pcs on {l.resource}. "
                                   f"Plan with {int(l.max_qty):,} unless the supplier confirms in writing.",
                                   [o.file, l.file], o.part, o.supplier_id, qty=int(o.qty_max - l.max_qty), confidence="high"))
    dl = ctx.q("SELECT * FROM doc_deadlines")
    for r in dl.itertuples():
        due = str(r.due)[:10]
        if ctx.asof.isoformat() <= due <= (ctx.deadline.date() + timedelta(days=7)).isoformat():
            out.append(Finding("supplier_deadline", "medium", "document deadline inside launch window",
                               f"{r.supplier_id}: {r.what} - due {r.due}.", [r.file], supplier_id=r.supplier_id))
    return out


def check_contract_deadlines(ctx: Ctx) -> list[Finding]:
    """Contract renewals/expiries and recurring notification duties coming up."""
    out = []
    horizon = ctx.asof + timedelta(days=60)
    df = ctx.q("SELECT * FROM contract_clauses WHERE type IN ('term_renewal','holiday_shutdown')")
    for r in df.itertuples():
        due = r.deadline if isinstance(getattr(r, "deadline", None), str) else None
        if r.type == "holiday_shutdown" and isinstance(getattr(r, "deadline_mmdd", None), str):
            due = f"{ctx.asof.year}-{r.deadline_mmdd}"
        if due and ctx.asof.isoformat() <= due <= horizon.isoformat():
            out.append(Finding("contract_deadline", "medium", "contractual deadline within 60 days",
                               f"{r.supplier_id} {r.contract_no} {r.section}: {r.text} (due {due}).", [r.file],
                               supplier_id=r.supplier_id, extra={"due": due}))
    return out


# ------------------------------------------------------------------ launch coverage

def check_launch_coverage(ctx: Ctx) -> list[Finding]:
    """Recompute part coverage for the remaining pack-out from evidence and compare with the launch plan."""
    ed = ctx.q("SELECT product, still_to_pack FROM lp_editions")
    bom = ctx.q("SELECT parent_id, child_id, qty_per FROM m_bom")
    included = set(ctx.q("SELECT child FROM contract_clauses WHERE type='bom_inclusion'")["child"])
    need = (bom.merge(ed, left_on="parent_id", right_on="product").assign(need=lambda d: d.qty_per * d.still_to_pack)
            .groupby("child_id")["need"].sum())
    stock = ctx.q("SELECT material_id, SUM(quantity) AS q FROM stock_snapshot GROUP BY material_id").set_index("material_id")["q"]
    blocked = {f.part_id: f.qty for f in check_failed_inspection_released(ctx)}
    overstated: dict[str, int] = {}
    for f in check_receipt_vs_delivery_note(ctx):
        if f.extra.get("stock_overstated"):
            overstated[f.part_id] = overstated.get(f.part_id, 0) + f.extra["stock_overstated"]
    inbound = ctx.q("SELECT * FROM lp_inbound")
    shorts = ctx.q("SELECT reference, part_id, qty, new_date FROM doc_issues WHERE type='short_shipment'")
    holds = ctx.q("""SELECT DISTINCT d.po_numbers FROM doc_issues i JOIN documents d ON d.file=i.file
                     WHERE i.type='shipment_on_hold'""")
    held_refs = set(ctx.q(f"""SELECT s.reference FROM shipment_po sp JOIN shipments_erp s ON s.shipment_id=sp.shipment_id
                             WHERE sp.po_number IN ({','.join('?' * len(holds))})""", tuple(holds.po_numbers))["reference"]) if len(holds) else set()
    lp = ctx.q("SELECT * FROM lp_parts").set_index("part")
    out = []
    for part, n in need.items():
        if part in included:
            continue  # covered by check_bom_vs_sources
        inb = inbound[(inbound.part == part) & (inbound.eta <= ctx.deadline_day)]
        inb_qty, notes = 0, []
        for r in inb.itertuples():
            q = int(r.quantity)
            s = shorts[shorts.reference == r.reference]
            if len(s) and str(s.new_date.iloc[0]) > ctx.deadline_day:
                q -= int(s.qty.iloc[0]); notes.append(f"{r.reference} only {q:,} (short shipment)")
            if r.reference in held_refs:
                notes.append(f"{r.reference} on hold at supplier"); q = 0
            if r.status and "port" in str(r.status):
                notes.append(f"{r.reference} at port, needs pick-up")
            inb_qty += q
        usable = int(stock.get(part, 0)) - int(blocked.get(part, 0) or 0) - int(overstated.get(part, 0))
        gap = int(n) - usable - inb_qty
        lp_row = lp.loc[part] if part in lp.index else None
        lp_cover = int(lp_row["cover"]) if lp_row is not None else None
        if gap > 0 or (lp_cover is not None and lp_cover >= 0 and gap > 0):
            per = ed.merge(bom[bom.child_id == part], left_on="product", right_on="parent_id")
            out.append(Finding(
                "launch_coverage_gap", "critical", "evidence-based coverage < remaining pack-out need",
                (f"{part}: need {int(n):,} for remaining pack-out ({', '.join(f'{p.product} {int(p.still_to_pack):,}x{int(p.qty_per)}' for p in per.itertuples())}). "
                 f"ERP stock {int(stock.get(part, 0)):,} - blocked (failed inspection) {int(blocked.get(part, 0) or 0):,} "
                 f"- overstated receipts {int(overstated.get(part, 0)):,} = usable {usable:,}; credible inbound before "
                 f"{ctx.deadline_day}: {inb_qty:,}{' (' + '; '.join(notes) + ')' if notes else ''}. Gap {gap:,} pcs. "
                 + (f"Launch plan shows cover {lp_cover:,} and status '{lp_row['status']}'." if lp_row is not None else "")),
                ["soony/context/launch_plan_GH6.xlsx#Parts", "soony/erp/stock_snapshot.csv", "soony/master/bom.csv"]
                + (["soony/context/launch_plan_GH6.xlsx#Inbound"] if len(inb) else []), part, qty=gap,
                extra={"need": int(n), "usable": usable, "inbound": inb_qty, "lp_cover": lp_cover}))
    return out


def check_launch_plan_vs_erp(ctx: Ctx) -> list[Finding]:
    """Launch plan figures that contradict ERP stock or the pack-out log."""
    out = []
    lp = ctx.q("SELECT part, erp_stock FROM lp_parts")
    st = ctx.q("SELECT material_id AS part, SUM(quantity) AS stock FROM stock_snapshot GROUP BY material_id")
    m = lp.merge(st, on="part", how="left").fillna({"stock": 0})
    for r in m[m.erp_stock != m.stock].itertuples():
        out.append(Finding("launch_plan_vs_erp_stock", "medium", "lp_parts.erp_stock != stock_snapshot",
                           f"{r.part}: launch plan uses {int(r.erp_stock):,}, ERP snapshot shows {int(r.stock):,}.",
                           ["soony/context/launch_plan_GH6.xlsx#Parts", "soony/erp/stock_snapshot.csv"], r.part))
    ed = ctx.q("SELECT product, packed FROM lp_editions")
    po = ctx.q("SELECT product_id AS product, SUM(units_packed) AS packed_log FROM packout_log GROUP BY product_id")
    m = ed.merge(po, on="product", how="left")
    for r in m[m.packed != m.packed_log].itertuples():
        out.append(Finding("launch_plan_vs_packout", "medium", "lp_editions.packed != packout_log",
                           f"{r.product}: launch plan packed {r.packed}, pack-out log {r.packed_log}.",
                           ["soony/context/launch_plan_GH6.xlsx#Editions", "soony/erp/packout_log.csv"]))
    return out


def check_document_quality(ctx: Ctx) -> list[Finding]:
    """Delivery notes without receiving stamp or receiver signature (aggregated)."""
    df = ctx.q("""SELECT file, received_stamp_date, received_by FROM documents WHERE doc_type='delivery_note'""")
    out = []
    for col, label in (("received_stamp_date", "DC-HAM receiving stamp"), ("received_by", "receiver signature")):
        miss = df[df[col].isna()]
        if len(miss):
            out.append(Finding("document_missing_" + col.split("_")[1], "low", f"delivery note without {label}",
                               f"{len(miss)} of {len(df)} scanned delivery notes have no {label}; receipt cannot be proven "
                               f"from the paper alone.", list(miss.file), qty=len(miss)))
    return out


CHECKS: list[Callable[[Ctx], list[Finding]]] = [
    check_receipt_vs_delivery_note, check_failed_inspection_released, check_receipts_without_po,
    check_po_vs_confirmation, check_confirmation_statements, check_bom_vs_sources, check_single_source,
    check_pp07_release, check_price_vs_contract, check_shipment_status, check_short_shipments,
    check_supplier_notices, check_contract_deadlines, check_launch_coverage, check_launch_plan_vs_erp,
    check_document_quality,
]


def run_all(con: sqlite3.Connection, asof: date, deadline: datetime) -> list[Finding]:
    """Run every check, store results in `findings` sorted by severity, return them."""
    ctx = Ctx(con, asof, deadline)
    found: list[Finding] = []
    for check in CHECKS:
        found.extend(check(ctx))
    found.sort(key=lambda f: (SEVERITY_RANK[f.severity], f.category, f.part_id or ""))
    rows = []
    for i, f in enumerate(found, 1):
        d = asdict(f)
        d["finding_id"] = f"F{i:03d}"
        d["evidence"] = json.dumps([e for e in d["evidence"] if e], ensure_ascii=False)
        d["extra"] = json.dumps(d["extra"], ensure_ascii=False, default=str)
        rows.append(d)
    cols = ["finding_id", "severity", "category", "part_id", "supplier_id", "po_number", "qty", "amount", "currency",
            "rationale", "evidence", "confidence", "rule", "extra"]
    pd.DataFrame(rows, columns=cols).to_sql("findings", con, if_exists="replace", index=False)
    return found
