"""
Remembers where a place is, so no later run ever pays to ask again.

Geocoding is a billed call, and "Pune, India" resolves to the same point today,
tomorrow and next year. The answer is kept for good — this is a long-running
tool, and re-asking a question already answered is money for nothing — keyed by
the exact question asked, language and region included.

    ~/.local/state/businesslead/geocode.json     (BUSINESSLEAD_GEOCACHE_FILE overrides)

It sits with the usage ledger rather than in the cache directory because losing
it costs calls. Delete the file (or an entry) to make a location be asked again;
Google's own terms put a 30-day limit on caching geocodes, so keeping them for
longer is a decision this tool leaves to whoever runs it.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from .paths import FileLock, env, set_aside, state_dir, write_json_atomic

VERSION = 1
MAX_ENTRIES = 10_000    # a stop on unbounded growth, not an expiry


def default_path() -> Path:
    override = env("GEOCACHE_FILE")
    if override:
        return Path(override).expanduser()
    return state_dir() / "geocode.json"


def _key(location: str, language: Optional[str], region: Optional[str]) -> str:
    return "|".join([" ".join(location.lower().split()), language or "", region or ""])


class GeoCache:
    """location → (lat, lng, resolved address, viewport radius)."""

    def __init__(self, path: Optional[Path] = None, *, today: Optional[dt.date] = None):
        self.path = Path(path) if path else default_path()
        self.today = today or dt.date.today()
        self.entries: dict[str, dict] = self._read()
        self.dirty = False

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
            found = data.get("entries")
            if isinstance(found, dict):
                return found
        set_aside(self.path, self.today)
        return {}

    def get(self, location: str, language: Optional[str] = None,
            region: Optional[str] = None) -> Optional[tuple[float, float, str, float | None]]:
        """Where this location is, from any earlier run. Never expires."""
        entry = self.entries.get(_key(location, language, region))
        if not entry:
            return None
        try:
            found = (float(entry["lat"]), float(entry["lng"]), str(entry["resolved"]),
                     None if entry.get("radius") is None else float(entry["radius"]))
        except (KeyError, TypeError, ValueError):
            return None
        stamp = self.today.isoformat()
        if entry.get("used") != stamp:     # touched once a day: cheap, and it
            entry["used"] = stamp          # keeps the busy places off the cull
            self.dirty = True
        return found

    def put(self, location: str, language: Optional[str], region: Optional[str],
            lat: float, lng: float, resolved: str, radius: float | None) -> None:
        stamp = self.today.isoformat()
        self.entries[_key(location, language, region)] = {
            "lat": lat, "lng": lng, "resolved": resolved, "radius": radius,
            "day": stamp, "used": stamp,
        }
        self.dirty = True

    def _merged(self) -> dict[str, dict]:
        """Disk entries with ours laid over them: a geocode is a fact, so a
        concurrent run's answers are as good as this one's — keep both."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(self.entries)
        disk = (raw.get("entries")
                if isinstance(raw, dict) and raw.get("version") == VERSION else None)
        if not isinstance(disk, dict):
            return dict(self.entries)
        return {**disk, **self.entries}

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(self.path.with_name(self.path.name + ".lock")):
                kept = self._merged()
                if len(kept) > MAX_ENTRIES:    # culled by size only, least used first
                    kept = dict(sorted(kept.items(),
                                       key=lambda item: (item[1].get("used") or
                                                         item[1].get("day", ""))
                                       )[-MAX_ENTRIES:])
                write_json_atomic(self.path, {"version": VERSION, "entries": kept},
                                  separators=(",", ":"), sort_keys=True)
            self.entries = kept
            self.dirty = False
        except OSError:
            pass        # stays dirty: the next save() tries again
