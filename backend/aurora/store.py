"""SQLite store for signals, cases, actions, messages, timers and playbook stats."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from aurora.config import Tenant

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, title TEXT, status TEXT, playbook_id TEXT,
  signal_type TEXT, data TEXT, rank_score REAL, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, at TEXT, actor TEXT, text TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, kind TEXT, tier TEXT, status TEXT,
  payload TEXT, result TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, direction TEXT, counterpart TEXT,
  subject TEXT, body TEXT, body_en TEXT, message_id TEXT, at TEXT, parsed TEXT);
CREATE TABLE IF NOT EXISTS timers (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, kind TEXT, due_at TEXT, done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS playbook_stats (
  playbook_id TEXT PRIMARY KEY, approvals INTEGER DEFAULT 0, approvals_without_edit INTEGER DEFAULT 0,
  auto_enabled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, reason TEXT, report TEXT);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class _Rows:
    """Query result fetched while the lock was held, so it is safe to read after release."""

    def __init__(self, cur: sqlite3.Cursor):
        self._rows = cur.fetchall()
        self.lastrowid = cur.lastrowid
        self.rowcount = cur.rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _LockedDB:
    """One sqlite connection shared by API threads and the agent loop: every call takes the same lock."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn, self._lock = conn, lock

    def execute(self, sql: str, args: tuple = ()) -> _Rows:
        with self._lock:
            return _Rows(self._conn.execute(sql, args))

    def executescript(self, sql: str) -> None:
        with self._lock:
            self._conn.executescript(sql)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()


