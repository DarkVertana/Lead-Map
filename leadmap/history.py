"""
A line per finished search, so the tool can tell you what you've already run.

Kept beside the usage ledger (~/.local/state/leadmap/sessions.jsonl) as JSON
lines: append-only, trivially greppable, and harmless to delete. It records what
was searched and what came back — never the API key.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional

from .paths import state_dir

KEEP = 500          # lines; older ones are dropped when the file is rewritten


def history_path() -> Path:
    return state_dir() / "sessions.jsonl"


def record(**entry: Any) -> None:
    """Append one finished search. Never raises — a lost line isn't worth a crash."""
    entry.setdefault("at", dt.datetime.now().isoformat(timespec="seconds"))
    try:
        path = history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent(limit: int = 10) -> list[dict]:
    """The last `limit` searches, newest first."""
    try:
        lines = history_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in reversed(lines[-KEEP:]):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out


def when(entry: dict) -> str:
    """'24 Aug 2026 00:42' from the stored timestamp."""
    stamp: Optional[str] = entry.get("at")
    try:
        return dt.datetime.fromisoformat(stamp).strftime("%d %b %Y %H:%M")
    except (TypeError, ValueError):
        return stamp or "—"


def describe(entry: dict) -> str:
    """'barber · Nashik' — what was actually searched for."""
    parts = [entry.get("name") or "", entry.get("category") or ""]
    looking = " ".join(p for p in parts if p) or "anything"
    return f"{looking} · {entry.get('location') or '—'}"
