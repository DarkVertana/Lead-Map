"""
Every business this machine has already handed over, so no two runs repeat one.

A client who runs the same search on Monday and again on Friday wants Friday's
file to hold what Monday's didn't. The place id is Google's own stable handle
for a business, so remembering the ids that have been written into a file is
enough: anything already delivered is dropped from every later search, whatever
the query was that found it again.

    ~/.local/state/businesslead/delivered.db      (BUSINESSLEAD_DELIVERED_FILE overrides)

This one is expected to be alive in five years, holding hundreds of thousands of
ids, so it is a SQLite table rather than a JSON file: a membership check is an
index lookup, a new id is one INSERT, and nothing rewrites the whole record on
every run. SQLite is in the standard library and its file format is famously
long-lived. An older delivered.json is imported the first time it is seen.

Ids are only recorded once a file has actually been written — a run that dies
before that leaves nothing behind and can be repeated. `--include-seen` searches
without the filter, and `--forget-seen` empties the record.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .paths import env, set_aside, state_dir

SCHEMA = 1


def default_path() -> Path:
    override = env("DELIVERED_FILE")
    if override:
        return Path(override).expanduser()
    return state_dir() / "delivered.db"


class Delivered:
    """The set of place ids already written into a results file.

    Never raises on a broken or unwritable store: a search that can't remember
    what it delivered is worth more than a search that refuses to run.
    """

    def __init__(self, path: Optional[Path] = None, *, today: Optional[dt.date] = None):
        self.path = Path(path) if path else default_path()
        self.today = today or dt.date.today()
        self.pending: dict[str, str] = {}      # staged by add(), written by save()
        self.db = self._open()
        if self.db is not None:
            self._import_json()

    # -- storage -------------------------------------------------------------
    def _open(self, retry: bool = True) -> Optional[sqlite3.Connection]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            # The rollback journal, not WAL: one small batch is written per run,
            # durability matters more than concurrency, and a finished run leaves
            # one file behind rather than three.
            db.execute("CREATE TABLE IF NOT EXISTS delivered ("
                       "place_id TEXT PRIMARY KEY, day TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS delivered_by_day ON delivered(day)")
            if not db.execute("PRAGMA user_version").fetchone()[0]:
                db.execute(f"PRAGMA user_version={SCHEMA}")
            return db
        except sqlite3.OperationalError:
            # Locked, read-only, or briefly unopenable — NOT corruption. The
            # file may hold years of ids; leave it be and run without the
            # filter rather than rename a healthy store aside.
            return None
        except sqlite3.DatabaseError:
            # Not a database any more. Keep the file — somebody may want to look
            # at it — and start a new one, so tomorrow's run remembers again.
            if not retry:
                return None
            set_aside(self.path, self.today)
            return self._open(retry=False)
        except (OSError, sqlite3.Error):
            return None

    def _import_json(self) -> None:
        """Carry an older delivered.json in, once, then leave it behind renamed."""
        legacy = self.path.with_name("delivered.json")
        if not legacy.exists():
            return
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            ids = data.get("ids") if isinstance(data, dict) else None
            if isinstance(ids, dict) and self.db is not None:
                self.db.executemany(
                    "INSERT OR IGNORE INTO delivered(place_id, day) VALUES (?, ?)",
                    [(str(k), str(v)) for k, v in ids.items()])
            legacy.replace(legacy.with_suffix(".json.imported"))
        except (OSError, ValueError, sqlite3.Error):
            pass

    def close(self) -> None:
        if self.db is not None:
            try:
                self.db.close()
            except sqlite3.Error:
                pass
            self.db = None

    # -- reading -------------------------------------------------------------
    def __contains__(self, place_id: object) -> bool:
        key = str(place_id or "")
        if key in self.pending:
            return True
        if self.db is None or not key:
            return False
        try:
            return self.db.execute("SELECT 1 FROM delivered WHERE place_id=?",
                                   (key,)).fetchone() is not None
        except sqlite3.Error:
            return False

    def __len__(self) -> int:
        if self.db is None:
            return len(self.pending)
        try:
            return int(self.db.execute("SELECT COUNT(*) FROM delivered").fetchone()[0])
        except sqlite3.Error:
            return len(self.pending)

    def when(self, place_id: str) -> str:
        if self.db is None:
            return self.pending.get(place_id, "")
        try:
            row = self.db.execute("SELECT day FROM delivered WHERE place_id=?",
                                  (place_id,)).fetchone()
        except sqlite3.Error:
            return ""
        return row[0] if row else ""

    def by_day(self, days: int = 7) -> list[tuple[str, int]]:
        """The most recent days that delivered anything, oldest first."""
        if self.db is None:
            return []
        try:
            rows = self.db.execute(
                "SELECT day, COUNT(*) FROM delivered GROUP BY day "
                "ORDER BY day DESC LIMIT ?", (days,)).fetchall()
        except sqlite3.Error:
            return []
        return [(str(day), int(count)) for day, count in reversed(rows)]

    def since(self, day: dt.date) -> int:
        if self.db is None:
            return 0
        try:
            return int(self.db.execute("SELECT COUNT(*) FROM delivered WHERE day>=?",
                                       (day.isoformat(),)).fetchone()[0])
        except sqlite3.Error:
            return 0

    # -- writing -------------------------------------------------------------
    def add(self, place_ids: Iterable[str]) -> int:
        """Stage ids that are about to be delivered. Returns how many are new."""
        stamp = self.today.isoformat()
        added = 0
        for place_id in place_ids:
            key = str(place_id or "").strip()
            if key and key not in self.pending and key not in self:
                self.pending[key] = stamp
                added += 1
        return added

    def forget(self) -> int:
        """Empty the record — the next search may deliver everything again."""
        count = len(self)
        self.pending.clear()
        if self.db is not None:
            try:
                self.db.execute("DELETE FROM delivered")
                self.db.execute("VACUUM")
            except sqlite3.Error:
                return 0
        return count

    def save(self) -> None:
        """Commit the staged ids. Safe to call twice; safe to never call."""
        if not self.pending or self.db is None:
            self.pending.clear()
            return
        try:
            self.db.execute("BEGIN")
            self.db.executemany(
                "INSERT OR IGNORE INTO delivered(place_id, day) VALUES (?, ?)",
                list(self.pending.items()))
            self.db.execute("COMMIT")
            self.pending.clear()
        except sqlite3.Error:
            try:
                self.db.execute("ROLLBACK")
            except sqlite3.Error:
                pass