class Store:
    def __init__(self, tenant: Tenant, path: Path | None = None):
        self.path = path or tenant.state_dir / "aurora.sqlite"
        self._lock = threading.RLock()
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self.db = _LockedDB(conn, self._lock)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> _Rows:
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # ---- cases -----------------------------------------------------------------
    def next_case_id(self) -> str:
        n = self.db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] + 1
        return f"C-{n:04d}"

    def upsert_case(self, fingerprint: str, title: str, status: str, playbook_id: str | None,
                    signal_type: str, data: dict, rank_score: float) -> tuple[str, bool]:
        """Insert a new case or refresh an existing one. Returns (id, created)."""
        row = self.db.execute("SELECT id, status, data FROM cases WHERE fingerprint=?", (fingerprint,)).fetchone()
        if row:
            old = json.loads(row["data"] or "{}")
            for k in ("mandate", "negotiation", "tracking", "investigation", "explanation_locked"):   # human/agent state survives re-analysis
                if k in old:
                    data[k] = old[k]
            if row["status"] not in ("DETECTED", "AWAITING_APPROVAL", "AWAITING_HUMAN_REVIEW", "INVESTIGATING"):
                data["recommended_option"] = old.get("recommended_option", data.get("recommended_option"))
            # never overwrite a human decision or an action in flight
            keep = row["status"] not in ("DETECTED", "AWAITING_APPROVAL", "AWAITING_HUMAN_REVIEW", "INVESTIGATING",
                                         "READY_TO_ASK", "SUPERSEDED")   # a problem that reappears reopens its case
            self._exec("UPDATE cases SET title=?, data=?, rank_score=?, playbook_id=?, updated_at=?"
                       + ("" if keep else ", status=?") + " WHERE id=?",
                       (title, json.dumps(data, default=str), rank_score, playbook_id, _now())
                       + (() if keep else (status,)) + (row["id"],))
            return row["id"], False
        cid = self.next_case_id()
        self._exec("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (cid, fingerprint, title, status, playbook_id, signal_type,
                    json.dumps(data, default=str), rank_score, _now(), _now()))
        return cid, True

    def case(self, cid: str) -> dict | None:
        row = self.db.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
        return self._case_dict(row) if row else None

    def cases(self, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM cases", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        return [self._case_dict(r) for r in self.db.execute(q + " ORDER BY rank_score DESC", args)]

    def _case_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["data"] = json.loads(d["data"] or "{}")
        return d

    def set_status(self, cid: str, status: str, actor: str, note: str) -> None:
        self._exec("UPDATE cases SET status=?, updated_at=? WHERE id=?", (status, _now(), cid))
        self.event(cid, actor, f"{status}: {note}")

    def update_data(self, cid: str, **fields: Any) -> None:
        case = self.case(cid)
        case["data"].update(fields)
        self._exec("UPDATE cases SET data=?, updated_at=? WHERE id=?",
                   (json.dumps(case["data"], default=str), _now(), cid))

    # ---- timeline, actions, messages, timers -------------------------------------
    def event(self, cid: str, actor: str, text: str, data: dict | None = None) -> None:
        self._exec("INSERT INTO events (case_id, at, actor, text, data) VALUES (?,?,?,?,?)",
                   (cid, _now(), actor, text, json.dumps(data or {}, default=str)))

    def events(self, cid: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM events WHERE case_id=? ORDER BY id", (cid,))]

    def add_action(self, cid: str, kind: str, tier: str, status: str, payload: dict) -> int:
        cur = self._exec("INSERT INTO actions (case_id, kind, tier, status, payload, result, created_at, updated_at)"
                         " VALUES (?,?,?,?,?,?,?,?)",
                         (cid, kind, tier, status, json.dumps(payload, default=str), "{}", _now(), _now()))
        return cur.lastrowid

    def actions(self, cid: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM actions WHERE case_id=? ORDER BY id", (cid,))]

    def add_message(self, cid: str, direction: str, counterpart: str, subject: str, body: str,
                    body_en: str = "", message_id: str = "", parsed: dict | None = None) -> None:
        self._exec("INSERT INTO messages (case_id, direction, counterpart, subject, body, body_en, message_id, at, parsed)"
                   " VALUES (?,?,?,?,?,?,?,?,?)",
                   (cid, direction, counterpart, subject, body, body_en, message_id, _now(), json.dumps(parsed or {})))

    def messages(self, cid: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM messages WHERE case_id=? ORDER BY id", (cid,))]

    def add_timer(self, cid: str, kind: str, due_at: str) -> None:
        self._exec("INSERT INTO timers (case_id, kind, due_at) VALUES (?,?,?)", (cid, kind, due_at))

    def due_timers(self, now: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM timers WHERE done=0 AND due_at<=?", (now,))]

    def finish_timer(self, tid: int) -> None:
        self._exec("UPDATE timers SET done=1 WHERE id=?", (tid,))

    # ---- earned autonomy ---------------------------------------------------------
    def record_approval(self, playbook_id: str, edited: bool) -> dict:
        self._exec("INSERT OR IGNORE INTO playbook_stats (playbook_id) VALUES (?)", (playbook_id,))
        self._exec("UPDATE playbook_stats SET approvals=approvals+1"
                   + ("" if edited else ", approvals_without_edit=approvals_without_edit+1")
                   + " WHERE playbook_id=?", (playbook_id,))
        return self.playbook_stats(playbook_id)

    def playbook_stats(self, playbook_id: str) -> dict:
        row = self.db.execute("SELECT * FROM playbook_stats WHERE playbook_id=?", (playbook_id,)).fetchone()
        return dict(row) if row else {"playbook_id": playbook_id, "approvals": 0,
                                      "approvals_without_edit": 0, "auto_enabled": 0}

    def set_auto(self, playbook_id: str, on: bool) -> None:
        self._exec("INSERT OR IGNORE INTO playbook_stats (playbook_id) VALUES (?)", (playbook_id,))
        self._exec("UPDATE playbook_stats SET auto_enabled=? WHERE playbook_id=?", (int(on), playbook_id))

    # ---- runs + kv -----------------------------------------------------------------
    def log_run(self, started: str, reason: str, report: dict) -> None:
        self._exec("INSERT INTO runs (started, finished, reason, report) VALUES (?,?,?,?)",
                   (started, _now(), reason, json.dumps(report, default=str)))

    def last_run(self) -> dict | None:
        row = self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return {**dict(row), "report": json.loads(row["report"])} if row else None

    def put(self, k: str, v: Any) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, json.dumps(v, default=str)))

    def get(self, k: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(row["v"]) if row else default


    # ---- demo ---------------------------------------------------------------------
    def reset_decisions(self) -> dict:
        """Put every case back to 'not decided yet' (for a fresh demo). Keeps the analysis,
        investigations and the inbox position (old emails are not processed again)."""
        undone = []
        for c in self.cases():
            d = c["data"]
            for k in ("mandate", "negotiation", "tracking"):
                d.pop(k, None)
            if c["status"] in ("AWAITING_SUPPLIER", "AGREED", "IN_TRANSIT", "DELIVERED", "VERIFIED", "EXECUTING",
                               "ESCALATED", "DECIDED"):
                status = ("AWAITING_HUMAN_REVIEW" if not c["playbook_id"] or d.get("tier") in ("review", "never")
                          else "READY_TO_ASK" if d.get("tier") in ("ask", "observe") else "AWAITING_APPROVAL")
                undone.append(c["id"])
            else:
                status = c["status"]
            self._exec("UPDATE cases SET status=?, data=? WHERE id=?", (status, json.dumps(d, default=str), c["id"]))
        self._exec("DELETE FROM events WHERE actor IN ('human','comms','negotiator','tracker','agent','timer')")
        self._exec("DELETE FROM messages")
        self._exec("DELETE FROM actions")
        self._exec("DELETE FROM timers")
        self._exec("DELETE FROM playbook_stats")
        self.put("committed_actions", [])
        return {"reset": undone}
