"""
Where Business Lead keeps what it remembers, on whichever platform it's running.

Two directories: state (the usage ledger and the search history — precious,
should survive) and cache (the gazetteer index — rebuildable in a second).
Unix keeps them apart under ~/.local/state and ~/.cache; Windows puts both under
%LOCALAPPDATA%, which is the same idea with a different address.

Both were named after the tool, so renaming the tool moved them. Anything left
under the old name is adopted the first time it's looked for — see `_adopt`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP = "businesslead"
LEGACY_APP = "leadmap"        # what the tool was called before it was Business Lead

ENV_PREFIX = "BUSINESSLEAD_"
LEGACY_ENV_PREFIX = "LEADMAP_"


def env(suffix: str, default=None):
    """Read BUSINESSLEAD_<suffix>, falling back to the name used before the rename.

    Same reasoning as `_adopt` below. A cap or a file location someone set under
    the old spelling has to keep working, because the failure mode is silent:
    the setting simply stops applying, and whatever it was holding back — a
    ledger kept elsewhere, a ceiling below Google's — starts happening again.
    """
    for prefix in (ENV_PREFIX, LEGACY_ENV_PREFIX):
        value = os.environ.get(prefix + suffix)
        if value:
            return value
    return default


def set_aside(path, today=None) -> None:
    """Keep a state file we can no longer read, instead of quietly dropping it.

    These files hold years of work. A truncated write or a format from a newer
    version is a reason to start again, never a reason to destroy the evidence:
    it is renamed, and whoever cares can look at it.
    """
    import datetime as dt
    from pathlib import Path as _Path

    path = _Path(path)
    stamp = (today or dt.date.today()).isoformat()
    try:
        if path.exists():
            path.replace(path.with_name(f"{path.name}.unreadable-{stamp}"))
    except OSError:
        pass


def write_json_atomic(path, payload, **dump_kwargs) -> None:
    """Write JSON to a temp file, fsync it, then atomically replace `path`.

    The fsync matters: a rename can be journalled before the data blocks land,
    and a power cut then leaves an empty file where a year of state used to be.
    On Windows the replace is retried a few times — antivirus and backup tools
    hold freshly written files open for a moment. The temp file never outlives
    a failure, and any failure is raised for the caller to deal with.
    """
    import json
    import tempfile
    import time

    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False,
                                         encoding="utf-8") as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, **dump_kwargs)
            handle.flush()
            os.fsync(handle.fileno())
        last_error = None
        for pause in (0.0, 0.05, 0.2, 0.5):
            if pause:
                time.sleep(pause)
            try:
                temporary.replace(path)
                temporary = None
                return
            except PermissionError as exc:     # Windows: someone holds the file
                last_error = exc
        raise last_error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


class FileLock:
    """A cross-platform advisory lock: the file existing means someone is writing.

    Two runs saving state at once is rare and brief, so this waits a little,
    steals locks that look abandoned, and never raises — a lock that can't be
    taken must not stop a save that can still happen.
    """

    def __init__(self, path, timeout: float = 5.0, stale: float = 60.0):
        self.path = Path(path)
        self.timeout = timeout
        self.stale = stale
        self._held = False

    def __enter__(self) -> "FileLock":
        import time
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                self._held = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()               # a crash left it behind
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    return self       # carry on unlocked: saving beats not saving
                time.sleep(0.05)
            except OSError:
                return self           # unwritable dir: the save itself will say so

    def __exit__(self, *exc) -> bool:
        if self._held:
            try:
                self.path.unlink()
            except OSError:
                pass
        return False


def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def _adopt(current: Path, legacy: Path) -> Path:
    """Take over a directory the tool left behind under its old name.

    The ledger inside is the only record of what has been spent against Google's
    free tier this month. Starting a clean one because the tool was renamed
    would hand back a month of calls that are already gone, and the bill for
    spending them twice is real — so the old directory is moved, not abandoned.

    A move that can't happen is not worth failing over: the old location is
    returned instead, and the ledger keeps being read and written where it is.
    """
    if current.exists() or not legacy.is_dir():
        return current
    try:
        current.parent.mkdir(parents=True, exist_ok=True)
        legacy.rename(current)
    except OSError:
        return legacy
    return current


def state_dir() -> Path:
    """The usage ledger and the search history live here."""
    override = os.environ.get("XDG_STATE_HOME")
    if override:
        root = Path(override).expanduser()
        return _adopt(root / APP, root / LEGACY_APP)
    if sys.platform == "win32":
        root = _local_app_data()
        return _adopt(root / APP / "state", root / LEGACY_APP / "state")
    root = Path.home() / ".local" / "state"
    return _adopt(root / APP, root / LEGACY_APP)


def cache_dir() -> Path:
    """The gazetteer index lives here. Safe to delete; it rebuilds."""
    override = os.environ.get("XDG_CACHE_HOME")
    if override:
        root = Path(override).expanduser()
        return _adopt(root / APP, root / LEGACY_APP)
    if sys.platform == "win32":
        root = _local_app_data()
        return _adopt(root / APP / "cache", root / LEGACY_APP / "cache")
    root = Path.home() / ".cache"
    return _adopt(root / APP, root / LEGACY_APP)


def config_dir() -> Path:
    """What you edit by hand lives here — the places you have added yourself.

    Kept apart from state and cache on purpose: those two are ours to write and
    yours to delete, and this one is the opposite.
    """
    override = os.environ.get("XDG_CONFIG_HOME")
    if override:
        root = Path(override).expanduser()
        return _adopt(root / APP, root / LEGACY_APP)
    if sys.platform == "win32":
        root = _local_app_data()
        return _adopt(root / APP / "config", root / LEGACY_APP / "config")
    root = Path.home() / ".config"
    return _adopt(root / APP, root / LEGACY_APP)
