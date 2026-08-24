"""
Business Lead — Google Places → CSV / Excel / PDF business lead extractor.

The package is laid out by job:

    constants.py    endpoints, limits, the field mask, the output columns
    errors.py       PlacesError (fatal) and RetryableError (transient)
    geometry.py     Tile, and the maths that splits a circle into four
    places.py       the HTTP client: one call per quota unit
    records.py      a Places result → one flat row
    search.py       a whole run: check, locate, sweep, write, report
    export.py       csv / xlsx / pdf / json, and converting between them
    config.py       Settings, and the flags / environment / .env behind them
    quota.py        the free tier: SKUs, the ledger, today's share
    delivered.py    the ids already handed over (SQLite), so no run repeats one
    frontier.py     where each search got to, so the next run carries on
    geocache.py     where a place is, remembered, so it is only ever asked once
    cli.py          the command line          session.py  the guided session
    ui/             theme, reporter, tables, the block-letter opening
    validate/       offline checks: gazetteer (places), place_types (categories)

The names below are re-exported so `import businesslead` reaches the useful parts
without knowing which module they live in — lazily, so `businesslead --version`
doesn't pay to import pandas.
"""

from __future__ import annotations

import sys
from importlib import import_module

# Windows consoles and pipes often speak cp1252, which has none of the ⏺ ⎿ ▰
# glyphs this tool prints. UTF-8 with replacement means a redirected --usage
# writes a file instead of raising UnicodeEncodeError. Harmless elsewhere.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

from .constants import VERSION      # cheap: constants pulls in quota, nothing heavy

__version__ = VERSION
__author__ = "Business Lead contributors"
__license__ = "MIT"
__url__ = "https://github.com/DarkVertana/Business-Lead"

# name → the module that defines it; imported the first time it is asked for.
_HOME = {
    "Settings": "config", "apply_env_defaults": "config", "ask": "config",
    "collect_inputs": "config", "env_default": "config", "load_environment": "config",
    "Delivered": "delivered",
    "Frontier": "frontier",
    "GeoCache": "geocache",
    "APP_TAGLINE": "constants", "APP_TITLE": "constants", "COLUMNS": "constants",
    "ENV_KEYS": "constants", "FIELD_MASK": "constants", "GEOCODE_URL": "constants",
    "MAX_PAGES": "constants", "MAX_RADIUS_M": "constants",
    "MIN_TILE_RADIUS": "constants", "PAGE_SIZE": "constants",
    "PLACES_SEARCH_URL": "constants", "SATURATED": "constants",
    "SEARCH_SKU": "constants", "VERSION": "constants",
    "PlacesError": "errors", "RetryableError": "errors",
    "FORMATS": "export", "READABLE": "export", "convert_file": "export",
    "output_path_for": "export", "read_dataframe": "export",
    "write_dataframe": "export", "write_pdf": "export",
    "Tile": "geometry", "build_tiles": "geometry", "haversine": "geometry",
    "split_tile": "geometry",
    "PlacesClient": "places",
    "address_part": "records", "name_matches": "records", "to_row": "records",
    "run": "search",
    "banner": "ui.banner",
    "Reporter": "ui.report", "elide": "ui.report", "mask_key": "ui.report",
    "progress_bar": "ui.report", "short_path": "ui.report",
    "results_table": "ui.tables", "summary_panel": "ui.tables",
    "BRANCH": "ui.theme", "BULLET": "ui.theme", "WORK_VERBS": "ui.theme",
    "console": "ui.theme",
}

__all__ = sorted(_HOME)


def __getattr__(name: str):
    module = _HOME.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value              # cached: the next access is a dict hit
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_HOME))
