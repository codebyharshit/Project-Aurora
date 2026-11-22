"""Watcher: pull the customer's file source and report what changed (by SHA-256)."""
from __future__ import annotations

import io
import json
import os
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from aurora.config import DATA_DIR, ROOT, Tenant


@dataclass
class Drop:
    pulled_at: str
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.removed)


class PortalWatcher:
    def __init__(self, tenant: Tenant):
        self.tenant = tenant
        src = tenant.cfg["source"]
        self.base = src["base_url"].rstrip("/")
        self.token = os.environ.get(src["token_env"], "")
        self.snapshots = DATA_DIR / "snapshots"
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.local = ROOT / src["local_dir"]

    def _get(self, path: str) -> bytes:
        req = urllib.request.Request(self.base + path, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    def last_listing(self) -> dict[str, str]:
        files = sorted(self.snapshots.glob("files_*.json"))
        if not files:
            return {}
        return {f["path"]: f["sha256"] for f in json.loads(files[-1].read_text())["files"]}

    def poll(self) -> Drop:
        """Fetch the file list; if anything changed, download and unpack the archive."""
        before = self.last_listing()
        listing = json.loads(self._get("/api/v1/files"))
        after = {f["path"]: f["sha256"] for f in listing["files"]}
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        drop = Drop(
            pulled_at=stamp,
            added=sorted(p for p in after if p not in before),
            changed=sorted(p for p in after if p in before and before[p] != after[p]),
            removed=sorted(p for p in before if p not in after),
        )
        if drop.empty and self.local.exists():
            return drop
        archive = self._get("/api/v1/archive.zip")
        (self.snapshots / f"files_{stamp}.json").write_text(json.dumps(listing))
        (self.snapshots / f"archive_{stamp}.zip").write_bytes(archive)
        tmp = self.local.parent / f".unpack_{stamp}"
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            z.extractall(tmp)
        inner = next(tmp.iterdir()) if len(list(tmp.iterdir())) == 1 else tmp
        if self.local.exists():
            shutil.rmtree(self.local)
        shutil.move(str(inner), str(self.local))
        shutil.rmtree(tmp, ignore_errors=True)
        return drop
