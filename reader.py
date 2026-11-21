"""
Document reader for the Soony launch-control project.

Walks the data folder, turns every document into structured JSON and writes
one line per document to documents.jsonl.

  - text PDFs / xlsx / csv  -> read locally (no AI needed), then optionally
                               sent to the LLM to extract structured fields
  - scans (jpg/png/PDFs without text) -> sent to Claude vision

Usage:
  export ANTHROPIC_API_KEY=...
  python reader.py /path/to/soony-data --out documents.jsonl
  python reader.py /path/to/soony-data --no-llm        # only read locally
"""
import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path

import openpyxl
import pdfplumber

MODEL = "claude-sonnet-5-5"
IMAGE_EXT = {".jpg", ".jpeg", ".png"}

# What we want back for every document. Keep it generic: the reader should
# find mismatches itself, not have them hardcoded.
EXTRACT_PROMPT = """You read business documents for a procurement team (games publisher, Hamburg warehouse).
The document may be in English, German, Polish, Korean or Chinese.

Return ONLY a JSON object with these keys:
{
  "doc_type": "delivery_note | order_confirmation | inspection_report | contract | supplier_notice | price_list | shipping_advice | other",
  "language": "ISO code",
  "document_number": string or null,
  "date": "YYYY-MM-DD" or null,
  "supplier": string or null,
  "po_number": string or null,
  "items": [{"part": "CMP-...", "description": string, "quantity": number or null,
             "quantity_printed": number or null, "quantity_handwritten": number or null}],
  "handwritten_corrections": [string],   // anything crossed out or written by hand, with what changed
  "stamps_and_signatures": [string],     // e.g. "RECEIVED 18.11.2026", "signed Meyer K."
  "deadlines_and_dates": [string],       // any dates/times that matter, quoted with meaning
  "problems_or_risks": [string],         // defects, delays, downtime, price changes, conditions
  "offers": [string],                    // any offer: what, quantity, price, how fast, validity
  "summary_en": "2 sentences in English"
}
Rules: copy numbers exactly. If a quantity is crossed out and replaced by hand, put the printed
value in quantity_printed, the handwritten value in quantity_handwritten, and the handwritten
value in quantity (the corrected one is what physically arrived). Do not guess; use null."""


def read_pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages).strip()


def read_xlsx(path: Path) -> str:
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for ws in wb:
        out.append(f"## sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            if any(c is not None for c in row):
                out.append(" | ".join("" if c is None else str(c) for c in row))
    return "\n".join(out)


def pdf_first_page_as_png(path: Path) -> bytes:
    with pdfplumber.open(path) as pdf:
        img = pdf.pages[0].to_image(resolution=150).original
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def llm_extract(client, text: str | None = None, image: bytes | None = None, media_type="image/png") -> dict:
    content = []
    if image is not None:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media_type,
            "data": base64.b64encode(image).decode()}})
    if text:
        content.append({"type": "text", "text": "Document text:\n" + text[:20000]})
    content.append({"type": "text", "text": EXTRACT_PROMPT})
    resp = client.messages.create(model=MODEL, max_tokens=2000,
                                  messages=[{"role": "user", "content": content}])
    raw = resp.content[0].text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"parse_error": True, "raw": raw}


def process(path: Path, client) -> dict:
    ext = path.suffix.lower()
    rec = {"path": str(path), "file": path.name, "kind": None, "text": None, "extracted": None}
    try:
        if ext in IMAGE_EXT:
            rec["kind"] = "scan_image"
            data = path.read_bytes()
            mt = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            if client:
                rec["extracted"] = llm_extract(client, image=data, media_type=mt)
        elif ext == ".pdf":
            text = read_pdf_text(path)
            if len(text) > 200:
                rec["kind"], rec["text"] = "pdf_text", text
                if client:
                    rec["extracted"] = llm_extract(client, text=text)
            else:  # tiny/empty text -> treat as scan
                rec["kind"] = "pdf_scan"
                rec["text"] = text or None
                if client:
                    rec["extracted"] = llm_extract(client, text=text or None,
                                                   image=pdf_first_page_as_png(path))
        elif ext in {".xlsx", ".xlsm"}:
            rec["kind"], rec["text"] = "spreadsheet", read_xlsx(path)
        elif ext in {".csv", ".md", ".txt"}:
            rec["kind"], rec["text"] = "table_or_text", path.read_text(errors="replace")[:20000]
        else:
            rec["kind"] = "skipped"
    except Exception as e:  # keep going, one bad file must not stop the run
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path, default=Path("documents.jsonl"))
    ap.add_argument("--no-llm", action="store_true", help="read locally only")
    ap.add_argument("--only", default="", help="only paths containing this text")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    client = None
    if not args.no_llm:
        try:
            import anthropic
            client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY
        except Exception as e:
            sys.exit(f"LLM client not available ({e}). Install `anthropic`, set ANTHROPIC_API_KEY, or use --no-llm.")

    files = sorted(p for p in args.root.rglob("*") if p.is_file() and not p.name.startswith("."))
    if args.only:
        files = [p for p in files if args.only in str(p)]
    if args.limit:
        files = files[: args.limit]

    with args.out.open("w") as f:
        for i, p in enumerate(files, 1):
            rec = process(p, client)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(files)}] {rec['kind']:<13} {p.name}", flush=True)
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
