"""Document Reader agent: turns any supplier/warehouse document into structured facts.

Works on PDFs, scans (PNG/JPG, incl. handwriting), DOCX and XLSX in any language.
Results are cached by SHA-256, so a new drop only costs the files that changed.
"""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from aurora.agents import llm
from aurora.config import Tenant

N = {"type": ["number", "null"]}
S = {"type": ["string", "null"]}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


LINE = _obj({
    "part_id": S, "supplier_part_ref": S, "description": S,
    "qty_printed": N, "qty_final": N, "unit": S, "revision": S,
    "confirmed_date": S, "unit_price": N, "currency": S,
})

EXTRACTION_SCHEMA = _obj({
    "doc_type": {"type": "string", "enum": [
        "order_confirmation", "delivery_note", "shipping_advice", "packing_list",
        "inspection_report", "supplier_notice", "capacity_notice", "offer", "price_list",
        "bank_details_change", "contract", "policy", "org_chart", "memo", "other"]},
    "language": {"type": "string"},
    "issuer": S,
    "document_number": S,
    "document_date": S,
    "po_numbers": {"type": "array", "items": {"type": "string"}},
    "lines": {"type": "array", "items": LINE},
    "manual_corrections": {"type": "array", "items": {"type": "string"}},
    "inspection": _nullable(_obj({
        "gr_or_batch": S, "lot_size": N, "sample_size": N, "defects": N,
        "result": {"type": "string", "enum": ["accept", "reject", "unknown"]},
        "stock_status_booked": S, "disposition": S, "required_signoff": S,
    })),
    "shipment": _nullable(_obj({
        "reference": S, "ordered_qty": N, "shipped_qty": N, "balance_qty": N,
        "balance_eta": S, "reason": S,
    })),
    "capacity_windows": {"type": "array", "items": _obj({
        "resource": S, "from": S, "to": S, "capacity_during": S})},
    "offer": _nullable(_obj({
        "valid_until": S, "conditions": S, "transport_hours": N,
        "items": {"type": "array", "items": _obj({
            "part_id": S, "description": S, "max_qty": N, "ready_in_hours": N, "price_note": S})},
    })),
    "bank_details": _nullable(_obj({"new_iban": S, "old_iban": S, "effective": S})),
    "rules": {"type": "array", "items": {"type": "string"}},
    "summary_en": {"type": "string"},
    "supply_risks": {"type": "array", "items": {"type": "string"}},
    "confidence": {"type": "number"},
})

SYSTEM = """You are the Document Reader in a procurement operations team.
You read one business document (order confirmation, delivery note, shipping advice,
inspection report, supplier notice, offer, contract, policy, memo, ...) in any language,
including scans with handwriting, stamps and strike-throughs.

Extract facts exactly as the document states them:
- Use internal part IDs (e.g. CMP-...) when printed; otherwise put the supplier's own
  reference in supplier_part_ref.
- Quantities are plain numbers of units. Many European documents write thousands with a
  dot or space: "75.000" and "75 000" mean 75000, "1.200" means 1200. Never return 75 for "75.000".
- qty_printed is the printed number; qty_final is the number after any handwritten or
  struck-through correction (same as printed if none). Describe every correction in
  manual_corrections.
- Dates as ISO 8601 (YYYY-MM-DD or with time) where possible.
- rules: for policies, contracts, memos and org charts, list each rule, limit, deadline,
  role or responsibility as one plain-English sentence.
- supply_risks: anything that could threaten supply, quantity, timing, quality,
  compliance or payment, stated plainly. Empty if none.
- offer.transport_hours: door-to-door transport time if the document states it.
- confidence: 0-1 for how sure you are about the key quantities and statuses.
Do not invent values; use null when the document does not say."""

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
INBOX_TYPES = {".txt", ".pdf", ".docx", ".xlsx", ".xlsm", ".csv", *IMAGE_TYPES}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _image_block(path: Path) -> dict:
    data = path.read_bytes()
    media = IMAGE_TYPES[path.suffix.lower()]
    if len(data) > 3_500_000:  # keep under the API image limit
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((2000, 2000))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data, media = buf.getvalue(), "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                         "data": base64.standard_b64encode(data).decode()}}


def _content_for(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        block = {"type": "document", "title": path.name,
                 "source": {"type": "base64", "media_type": "application/pdf",
                            "data": base64.standard_b64encode(path.read_bytes()).decode()}}
    elif suffix in IMAGE_TYPES:
        block = _image_block(path)
    elif suffix == ".docx":
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            parts += [" | ".join(c.text for c in r.cells) for r in t.rows]
        block = {"type": "text", "text": "\n".join(parts)}
    elif suffix in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        rows = []
        for ws in wb:
            rows.append(f"## sheet {ws.title}")
            rows += [" | ".join("" if c is None else str(c) for c in r)
                     for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
        block = {"type": "text", "text": "\n".join(rows)}
    else:
        block = {"type": "text", "text": path.read_text(errors="replace")}
    return [block, {"type": "text", "text": f"File name: {path.name}\nExtract the facts."}]


class DocumentReader:
    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        self.root = tenant.data_root
        self.cache = tenant.state_dir / "extractions"
        self.cache.mkdir(parents=True, exist_ok=True)

    def document_paths(self) -> list[Path]:
        pats = self.tenant.cfg.get("documents", [])
        inbox = self.tenant.state_dir / "inbox"   # emails and their attachments, saved by the comms agent
        out = sorted(f for f in inbox.glob("*") if f.suffix.lower() in INBOX_TYPES) if inbox.exists() else []
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(self.root))
                if any(fnmatch.fnmatch(rel, pat) for pat in pats):
                    out.append(p)
        return out

    def cached(self, path: Path) -> dict | None:
        f = self.cache / f"{sha256(path)}.json"
        return json.loads(f.read_text()) if f.exists() else None

    def extract(self, path: Path) -> dict:
        hit = self.cached(path)
        if hit:
            return hit
        facts = llm.structured(system=SYSTEM, content=_content_for(path), schema=EXTRACTION_SCHEMA,
                               effort="low", max_tokens=12000)
        facts["_source"] = (str(path.relative_to(self.root)) if self.root in path.parents
                            else f"inbox/{path.name}")
        facts["_sha256"] = sha256(path)
        (self.cache / f"{facts['_sha256']}.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
        return facts

    def extract_all(self, workers: int = 8, only_missing: bool = True) -> tuple[list[dict], list[str]]:
        paths = self.document_paths()
        results, errors = [], []
        todo = []
        for p in paths:
            hit = self.cached(p)
            if hit:
                results.append(hit)
            elif only_missing:
                todo.append(p)
        if todo and llm.available():
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self.extract, p): p for p in todo}
                for fut in as_completed(futures):
                    try:
                        results.append(fut.result())
                    except Exception as e:  # keep going; report per file
                        errors.append(f"{futures[fut].name}: {e}")
        elif todo:
            errors.append(f"{len(todo)} documents not read: no ANTHROPIC_API_KEY")
        return results, errors
