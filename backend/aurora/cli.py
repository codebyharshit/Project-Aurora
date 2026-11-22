"""Command line entry points: python -m aurora.cli <command>."""
from __future__ import annotations

import json
import sys

from aurora.agents import llm
from aurora.config import get_tenant


def models() -> None:
    """List models the configured provider key can use (OpenAI)."""
    client = llm._client()
    names = sorted(m.id for m in client.models.list())
    print("\n".join(names))


def read(path: str) -> None:
    """Run the Document Reader on one file and print the facts."""
    from pathlib import Path
    from aurora.ingest.documents import DocumentReader
    reader = DocumentReader(get_tenant())
    p = Path(path)
    if not p.is_absolute():
        p = reader.root / path
    print(json.dumps(reader.extract(p), indent=1, ensure_ascii=False))


def pull() -> None:
    from aurora.ingest.watcher import PortalWatcher
    print(PortalWatcher(get_tenant()).poll())


def extract_all() -> None:
    from aurora.ingest.documents import DocumentReader
    docs, errors = DocumentReader(get_tenant()).extract_all()
    print(f"{len(docs)} documents read, {len(errors)} errors")
    for e in errors[:20]:
        print("  ", e)


def plan(*actions: str) -> None:
    from aurora.planner import LaunchPlanner
    from aurora.world import World
    result = LaunchPlanner(World.load(read_documents=False)).run(actions=list(actions))
    print(json.dumps(result, indent=1, default=str))


COMMANDS = {"models": models, "read": read, "pull": pull, "extract-all": extract_all, "plan": plan}

if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["plan"]
    COMMANDS[cmd](*args)
