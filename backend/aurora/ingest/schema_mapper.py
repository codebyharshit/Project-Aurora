"""Schema Mapper agent: understands tabular files nobody configured.

For every CSV/XLSX/JSON file not covered by the tenant config, the AI looks at the header and a
few rows and proposes: which canonical table it is (receipts, stock, shipments, ...) and how its
columns map to canonical fields. High-confidence proposals are used immediately and shown as
"understood automatically"; a human can confirm or correct them. Cached by file SHA-256.

The canonical model below is the product's own schema, the same for every customer.
"""
from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import json
from pathlib import Path

from aurora.agents import llm
from aurora.config import Tenant

CANONICAL: dict[str, dict] = {
    "parts": {"desc": "component/material master", "fields": ["part_id", "description", "category", "critical", "drawing_rev"]},
    "products": {"desc": "finished products / editions", "fields": ["product_id", "name", "day_one_qty", "launch_date"]},
    "bom": {"desc": "bill of materials", "fields": ["parent_id", "part_id", "qty_per", "valid_from", "valid_to"]},
    "bom_changes": {"desc": "engineering/revision changes to the BOM", "fields": ["change_id", "parent_id", "part_id", "action", "rev_old", "rev_new", "use_up_old_rev", "effective_from", "reason"]},
    "po_lines": {"desc": "purchase order lines", "fields": ["po_number", "po_line", "supplier_id", "part_id", "quantity", "unit_price", "currency", "order_date", "requested_date", "promised_date", "delivered_date", "status", "buyer"]},
    "receipts": {"desc": "goods receipts booked at the warehouse", "fields": ["gr_number", "gr_date", "po_number", "po_line", "supplier_id", "part_id", "qty_ordered", "qty_received", "delivery_note", "inspector", "remark"]},
    "stock": {"desc": "stock by batch at a snapshot date", "fields": ["snapshot_date", "site", "part_id", "batch", "quantity", "safety_stock", "last_count"]},
    "stock_updates": {"desc": "book stock / packed finished goods per material at a later time (totals, no batches)", "fields": ["site", "part_id", "quantity", "receipts_today", "used_today", "packed_today", "last_count"]},
    "shipments": {"desc": "open inbound shipments", "fields": ["shipment_id", "carrier_id", "mode", "reference", "supplier_id", "po_numbers", "material_ids", "origin", "destination", "etd", "eta", "status", "updated_at", "note"]},
    "shipments_tracker": {"desc": "manually maintained shipment tracker (secondary source)", "fields": ["shipment_id", "carrier_id", "mode", "reference", "supplier_name", "po_numbers", "etd", "eta", "status", "comment"]},
    "packout": {"desc": "packing output per day", "fields": ["date", "site", "product_id", "units_packed"]},
    "suppliers": {"desc": "supplier master / profile", "fields": ["supplier_id", "name", "status", "qualification_status", "contact_name", "contact_email", "preferred_language"]},
    "supplier_parts": {"desc": "what a supplier delivers, prices, lead times", "fields": ["supplier_id", "part_id", "unit_price", "currency", "lead_time_days", "moq", "share"]},
    "supplier_part_changes": {"desc": "changes to supplier lead times / supply flags", "fields": ["part_id", "supplier_id", "action", "lead_time_days_old", "lead_time_days_new", "note"]},
    "routes": {"desc": "transport lanes and transit times", "fields": ["route_id", "origin", "destination", "mode", "carrier_id", "transit_days"]},
    "news": {"desc": "external news items", "fields": ["headline", "summary", "published_at", "source"]},
    "plan_status": {"desc": "launch / production plan or status summary per product", "fields": ["product_id", "demand", "packed", "remaining", "rate_per_hour"]},
    "reference": {"desc": "reference data not used for planning (ports, carriers, sites)", "fields": []},
}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["table", "confidence", "reason", "header_row", "columns"],
    "properties": {
        "table": {"type": "string", "enum": list(CANONICAL)},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "header_row": {"type": "integer"},
        "columns": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["source", "canonical"],
            "properties": {"source": {"type": "string"}, "canonical": {"type": ["string", "null"]}}}},
    },
}

