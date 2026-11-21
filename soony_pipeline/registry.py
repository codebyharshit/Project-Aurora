"""File inventory: every file in the data drop with its sha256, used for incremental processing."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

IGNORED_NAMES = {".DS_Store"}
STRUCTURED_EXT = {".csv", ".xlsx"}
DOCUMENT_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
TEXT_EXT = {".md"}


@dataclass(frozen=True)
class FileEntry:
    """One file of the data drop."""

    rel_path: str
    sha256: str
    size: int
    mtime_utc: str
    kind: str  # structured | document | text | other


def sha256_of(path: Path) -> str:
    """Return the hex sha256 of a file, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(path: Path) -> str:
    """Map a file extension to a processing kind."""
    ext = path.suffix.lower()
    if ext in STRUCTURED_EXT:
        return "structured"
    if ext in DOCUMENT_EXT:
        return "document"
    if ext in TEXT_EXT:
        return "text"
    return "other"


def scan(root: Path) -> list[FileEntry]:
    """Walk the data root and hash every relevant file (sorted for determinism)."""
    entries: list[FileEntry] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name in IGNORED_NAMES:
            continue
        stat = path.stat()
        entries.append(
            FileEntry(
                rel_path=path.relative_to(root).as_posix(),
                sha256=sha256_of(path),
                size=stat.st_size,
                mtime_utc=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                kind=classify(path),
            )
        )
    return entries


def previous_hashes(con: sqlite3.Connection) -> dict[str, str]:
    """Return {rel_path: sha256} from the last run (empty on first run)."""
    try:
        return dict(con.execute("SELECT rel_path, sha256 FROM files").fetchall())
    except sqlite3.OperationalError:
        return {}


def write_files_table(con: sqlite3.Connection, entries: list[FileEntry], before: dict[str, str]) -> dict[str, int]:
    """Persist the inventory with a change status per file and return counts per status."""
    con.execute("DROP TABLE IF EXISTS files")
    con.execute(
        """CREATE TABLE files (rel_path TEXT PRIMARY KEY, sha256 TEXT, size INTEGER,
           mtime_utc TEXT, kind TEXT, change_status TEXT)"""
    )
    counts: dict[str, int] = {}
    for e in entries:
        status = "new" if e.rel_path not in before else ("unchanged" if before[e.rel_path] == e.sha256 else "changed")
        counts[status] = counts.get(status, 0) + 1
        con.execute("INSERT INTO files VALUES (?,?,?,?,?,?)", (e.rel_path, e.sha256, e.size, e.mtime_utc, e.kind, status))
    removed = set(before) - {e.rel_path for e in entries}
    counts["removed"] = len(removed)
    return counts
