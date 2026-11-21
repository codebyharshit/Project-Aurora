#!/usr/bin/env python3
"""Build the Soony dataset: python build_dataset.py --data ~/Downloads/soony-data

Re-runnable and incremental: documents are only re-extracted when their sha256 changed
(cache in table `extraction_cache`). Structured CSV/XLSX are cheap and reloaded every run.

Outputs (all under build/, git-ignored):
    build/data/soony.db     SQLite dataset (tables, views, findings)
    build/REPORT.md         what was loaded, coverage, uncertain documents, top findings
Manual document readings live in build/extractions/*.jsonl (one JSON object per document).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from soony_pipeline import TZ, documents, findings, linking, registry, report, structured

REPO = Path(__file__).resolve().parent
DEFAULT_DB = REPO / "build/data/soony.db"
DEFAULT_EXTRACTIONS = REPO / "build/extractions"


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Command line interface."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, type=Path, help="root of the data drop (contains soony/ and suppliers/)")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--extractions", type=Path, default=DEFAULT_EXTRACTIONS)
    p.add_argument("--report", type=Path, default=REPO / "build/REPORT.md")
    p.add_argument("--asof", type=date.fromisoformat, default=datetime.now(TZ).date(),
                   help="analysis date (default: today in Europe/Berlin)")
    p.add_argument("--deadline", default="2026-11-22T20:00:00+01:00", help="trucks leave DC-HAM (ISO with offset)")
    p.add_argument("--pin-manual", action="store_true",
                   help="write the current sha256 into manual extraction records that have none yet")
    return p.parse_args(argv)


def pin_manual_hashes(data: Path, extraction_dir: Path) -> int:
    """Add sha256 to manual extraction records that lack it (binds a reading to the exact file version)."""
    pinned = 0
    for path in sorted(extraction_dir.glob("*.jsonl")):
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if "sha256" not in rec and (data / rec["file"]).exists():
                rec["sha256"] = registry.sha256_of(data / rec["file"])
                pinned += 1
            out.append(json.dumps(rec, ensure_ascii=False))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return pinned


def main(argv: list[str]) -> int:
    """Run all pipeline stages."""
    args = parse_args(argv)
    data = args.data.expanduser().resolve()
    if not (data / "soony").is_dir() or not (data / "suppliers").is_dir():
        print(f"error: {data} does not look like the data drop (missing soony/ or suppliers/)", file=sys.stderr)
        return 2
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.pin_manual:
        print(f"pinned sha256 on {pin_manual_hashes(data, args.extractions)} manual records")

    con = sqlite3.connect(args.db)
    before = registry.previous_hashes(con)
    entries = registry.scan(data)
    changes = registry.write_files_table(con, entries, before)
    print(f"[1/5] inventory: {len(entries)} files {changes}")

    xref = documents.contract_xref(args.extractions)
    linking.write_xref(con, xref)
    row_counts = structured.load_all(data, con, xref)
    print(f"[2/5] structured: {sum(row_counts.values())} rows in {len(row_counts)} tables")

    records, doc_stats = documents.extract_documents(con, data, args.extractions, xref)
    doc_counts = linking.write_document_tables(con, records)
    print(f"[3/5] documents: {len(records)} ({doc_stats})")

    views = linking.create_views(con)
    print(f"[4/5] views: {', '.join(views)}")

    deadline = datetime.fromisoformat(args.deadline)
    found = findings.run_all(con, asof=args.asof, deadline=deadline)
    print(f"[5/5] findings: {len(found)}")

    report.write(con, args.report, data=data, asof=args.asof, deadline=deadline, changes=changes,
                 row_counts=row_counts, doc_counts=doc_counts, doc_stats=doc_stats)
    con.commit()
    con.close()
    print(f"done -> {args.db} , {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
