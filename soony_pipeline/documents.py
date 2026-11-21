"""Document extraction: PDFs and scanned images -> one normalised record per document.

Extractors, in order of preference:
    1. manual   – a human/LLM reading stored in build/extractions/*.jsonl, pinned to the file's sha256.
                  If the file changed since it was read, the record is kept but marked stale/low confidence.
    2. template – deterministic regex parsers for supplier order confirmations and shipping advices
                  (text-layer PDFs following a fixed layout).
    3. fallback – raw text only (PDF with text layer) or nothing (image) -> confidence 'low',
                  status 'needs_review'. Nothing is guessed.

Results are cached per sha256 in table `extraction_cache`, so unchanged files are never re-read.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pdfplumber

EXTRACTOR_VERSION = "2026-11-21.1"  # bump to force re-extraction of template-parsed documents
NUM = r"[\d][\d,.\s]*"


# ---------------------------------------------------------------- helpers

def to_int(text: str | None) -> int | None:
    """Parse '13,000' / '13.000' / '13 000' as 13000 (all quantities in this drop are integers)."""
    if text is None:
        return None
    digits = re.sub(r"[^\d-]", "", str(text))
    return int(digits) if digits not in ("", "-") else None


def detect_language(text: str) -> str:
    """Cheap script/keyword based language tag for the document's non-English part."""
    if re.search(r"[가-힯]", text):
        return "ko"
    if re.search(r"[一-鿿]", text):
        return "zh"
    if re.search(r"\b(Potwierdzenie|Zamówienie|Dokument WZ|zawiadomienie|Oferta)\b", text, re.I):
        return "pl"
    return "en"


def pdf_text(path: Path) -> str:
    """Concatenated text layer of a PDF ('' for scanned PDFs)."""
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def empty_record(rel_path: str) -> dict[str, Any]:
    """Skeleton with every field the downstream tables expect."""
    return {"file": rel_path, "doc_type": None, "language": None, "doc_no": None, "doc_date": None,
            "supplier_id": rel_path.split("/")[1].split("_")[0] if rel_path.startswith("suppliers/") else None,
            "po_numbers": [], "gr_number": None, "lines": [], "stamps": [], "signatures": [],
            "handwritten_corrections": None, "issues": [], "offers": [], "deadlines": [], "clauses": [],
            "prices": [], "xref": {}, "summary": None, "confidence": "low", "notes": "", "status": "ok"}


# ---------------------------------------------------------------- template parsers

def parse_order_confirmation(text: str, rel_path: str, xref: dict[str, str]) -> dict[str, Any] | None:
    """Parse a supplier order confirmation / acknowledgement (text-layer PDF)."""
    flat = re.sub(r"\s+", " ", text)
    head = re.search(r"Order (?:Confirmation|Acknowledgement) (OA\d+)", flat)
    order = re.search(r"Your order (\d{10}) of (\d{4}-\d{2}-\d{2}) · Incoterms (.+?) · Payment (\S+)", flat)
    if not (head and order):
        return None
    rec = empty_record(rel_path)
    rec.update(doc_type="order_confirmation", language=detect_language(text), doc_no=head.group(1),
               doc_date=None, po_numbers=[order.group(1)], extractor="template:order_confirmation")
    rec["header"] = {"po_date": order.group(2), "incoterm": order.group(3).strip(), "payment": order.group(4)}
    line_re = re.compile(r"^(\d{5}) (\S+) .*?(\d[\d,]*) (\d+(?:\.\d+)?) ([A-Z]{3}) (\d{4}-\d{2}-\d{2})$")
    free: list[str] = []
    for raw in text.splitlines()[2:]:
        m = line_re.match(raw.strip())
        if m:
            part_raw = m.group(2)
            rec["lines"].append({
                "po_number": order.group(1), "po_line": int(m.group(1)) // 10, "part_raw": part_raw,
                "part_id": part_raw if part_raw.startswith("CMP-") else xref.get(part_raw),
                "qty_printed": to_int(m.group(3)), "unit_price": float(m.group(4)), "currency": m.group(5),
                "confirmed_date": m.group(6)})
        elif len(raw) > 40 and not raw.startswith(("Customer:", "Item Material")):
            free.append(raw.strip())
    note = " ".join(free)
    rec["free_text"] = note
    _issues_from_oc_note(rec, note, xref)
    unparsed = any(l["part_id"] is None for l in rec["lines"])
    rec["confidence"] = "high" if rec["lines"] and not unparsed else "medium"
    rec["notes"] = "unmapped supplier part number" if unparsed else ""
    rec["summary"] = (f"Order confirmation {rec['doc_no']} for PO {order.group(1)}: "
                      f"{len(rec['lines'])} line(s), incoterm {rec['header']['incoterm']}."
                      + (f" Note: {note[:200]}" if note else ""))
    return rec


