"""
Where LeadMap keeps what it remembers, on whichever platform it's running.

Two directories: state (the usage ledger and the search history — precious,
should survive) and cache (the gazetteer index — rebuildable in a second).
Unix keeps them apart under ~/.local/state and ~/.cache; Windows puts both under
%LOCALAPPDATA%, which is the same idea with a different address.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP = "leadmap"


def _local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def state_dir() -> Path:
    """The usage ledger and the search history live here."""
    override = os.environ.get("XDG_STATE_HOME")
    if override:
        return Path(override).expanduser() / APP
    if sys.platform == "win32":
        return _local_app_data() / APP / "state"
    return Path.home() / ".local" / "state" / APP


def cache_dir() -> Path:
    """The gazetteer index lives here. Safe to delete; it rebuilds."""
    override = os.environ.get("XDG_CACHE_HOME")
    if override:
        return Path(override).expanduser() / APP
    if sys.platform == "win32":
        return _local_app_data() / APP / "cache"
    return Path.home() / ".cache" / APP
