"""Pipeline that turns the Soony data drop into a linked, queryable SQLite dataset.

Modules:
    registry    – file inventory with sha256 hashes (drives incremental re-reads)
    structured  – CSV/XLSX loaders with explicit typing and normalisation
    documents   – PDF/image document extraction (template parsers + manual extractions)
    linking     – SQL views joining POs, receipts, delivery notes, stock, shipments, suppliers
    findings    – generic, evidence-backed contradiction checks
    report      – REPORT.md writer
"""

from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