def _issues_from_oc_note(rec: dict[str, Any], note: str, xref: dict[str, str]) -> None:
    """Turn the free-text remarks of an order confirmation into typed issues / line attributes."""
    if not note:
        return
    for m in re.finditer(r"(CMP-[A-Z]+-\d+|PR-[A-Z]+-\d+)[^.]*?rev\. ([A-Z])", note):
        part = m.group(1) if m.group(1).startswith("CMP-") else xref.get(m.group(1))
        for line in rec["lines"]:
            if line["part_id"] == part:
                line["artwork_rev"] = m.group(2)
        rec["issues"].append({"type": "artwork_revision", "part_id": part, "value": m.group(2), "text": m.group(0)})
    if re.search(r"on hold", note, re.I):
        rec["issues"].append({"type": "shipment_on_hold", "text": note})
    if re.search(r"DDP is not agreed|do not accept this term", note, re.I):
        rec["issues"].append({"type": "incoterm_dispute", "value": "EXW", "text": note})
    claim = re.search(r"Supplier status: ([^.(]+)", note)
    if claim:
        rec["issues"].append({"type": "supplier_status_claim", "value": claim.group(1).strip(), "text": note})
    incl = re.search(r"magnets (\S+) \((\d+) pcs per box\).*included in the unit price", note)
    if incl:
        rec["issues"].append({"type": "bom_inclusion", "part_id": xref.get(incl.group(1), incl.group(1)),
                              "value": int(incl.group(2)), "text": incl.group(0)})
    dispatch = re.search(r"Dispatch (\d{4}-\d{2}-\d{2})", note)
    if dispatch:
        rec["deadlines"].append({"what": "supplier dispatch date", "due": dispatch.group(1), "text": note})


def parse_shipping_advice(text: str, rel_path: str, xref: dict[str, str]) -> dict[str, Any] | None:
    """Parse a (short-)shipment advice: ordered / shipped / balance plus the balance's new date."""
    if "Shipping advice" not in text:
        return None
    rec = empty_record(rel_path)
    po = re.search(r"Your order (\d{10}) · (\d{4}-\d{2}-\d{2})", text)
    awb = re.search(r"AWB ([\d-]+)", text)
    rec.update(doc_type="shipping_advice", language=detect_language(text), doc_no=awb.group(1) if awb else None,
               doc_date=po.group(2) if po else None, po_numbers=[po.group(1)] if po else [],
               extractor="template:shipping_advice")
    m = re.search(r"(CMP-[A-Z]+-\d+) .*?(\d[\d,]*) (\d[\d,]*) (\d[\d,]*)\s*$", text, re.M)
    if m:
        rec["lines"].append({"po_number": rec["po_numbers"][0] if rec["po_numbers"] else None, "part_raw": m.group(1),
                             "part_id": m.group(1), "qty_ordered": to_int(m.group(2)), "qty_printed": to_int(m.group(3)),
                             "qty_balance": to_int(m.group(4))})
    eta = re.search(r"delivery to Hamburg (\d{4}-\d{2}-\d{2})", text)
    reason = re.search(r"\n([^\n]*offloaded[^\n]*)", text)
    if m and to_int(m.group(4)):
        rec["issues"].append({"type": "short_shipment", "part_id": m.group(1), "qty": to_int(m.group(4)),
                              "new_date": eta.group(1) if eta else None, "reference": rec["doc_no"],
                              "text": reason.group(1).strip() if reason else "short shipment"})
    if eta:
        rec["deadlines"].append({"what": "balance delivery to Hamburg", "due": eta.group(1)})
    rec["confidence"] = "high" if m else "low"
    rec["summary"] = (f"Short shipment for PO {rec['po_numbers'][0]}: {m.group(3)} of {m.group(2)} {m.group(1)} shipped "
                      f"on AWB {rec['doc_no']}, balance {m.group(4)} due in Hamburg {eta.group(1) if eta else '?'}."
                      if m else "Shipping advice (unparsed)")
    return rec


TEMPLATE_PARSERS = (parse_order_confirmation, parse_shipping_advice)


# ---------------------------------------------------------------- manual extractions

