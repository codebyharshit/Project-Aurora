"""Paths, environment and tenant configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STATE_DIR = DATA_DIR / "state"
TENANTS_DIR = ROOT / "tenants"


def load_env(path: Path = ROOT / ".env") -> None:
    """Load KEY=VALUE lines from .env without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env()


@dataclass(frozen=True)
class Tenant:
    name: str
    cfg: dict

    @property
    def data_root(self) -> Path:
        """Directory holding the tenant's current unpacked source files."""
        return ROOT / self.cfg["source"]["local_dir"]

    @property
    def deadline(self) -> datetime:
        return datetime.fromisoformat(self.cfg["deadline"]["at"])

    @property
    def state_dir(self) -> Path:
        d = STATE_DIR / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def threshold(self, key: str, default: float) -> float:
        return float(self.cfg.get("thresholds", {}).get(key, default))


@lru_cache
def get_tenant(name: str | None = None) -> Tenant:
    name = name or os.environ.get("AURORA_TENANT", "soony")
    cfg = yaml.safe_load((TENANTS_DIR / name / "tenant.yaml").read_text())
    return Tenant(name=name, cfg=cfg)
