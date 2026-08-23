"""
LeadMap — Google Places → CSV / Excel / PDF business lead extractor.

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
    cli.py          the command line          session.py  the guided session
    ui/             theme, reporter, tables, the block-letter opening
    validate/       offline checks: gazetteer (places), place_types (categories)

The names below are re-exported so `import leadmap` reaches the useful parts
without knowing which module they live in.
"""

from __future__ import annotations

from .config import (Settings, apply_env_defaults, ask, collect_inputs,
                     env_default, load_environment)
from .constants import (APP_TAGLINE, APP_TITLE, COLUMNS, DEFAULT_TILE_BUDGET,
                        ENV_KEYS, FIELD_MASK, GEOCODE_URL, MAX_PAGES, MAX_RADIUS_M,
                        MIN_TILE_RADIUS, PAGE_SIZE, PLACES_SEARCH_URL, SATURATED,
                        SEARCH_SKU, VERSION)
from .errors import PlacesError, RetryableError
from .export import (FORMATS, READABLE, convert_file, output_path_for,
                     read_dataframe, write_dataframe, write_pdf)
from .geometry import Tile, build_tiles, haversine, split_tile
from .places import PlacesClient
from .records import address_part, name_matches, to_row
from .search import run
from .ui.banner import banner
from .ui.report import Reporter, elide, mask_key, progress_bar, short_path
from .ui.tables import results_table, summary_panel
from .ui.theme import BRANCH, BULLET, WORK_VERBS, console

__version__ = VERSION
__author__ = "LeadMap contributors"
__license__ = "MIT"
__url__ = "https://github.com/DarkVertana/Lead-Map"

__all__ = [
    "APP_TAGLINE", "APP_TITLE", "BRANCH", "BULLET", "COLUMNS", "DEFAULT_TILE_BUDGET",
    "ENV_KEYS", "FIELD_MASK", "FORMATS", "GEOCODE_URL", "MAX_PAGES", "MAX_RADIUS_M",
    "MIN_TILE_RADIUS", "PAGE_SIZE", "PLACES_SEARCH_URL", "READABLE", "Reporter",
    "SATURATED", "SEARCH_SKU", "Settings", "PlacesClient", "PlacesError",
    "RetryableError", "Tile", "VERSION", "WORK_VERBS", "address_part",
    "apply_env_defaults", "ask", "banner", "build_tiles", "collect_inputs", "console",
    "convert_file", "elide", "env_default", "haversine", "load_environment",
    "mask_key", "name_matches", "output_path_for", "progress_bar", "read_dataframe",
    "results_table", "run", "short_path", "split_tile", "summary_panel", "to_row",
    "write_dataframe", "write_pdf",
]
