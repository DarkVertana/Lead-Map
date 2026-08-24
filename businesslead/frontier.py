"""
Where each search got to, so the next run carries on instead of starting over.

The ignore list in `delivered.py` keeps the data unique, but on its own it does
not save a single call: yesterday's tiles would be searched again, their results
recognised as already delivered, and thrown away. That is the expensive half of
the problem, and this is the other half.

A sweep is a queue of circles. When a run stops — the day's calls are gone, or
the ground stopped giving — the circles already searched and the ones still
waiting are written down under a fingerprint of the search that made them:

    ~/.local/state/businesslead/frontier.json      (BUSINESSLEAD_FRONTIER_FILE overrides)

Ask for the same thing tomorrow and it picks the queue back up where it stopped.
Ask for it once the queue has emptied and it says so instead of spending
anything: that area has been mined out, and `--resweep` is how you insist.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .geometry import Tile
from .paths import FileLock, env, set_aside, state_dir, write_json_atomic

VERSION = 1
KEEP_SWEEPS = 500       # distinct searches remembered, least recently used first


def human_day(day: str) -> str:
    """'2026-08-24' → '24 Aug 2026'. Dates are for reading."""
    try:
        return dt.date.fromisoformat(day).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return day or "an earlier run"


def default_path() -> Path:
    override = env("FRONTIER_FILE")
    if override:
        return Path(override).expanduser()
    return state_dir() / "frontier.json"


# ---------------------------------------------------------------------------
# Tiles, as text
# ---------------------------------------------------------------------------

def encode(tile: Tile) -> str:
    """A circle as one short string — the same key the run uses for 'searched'."""
    return f"{tile.lat:.5f},{tile.lng:.5f},{round(tile.radius)}"


def decode(text: str) -> Optional[Tile]:
    try:
        lat, lng, radius = text.split(",")
        return Tile(float(lat), float(lng), float(radius))
    except (AttributeError, TypeError, ValueError):
        return None


def filters_key(**flags) -> str:
    """The result-changing filters, as one canonical string — '' when unfiltered."""
    return ",".join(f"{name}={value}" for name, value in sorted(flags.items())
                    if value)


def fingerprint(location: str, category: str, name: str, region: Optional[str],
                language: Optional[str], radius: float, filters: str = "") -> str:
    """One search, identified by what makes it return different places.

    Filters are part of that identity: a sweep under --min-rating 4.5 must not
    mark the unfiltered search as mined out. An unfiltered search keeps the
    key it always had, so old frontiers still resume.
    """
    seed = "|".join([" ".join((location or "").lower().split()),
                     " ".join((category or "").lower().split()),
                     " ".join((name or "").lower().split()),
                     (region or "").lower(), (language or "").lower(),
                     str(round(radius))])
    if filters:
        seed += "|" + filters
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# One search's progress
# ---------------------------------------------------------------------------

@dataclass
class Sweep:
    key: str
    query: str = ""
    done: list[str] = field(default_factory=list)    # circles already searched
    queue: list[str] = field(default_factory=list)   # circles still waiting
    started: str = ""
    updated: str = ""
    finished: str = ""      # the day the queue emptied: nothing left to search
    delivered: int = 0      # businesses this search has handed over, all runs
    searched: int = 0       # circles covered, kept once `done` is thrown away

    @property
    def fresh(self) -> bool:
        """Nothing searched yet — this is the first run of this search."""
        return not self.done and not self.queue

    @property
    def exhausted(self) -> bool:
        """Every circle has been searched and none is waiting."""
        return bool(self.finished) and not self.queue

    def tiles(self) -> list[Tile]:
        return [tile for tile in (decode(text) for text in self.queue) if tile]


class Frontier:
    """Every search's progress, keyed by fingerprint."""

    def __init__(self, path: Optional[Path] = None, *, today: Optional[dt.date] = None):
        self.path = Path(path) if path else default_path()
        self.today = today or dt.date.today()
        self.sweeps: dict[str, dict] = self._read()
        self._touched: set[str] = set()    # only these are ours to overwrite
        self._forget_all = False

    def _read(self) -> dict[str, dict]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            set_aside(self.path, self.today)     # corrupt: kept, not destroyed
            return {}
        if isinstance(data, dict) and data.get("version") == VERSION:
            found = data.get("sweeps")
            if isinstance(found, dict):
                return found
        set_aside(self.path, self.today)         # a shape we don't know
        return {}

    def __len__(self) -> int:
        return len(self.sweeps)

    def waiting(self) -> int:
        """Circles queued across every unfinished search."""
        return sum(len(sweep.get("queue") or ()) for sweep in self.sweeps.values())

    def load(self, key: str) -> Sweep:
        raw = self.sweeps.get(key) or {}
        return Sweep(key=key, query=str(raw.get("query", "")),
                     done=list(raw.get("done") or ()),
                     queue=list(raw.get("queue") or ()),
                     started=str(raw.get("started", "")),
                     updated=str(raw.get("updated", "")),
                     finished=str(raw.get("finished", "")),
                     delivered=int(raw.get("delivered", 0)),
                     searched=int(raw.get("searched", 0)))

    def record(self, sweep: Sweep, *, query: str, done: Iterable[str],
               queue: Iterable[Tile], delivered: int) -> Sweep:
        """Fold what a run just did into the search's progress."""
        stamp = self.today.isoformat()
        sweep.query = query or sweep.query
        sweep.done = sorted(done)
        sweep.searched = len(sweep.done)
        sweep.queue = [encode(tile) for tile in queue]
        sweep.started = sweep.started or stamp
        sweep.updated = stamp
        sweep.finished = "" if sweep.queue else (sweep.finished or stamp)
        sweep.delivered += max(0, delivered)
        if sweep.finished:
            # Nothing will be resumed, so the list of circles is dead weight —
            # years of finished sweeps shouldn't be years of megabytes.
            sweep.done = []
        self.sweeps[sweep.key] = {
            "query": sweep.query, "done": sweep.done, "queue": sweep.queue,
            "started": sweep.started, "updated": sweep.updated,
            "finished": sweep.finished, "delivered": sweep.delivered,
            "searched": sweep.searched,
        }
        self._touched.add(sweep.key)
        return sweep

    def restart(self, key: str) -> Sweep:
        """Throw away one search's progress: --resweep asked for it all again."""
        self.sweeps.pop(key, None)
        self._touched.add(key)
        return Sweep(key=key)

    def forget(self) -> int:
        """Forget every search's progress. Returns how many were dropped."""
        count = len(self.sweeps)
        self.sweeps = {}
        self._forget_all = True
        self.save()
        return count

    def _merged(self) -> dict[str, dict]:
        """This run's sweeps folded over what's on disk right now.

        Another process may have saved since this one loaded; only the sweeps
        this run actually touched are ours to overwrite — everyone else's
        progress stays exactly as they left it.
        """
        if self._forget_all:
            return dict(self.sweeps)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(self.sweeps)
        disk = (raw.get("sweeps")
                if isinstance(raw, dict) and raw.get("version") == VERSION else None)
        if not isinstance(disk, dict):
            return dict(self.sweeps)
        merged = dict(disk)
        for key in self._touched:
            if key in self.sweeps:
                merged[key] = self.sweeps[key]
            else:
                merged.pop(key, None)      # restarted: its old progress goes too
        return merged

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(self.path.with_name(self.path.name + ".lock")):
                kept = self._merged()
                if len(kept) > KEEP_SWEEPS:      # least recently touched go first
                    kept = dict(sorted(kept.items(),
                                       key=lambda item: item[1].get("updated", "")
                                       )[-KEEP_SWEEPS:])
                write_json_atomic(self.path, {"version": VERSION, "sweeps": kept},
                                  separators=(",", ":"), sort_keys=True)
            self.sweeps = kept
            self._forget_all = False
        except OSError:
            pass
