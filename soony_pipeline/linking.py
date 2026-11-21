"""Document tables and cross-source SQL views.

Join keys used throughout:
    po_number (+ po_line)       purchase orders <-> receipts, confirmations, shipments, delivery notes
    delivery_note / doc_no      goods receipts <-> scanned delivery notes
    gr_number == batch          goods receipts <-> stock snapshot <-> inspection reports
    part_id / material_id       everything <-> component master / BOM
    supplier_id                 everything <-> supplier profiles, contracts, notices
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pandas as pd


def _effective_qty(line: dict[str, Any]) -> int | None:
    """Quantity the document actually certifies: corrected > handwritten > printed."""
    for key in ("qty_corrected", "qty_handwritten", "qty_printed"):
        if line.get(key) is not None:
            return line[key]
    return None


def write_document_tables(con: sqlite3.Connection, records: list[dict[str, Any]]) -> dict[str, int]:
    """Flatten extraction records into relational tables."""
    docs, lines, marks, issues, offers, deadlines, clauses, prices = [], [], [], [], [], [], [], []
    for r in records:
        f = r["file"]
        docs.append({
            "file": f, "sha256": r.get("sha256"), "doc_type": r.get("doc_type"), "language": r.get("language"),
            "doc_no": r.get("doc_no"), "doc_date": r.get("doc_date"), "supplier_id": r.get("supplier_id"),
            "po_numbers": "|".join(r.get("po_numbers") or []), "gr_number": r.get("gr_number"),
            "received_stamp_date": r.get("received_stamp"), "received_by": next(
                (s.replace("received by ", "") for s in r.get("signatures", []) if s.startswith("received by")), None),
            "handwritten_corrections": r.get("handwritten_corrections"), "decision": r.get("decision"),
            "valid_from": r.get("valid_from"), "valid_to": r.get("valid_to"), "header": json.dumps(r.get("header")) if r.get("header") else None,
            "extractor": r.get("extractor"), "status": r.get("status"), "confidence": r.get("confidence"),
            "notes": r.get("notes"), "summary": r.get("summary"), "free_text": r.get("free_text"),
            "raw_text": r.get("raw_text"),
        })
        for i, ln in enumerate(r.get("lines", []), 1):
            lines.append({
                "file": f, "doc_line": i, "po_number": ln.get("po_number"), "po_line": ln.get("po_line"),
                "part_raw": ln.get("part_raw"), "part_id": ln.get("part_id"), "description": ln.get("description"),
                "qty_printed": ln.get("qty_printed"), "qty_handwritten": ln.get("qty_handwritten"),
                "qty_corrected": ln.get("qty_corrected"), "qty_effective": _effective_qty(ln),
                "qty_ordered": ln.get("qty_ordered"), "qty_balance": ln.get("qty_balance"),
                "unit_price": ln.get("unit_price"), "currency": ln.get("currency"),
                "confirmed_date": ln.get("confirmed_date"), "packages": ln.get("packages"),
                "artwork_rev": ln.get("artwork_rev"), "lot_size": ln.get("lot_size"), "defective": ln.get("defective"),
                "sample": ln.get("sample"), "accept": ln.get("accept"), "reject": ln.get("reject"),
            })
        for s in r.get("stamps", []):
            marks.append({"file": f, "kind": "stamp", "text": s})
        for s in r.get("signatures", []):
            marks.append({"file": f, "kind": "signature", "text": s})
        for it in r.get("issues", []):
            issues.append({"file": f, "supplier_id": r.get("supplier_id"), **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                                                                              for k, v in it.items()}})
        for o in r.get("offers", []):
            offers.append({"file": f, "supplier_id": r.get("supplier_id"), **o})
        for d in r.get("deadlines", []):
            deadlines.append({"file": f, "supplier_id": r.get("supplier_id"), **d})
        for c in r.get("clauses", []):
            clauses.append({"file": f, "supplier_id": r.get("supplier_id"), "contract_no": r.get("doc_no"),
                            **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in c.items()}})
        for p in r.get("prices", []):
            prices.append({"file": f, "supplier_id": r.get("supplier_id"), "contract_no": r.get("doc_no"),
                           "valid_from": r.get("valid_from"), "valid_to": r.get("valid_to"), **p})
    tables = {"documents": docs, "doc_lines": lines, "doc_marks": marks, "doc_issues": issues, "doc_offers": offers,
              "doc_deadlines": deadlines, "contract_clauses": clauses, "contract_prices": prices}
    for name, rows in tables.items():
        pd.DataFrame(rows).to_sql(name, con, if_exists="replace", index=False)
    return {k: len(v) for k, v in tables.items()}


def write_xref(con: sqlite3.Connection, xref: dict[str, str]) -> None:
    """Supplier part number -> Soony part id."""
    pd.DataFrame([{"supplier_part": k, "part_id": v} for k, v in xref.items()]).to_sql(
        "part_xref", con, if_exists="replace", index=False)


VIEWS = {
    # Stock per batch, enriched with its goods receipt, the scanned delivery note line and any inspection result.
    "v_stock_batch_receipt": """
        SELECT s.material_id, s.batch, s.quantity AS stock_qty, s.snapshot_date,
               g.gr_date, g.po_number, g.po_line, g.supplier_id, g.qty_ordered, g.qty_received, g.delivery_note, g.remark,
               dn.file AS dn_file, dl.qty_printed AS dn_qty_printed, dl.qty_handwritten AS dn_qty_handwritten,
               dl.qty_effective AS dn_qty_effective, dn.received_stamp_date, dn.received_by,
               ir.file AS inspection_file, ir.decision AS inspection_decision
        FROM stock_snapshot s
        LEFT JOIN goods_receipts g ON g.gr_number = s.batch
        LEFT JOIN documents dn ON dn.doc_type = 'delivery_note' AND dn.doc_no = g.delivery_note
        LEFT JOIN doc_lines dl ON dl.file = dn.file AND dl.part_id = g.material_id
             AND (dl.po_number IS NULL OR dl.po_number = g.po_number)
        LEFT JOIN documents ir ON ir.doc_type = 'inspection_report' AND ir.gr_number = s.batch""",
    # Goods receipt vs. scanned delivery note line (only receipts with a scan).
    "v_receipt_vs_delivery_note": """
        SELECT g.gr_number, g.gr_date, g.po_number, g.po_line, g.supplier_id, g.material_id, g.qty_ordered, g.qty_received,
               g.remark, g.delivery_note, d.file AS dn_file, dl.qty_printed, dl.qty_handwritten, dl.qty_effective,
               d.handwritten_corrections, d.received_stamp_date, d.received_by, d.confidence
        FROM goods_receipts g
        JOIN documents d ON d.doc_type = 'delivery_note' AND d.doc_no = g.delivery_note
        LEFT JOIN doc_lines dl ON dl.file = d.file AND dl.part_id = g.material_id
             AND (dl.po_number IS NULL OR dl.po_number = g.po_number OR g.po_number IS NULL)""",
    # Open PO lines with confirmation and every shipment (ERP + tracker) that references the PO.
    "v_open_po_shipments": """
        SELECT p.po_number, p.po_line, p.supplier_id, p.material_id, p.quantity, p.unit_price, p.currency,
               p.order_date, p.requested_date, p.promised_date, p.status, p.incoterm,
               oc.file AS oc_file, ol.qty_printed AS oc_qty, ol.unit_price AS oc_price, ol.confirmed_date AS oc_date,
               se.shipment_id, se.mode, se.reference, se.etd, se.eta, se.status AS erp_ship_status,
               st.status AS tracker_status, st.eta AS tracker_eta
        FROM purchase_orders p
        LEFT JOIN doc_lines ol ON ol.po_number = p.po_number AND ol.po_line = p.po_line
             AND ol.file IN (SELECT file FROM documents WHERE doc_type = 'order_confirmation')
        LEFT JOIN documents oc ON oc.file = ol.file
        LEFT JOIN shipment_po sp ON sp.po_number = p.po_number
        LEFT JOIN shipments_erp se ON se.shipment_id = sp.shipment_id
             AND (se.material_ids LIKE '%' || p.material_id || '%')
        LEFT JOIN shipments_tracker st ON st.shipment_id = se.shipment_id
        WHERE p.status IN ('open', 'awaiting_approval')""",
    # PO line vs. supplier order confirmation line.
    "v_po_vs_confirmation": """
        SELECT p.po_number, p.po_line, p.supplier_id, p.material_id, p.status, p.quantity AS po_qty, p.unit_price AS po_price,
               p.currency AS po_currency, p.promised_date, p.requested_date, p.incoterm AS po_incoterm,
               l.file AS oc_file, l.qty_printed AS oc_qty, l.unit_price AS oc_price, l.currency AS oc_currency,
               l.confirmed_date AS oc_date, l.artwork_rev, json_extract(d.header, '$.incoterm') AS oc_incoterm
        FROM purchase_orders p
        JOIN doc_lines l ON l.po_number = p.po_number AND l.po_line = p.po_line
        JOIN documents d ON d.file = l.file AND d.doc_type = 'order_confirmation'""",
    # Supplier with parts, master price, contract price/terms and latest price list.
    "v_supplier_terms": """
        SELECT sc.supplier_id, sp.name, sp.status AS supplier_status, sp.qualification_status, sc.component_id,
               c.description, c.critical, sc.share, sc."primary", sc.unit_price AS master_price, sc.currency,
               sc.lead_time_days, sc.moq, cp.price AS contract_price, cp.contract_no, cp.valid_to AS contract_valid_to,
               (SELECT pl.new_price FROM price_lists pl WHERE pl.supplier_id = sc.supplier_id AND pl.part_id = sc.component_id
                ORDER BY pl.valid_from DESC LIMIT 1) AS latest_list_price,
               (SELECT COUNT(*) FROM supplier_components x WHERE x.component_id = sc.component_id) AS n_sources
        FROM supplier_components sc
        JOIN supplier_profiles sp ON sp.supplier_id = sc.supplier_id
        LEFT JOIN m_components c ON c.component_id = sc.component_id
        LEFT JOIN contract_prices cp ON cp.supplier_id = sc.supplier_id AND cp.part = sc.component_id""",
    # Shipment status ERP vs tracker side by side.
    "v_shipment_status_compare": """
        SELECT COALESCE(e.shipment_id, t.shipment_id) AS shipment_id, e.reference, e.supplier_id, e.mode,
               e.status AS erp_status, t.status AS tracker_status, e.eta AS erp_eta, t.eta AS tracker_eta,
               e.updated_at, e.note AS erp_note, t.comment AS tracker_comment,
               CASE WHEN t.shipment_id IS NULL THEN 'missing_in_tracker'
                    WHEN e.shipment_id IS NULL THEN 'missing_in_erp'
                    WHEN e.status <> t.status OR e.eta <> t.eta THEN 'mismatch' ELSE 'match' END AS comparison
        FROM shipments_erp e LEFT JOIN shipments_tracker t ON t.shipment_id = e.shipment_id
        UNION ALL
        SELECT t.shipment_id, t.reference, t.supplier_id, t.mode, NULL, t.status, NULL, t.eta, NULL, NULL, t.comment,
               'missing_in_erp'
        FROM shipments_tracker t WHERE t.shipment_id NOT IN (SELECT shipment_id FROM shipments_erp)""",
}


def create_views(con: sqlite3.Connection) -> list[str]:
    """(Re)create all linking views."""
    for name, sql in VIEWS.items():
        con.execute(f"DROP VIEW IF EXISTS {name}")
        con.execute(f"CREATE VIEW {name} AS {sql}")
    return list(VIEWS)