def load_manual(extraction_dir: Path) -> dict[str, dict[str, Any]]:
    """Read every *.jsonl in the extraction directory into {rel_path: record}."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(extraction_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["file"]] = rec
    return out


def normalise_manual(rec: dict[str, Any], current_sha: str) -> dict[str, Any]:
    """Map a manual extraction onto the standard record; mark it stale if the file changed since reading."""
    out = empty_record(rec["file"])
    out.update({k: v for k, v in rec.items() if k in out})
    out["extractor"] = "manual"
    pos = rec.get("po_number")
    out["po_numbers"] = [p for p in (pos.split("|") if pos else []) if p]
    if rec.get("gr_number"):
        out["gr_number"] = rec["gr_number"]
    if rec.get("received_by"):
        out["signatures"] = [f"received by {rec['received_by']}"]
    out["signatures"] += [s for s in rec.get("signatures", []) if s not in out["signatures"]]
    for line in out["lines"]:
        line.setdefault("part_raw", line.get("part"))
        line.setdefault("part_id", line.get("part_soony") or line.get("part"))
        if len(out["po_numbers"]) == 1:
            line.setdefault("po_number", out["po_numbers"][0])
    for clause in rec.get("clauses", []):
        out["clauses"].append(clause)
    for key in ("received_stamp", "gross_weight_kg", "carrier", "remarks", "decision", "rules", "roles",
                "valid_from", "valid_to", "container", "logistics"):
        if key in rec:
            out[key] = rec[key]
    pinned = rec.get("sha256")
    if pinned and pinned != current_sha:
        out.update(confidence="low", status="stale_manual_extraction",
                   notes=(out["notes"] + "; file changed after manual reading - re-read required").strip("; "))
    return out


# ---------------------------------------------------------------- orchestration

def ensure_cache(con: sqlite3.Connection) -> None:
    """Create the persistent extraction cache (survives re-runs)."""
    con.execute("""CREATE TABLE IF NOT EXISTS extraction_cache (sha256 TEXT, rel_path TEXT, extractor TEXT,
                   extractor_version TEXT, payload TEXT, PRIMARY KEY (sha256, rel_path))""")


def extract_one(root: Path, rel_path: str, sha: str, manual: dict[str, dict], xref: dict[str, str]) -> dict[str, Any]:
    """Extract a single document with the best available extractor."""
    if rel_path in manual:
        return normalise_manual(manual[rel_path], sha)
    path = root / rel_path
    if path.suffix.lower() == ".pdf":
        text = pdf_text(path)
        for parser in TEMPLATE_PARSERS:
            rec = parser(text, rel_path, xref) if text.strip() else None
            if rec:
                rec["raw_text"] = text
                return rec
        rec = empty_record(rel_path)
        rec.update(extractor="fallback:text" if text.strip() else "none", raw_text=text, status="needs_review",
                   language=detect_language(text) if text.strip() else None,
                   notes="no template parser matched; raw text stored, needs manual reading" if text.strip()
                   else "scanned PDF without text layer; needs manual reading")
        return rec
    rec = empty_record(rel_path)
    rec.update(extractor="none", status="needs_review", notes="image without manual extraction; needs manual reading")
    return rec


def extract_documents(con: sqlite3.Connection, root: Path, extraction_dir: Path,
                      xref: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Extract all documents, re-using cached results for unchanged (sha256, path) pairs."""
    ensure_cache(con)
    manual = load_manual(extraction_dir)
    manual_fingerprint = {k: json.dumps(v, sort_keys=True) for k, v in manual.items()}
    docs = con.execute("SELECT rel_path, sha256 FROM files WHERE kind='document'").fetchall()
    stats = {"cached": 0, "extracted": 0}
    records = []
    for rel_path, sha in docs:
        row = con.execute("SELECT extractor, extractor_version, payload FROM extraction_cache WHERE sha256=? AND rel_path=?",
                          (sha, rel_path)).fetchone()
        reusable = row and row[1] == EXTRACTOR_VERSION and (
            row[0] != "manual" or json.loads(row[2]).get("_manual_fp") == manual_fingerprint.get(rel_path)) and (
            row[0] == "manual" or rel_path not in manual)
        if reusable:
            rec = json.loads(row[2])
            stats["cached"] += 1
        else:
            rec = extract_one(root, rel_path, sha, manual, xref)
            rec["_manual_fp"] = manual_fingerprint.get(rel_path)
            con.execute("INSERT OR REPLACE INTO extraction_cache VALUES (?,?,?,?,?)",
                        (sha, rel_path, rec["extractor"], EXTRACTOR_VERSION, json.dumps(rec, ensure_ascii=False)))
            stats["extracted"] += 1
        rec["sha256"] = sha
        records.append(rec)
    con.commit()
    return records, stats


def contract_xref(extraction_dir: Path) -> dict[str, str]:
    """Supplier part-number cross reference taken from contract annexes (manual extractions)."""
    xref: dict[str, str] = {}
    for rec in load_manual(extraction_dir).values():
        xref.update(rec.get("xref", {}))
    return xref
