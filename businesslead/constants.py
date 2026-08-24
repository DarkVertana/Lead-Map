"""
Everything fixed about the Google APIs we talk to: endpoints, hard limits, the
field mask, and the columns those fields become.

The field mask is the expensive decision in this file — it decides which SKU
every search bills at, and therefore how many are free each month. See quota.py.
"""

from __future__ import annotations

from . import quota


APP_TITLE = "Business Lead"
APP_TAGLINE = "Business leads from Google Places  ·  csv · excel · pdf · json"
VERSION = "2.0.0"

# The folder results land in, beside wherever you run from.
# BUSINESSLEAD_OUTPUT_DIR moves it somewhere else entirely.
OUTPUT_DIR_NAME = "Business Lead"

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ENV_KEYS = ("GOOGLE_MAPS_API_KEY", "GOOGLE_PLACES_API_KEY")

MAX_PAGES = 3          # the API returns at most 3 pages (~60 places) per query
PAGE_SIZE = 20         # hard API maximum per page
MAX_RADIUS_M = 50_000  # hard API maximum

# A sweep keeps splitting an area while it looks like Google is holding back.
# A tile that comes back this full has almost certainly hit the 60-place ceiling,
# so the same ground is searched again in four smaller circles.
SATURATED = MAX_PAGES * PAGE_SIZE - 5
MIN_TILE_RADIUS = 300.0     # below this, splitting stops finding anything new
# There is no tile budget: a sweep digs until the area stops giving or the day's
# free calls are gone. --max-tiles puts a ceiling back on if you want one. The
# ids-only SKU is unmetered, so nothing would ever stop it — that one gets a cap.
UNMETERED_TILES = 200
# Searches in a row that hand back nothing new before a sweep gives up. The
# queue it hasn't reached is kept, so the next run starts there instead.
DRY_TILES = 10
# Searches in a row that fail outright before a sweep stops. A bad key or a
# dead service fails on every tile the same way — draining the whole queue to
# find that out would burn the frontier for nothing.
ERROR_TILES = 5

# Fields requested from the Places API. Trim this to lower your bill: contact and
# atmosphere fields (phone, website, hours, rating) bill at a higher SKU than the
# basic id/name/address ones.
FIELD_MASK = ",".join([
    "nextPageToken",
    "places.id", "places.displayName", "places.formattedAddress",
    "places.addressComponents", "places.location",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber",
    "places.websiteUri", "places.googleMapsUri",
    "places.rating", "places.userRatingCount", "places.priceLevel",
    "places.businessStatus", "places.primaryType", "places.primaryTypeDisplayName",
    "places.types", "places.regularOpeningHours", "places.editorialSummary",
])

# These cost nothing extra — the mask above already bills at the top tier, so the
# rest of that tier may as well be collected. They are kept separate so a search
# can fall back to the mask above if Google ever stops recognising one of them.
EXTRA_FIELDS = ["places.priceRange", "places.openingDate", "places.googleMapsLinks"]
CORE_FIELD_MASK = FIELD_MASK
FIELD_MASK = ",".join([FIELD_MASK, *EXTRA_FIELDS])

# Which SKU our requests bill at, worked out from the field mask above. Trim the
# mask and both the price and the free allowance follow — see quota.py.
SEARCH_SKU = quota.sku_for_mask(FIELD_MASK)

# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------
# Google prices a search by the most expensive field you ask for, so asking for
# less is the only way to a bigger free allowance. A plan is exactly that: the
# tier to stop at. Everything above it is dropped from the mask, those columns
# come back empty, and the monthly allowance changes to match.

# What a format is called, and the extension it writes. PLACES_FORMAT in .env
# picks the one every run uses — the session never asks for it.
FILE_FORMATS = {
    "csv": ".csv", "excel": ".xlsx", "xlsx": ".xlsx", "xls": ".xlsx",
    "spreadsheet": ".xlsx", "sheet": ".xlsx", "workbook": ".xlsx",
    "pdf": ".pdf", "print": ".pdf", "json": ".json",
}
DEFAULT_FORMAT = "csv"


def suffix_for(fmt: str) -> str:
    """'excel' → '.xlsx'. An extension is taken as it is; anything else is csv."""
    word = (fmt or "").strip().lower()
    if word in FILE_FORMATS:
        return FILE_FORMATS[word]
    if word.startswith(".") and word[1:] in FILE_FORMATS:
        return FILE_FORMATS[word[1:]]
    return FILE_FORMATS[DEFAULT_FORMAT]


DEFAULT_PLAN = "atmosphere"

PLAN_ALIASES = {
    "full": "atmosphere", "everything": "atmosphere", "max": "atmosphere",
    "contact": "enterprise", "leads": "enterprise",
    "basic": "pro", "names": "pro",
    "minimal": "essentials", "addresses": "essentials",
    "ids-only": "ids", "free": "ids", "count": "ids",
}
PLAN_NOTES = {
    "atmosphere": "everything — phone, website, rating, hours, editorial summary",
    "enterprise": "drops the editorial summary, which is empty on most small businesses",
    "pro": "drops phone, website, rating, reviews, price and hours",
    "essentials": "drops the business name too — ids, addresses, coordinates, types",
    "ids": "place ids only, for counting or enriching later",
}


def plan_name(plan: str) -> str:
    """'full' → 'atmosphere'. Unknown names raise, so a typo can't silently bill."""
    wanted = (plan or DEFAULT_PLAN).strip().lower().replace("_", "-")
    resolved = PLAN_ALIASES.get(wanted, wanted)
    if resolved not in quota.TIER_ORDER:
        raise ValueError(f"unknown plan {plan!r} — "
                         f"try {', '.join(reversed(quota.TIER_ORDER))}")
    return resolved


def mask_for(plan: str) -> str:
    """The field mask a plan is allowed to ask for."""
    ceiling = quota.TIER_ORDER.index(plan_name(plan))
    return ",".join(field for field in FIELD_MASK.split(",")
                    if quota.TIER_ORDER.index(quota.tier_of(field)) <= ceiling)


def dropped_by(plan: str) -> list[str]:
    """The fields a plan gives up, in the order the mask lists them."""
    ceiling = quota.TIER_ORDER.index(plan_name(plan))
    return [field.split(".")[-1] for field in FIELD_MASK.split(",")
            if quota.TIER_ORDER.index(quota.tier_of(field)) > ceiling]


def sku_for_plan(plan: str) -> "quota.Sku":
    return quota.sku_for_tier(plan_name(plan))

# The spreadsheet, in reading order: who they are, how to reach them, where they
# are (broken up), then everything else Google knows, and last the three columns
# about the search rather than the business. `extracted_on` is the day the row
# was written: a file is added to by every later run of the same search, so it
# is what tells one run's findings from the next.
COLUMNS = [
    "name", "category", "primary_type", "all_types",
    "phone", "international_phone", "website",
    "street", "area", "city", "district", "state", "state_code", "postal_code",
    "country", "formatted_address", "latitude", "longitude",
    "rating", "reviews_count", "price_level", "price_range", "business_status",
    "opened", "opening_hours", "open_now",
    "google_maps_url", "reviews_url", "directions_url",
    "summary", "place_id", "search_query", "searched_name", "extracted_on",
]
