"""World: one consistent snapshot of everything the agents know about a tenant.

Combines canonical tables (ERP/master exports) with facts the Document Reader
extracted from paper, and offers the lookups detectors and the planner need.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from aurora.config import Tenant, get_tenant
from aurora.ingest.documents import DocumentReader
from aurora.ingest.tabular import TabularLoader, normalise_supplier_ids


def _norm_ref(v) -> str:
    """Normalise document/PO references for matching (case, spaces, dashes)."""
    return re.sub(r"[^A-Z0-9]", "", str(v).upper())


def same_ref(a, b) -> bool:
    """References match if one contains the other after normalising ("AWB 123-45678901" ~ "123-45678901")."""
    x, y = _norm_ref(a), _norm_ref(b)
    return bool(x and y) and (x == y or (min(len(x), len(y)) >= 6 and (x in y or y in x)))


@dataclass
class World:
    tenant: Tenant
    tables: dict[str, pd.DataFrame]
    documents: list[dict]
    errors: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, tenant: Tenant | None = None, read_documents: bool = True) -> "World":
        tenant = tenant or get_tenant()
        loads = TabularLoader(tenant).load_all()
        tables = {k: v.frame for k, v in loads.items()}
        known = tables["suppliers"]["supplier_id"].dropna().tolist() if not tables["suppliers"].empty else []
        for name in ("po_lines", "receipts"):
            tables[name] = normalise_supplier_ids(tables[name], known)
        docs, errors = DocumentReader(tenant).extract_all(only_missing=read_documents)
        return cls(tenant=tenant, tables=tables, documents=docs, errors=errors)

    # ---- lookups -------------------------------------------------------------
    def t(self, name: str) -> pd.DataFrame:
        return self.tables.get(name, pd.DataFrame())

    def docs_of(self, *types: str) -> list[dict]:
        return [d for d in self.documents if d.get("doc_type") in types]

    def doc_by_number(self, ref: str) -> list[dict]:
        key = _norm_ref(ref)
        return [d for d in self.documents if d.get("document_number") and _norm_ref(d["document_number"]) == key
                or key and key in _norm_ref(d.get("_source", ""))]

    def docs_for_po(self, po: str) -> list[dict]:
        key = _norm_ref(po)
        return [d for d in self.documents if any(_norm_ref(p) == key for p in d.get("po_numbers", []))
                or key in _norm_ref(d.get("_source", ""))]

    def bom(self, product_id: str, at: datetime | None = None) -> dict[str, float]:
        b = self.t("bom")
        b = b[b["parent_id"] == product_id]
        fitted = set(self.tenant.cfg.get("supplier_fitted_components", []))
        return {r.part_id: float(r.qty_per) for r in b.itertuples() if r.part_id not in fitted}

    def part_name(self, part_id: str) -> str:
        p = self.t("parts")
        row = p[p["part_id"] == part_id]
        return row.iloc[0]["description"] if len(row) else part_id

    def supplier_name(self, supplier_id: str) -> str:
        s = self.t("suppliers")
        row = s[s["supplier_id"] == supplier_id]
        return row.iloc[0]["name"] if len(row) else supplier_id

    def stock_batches(self, part_id: str) -> pd.DataFrame:
        s = self.t("stock")
        return s[(s["part_id"] == part_id) & (s["batch"].astype(str).str.len() > 0)]

    def receipt(self, gr_number: str) -> pd.Series | None:
        r = self.t("receipts")
        hit = r[r["gr_number"].astype(str) == str(gr_number)]
        return hit.iloc[0] if len(hit) else None

    def received_qty(self, po: str, part_id: str) -> float:
        r = self.t("receipts")
        hit = r[(r["po_number"].astype(str) == str(po)) & (r["part_id"] == part_id)]
        return float(hit["qty_received"].sum())

    def po_qty(self, po: str, part_id: str) -> float:
        p = self.t("po_lines")
        hit = p[(p["po_number"].astype(str) == str(po)) & (p["part_id"] == part_id) & (p["quantity"] > 0)]
        return float(hit["quantity"].sum())