SYSTEM = """You are onboarding a company's data into a supply-planning product. You get one tabular
file (first rows, possibly with title rows above the header). Decide which canonical table it is and
map each source column to a canonical field of that table (null if none fits). header_row is the
0-based index of the header row in the sample. Be strict: choose "reference" if it does not feed
planning. confidence 0-1."""

TABULAR = (".csv", ".xlsx", ".xlsm", ".json", ".tsv")


def _sample(path: Path, n: int = 12) -> list[list[str]]:
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        try:
            sep = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
        return [r for r in csv.reader(io.StringIO(text), delimiter=sep)][:n]
    if suffix in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        rows = []
        for ws in wb:
            rows.append([f"## sheet: {ws.title}"])
            rows += [["" if c is None else str(c) for c in r] for r in ws.iter_rows(values_only=True, max_row=n)
                     if any(c is not None for c in r)]
        return rows[: n * 2]
    data = json.loads(path.read_text(errors="replace"))
    return [[json.dumps(data, ensure_ascii=False)[:3000]]]


class SchemaMapper:
    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        self.root = tenant.data_root
        self.cache = tenant.state_dir / "schema_map.json"
        self.state = json.loads(self.cache.read_text()) if self.cache.exists() else {}

    def configured(self, rel: str) -> bool:
        for spec in self.tenant.cfg.get("tables", {}).values():
            if fnmatch.fnmatch(rel, spec["glob"]) and not any(fnmatch.fnmatch(Path(rel).name, e) for e in spec.get("exclude", [])):
                return True
        return False

    def unknown_files(self) -> list[Path]:
        docs = self.tenant.cfg.get("documents", [])
        out = []
        for p in sorted(self.root.rglob("*")):
            rel = str(p.relative_to(self.root))
            if p.is_file() and p.suffix.lower() in TABULAR and not self.configured(rel) \
                    and not any(fnmatch.fnmatch(rel, d) for d in docs):
                out.append(p)
        return out

    def map_file(self, path: Path) -> dict:
        rel = str(path.relative_to(self.root))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        hit = self.state.get(rel)
        if hit and hit.get("sha256") == sha:
            return hit
        sample = _sample(path)
        content = (f"File: {rel}\nCanonical tables:\n" + "\n".join(f"- {k}: {v['desc']} · fields {v['fields']}"
                                                                   for k, v in CANONICAL.items())
                   + "\n\nSample rows:\n" + "\n".join(" | ".join(r) for r in sample))
        res = llm.structured(system=SYSTEM, content=content, schema=SCHEMA, role="exec", effort="low")
        res["column_map"] = {c["source"]: c["canonical"] for c in res.pop("columns") if c["canonical"]}
        threshold = float(self.tenant.cfg.get("thresholds", {}).get("auto_map_confidence", 0.8))
        res.update(sha256=sha, path=rel,
                   status="auto" if res["confidence"] >= threshold and res["table"] != "reference" else "proposed",
                   confirmed_by=(hit or {}).get("confirmed_by"))
        self.state[rel] = res
        self.cache.write_text(json.dumps(self.state, indent=1, ensure_ascii=False))
        return res

    def run(self) -> list[dict]:
        if not llm.available():
            return []
        return [self.map_file(p) for p in self.unknown_files()]

    def confirm(self, rel: str, by: str, table: str | None = None) -> dict:
        m = self.state[rel]
        if table:
            m["table"] = table
        m["status"], m["confirmed_by"] = "confirmed", by
        self.cache.write_text(json.dumps(self.state, indent=1, ensure_ascii=False))
        return m

    def learned_for(self, table: str) -> list[dict]:
        """Files the mapper assigned to a canonical table (auto or confirmed), for the loader."""
        return [m for m in self.state.values() if m["table"] == table and m["status"] in ("auto", "confirmed")
                and (self.root / m["path"]).exists()]
