"""
Everything fixed about the Google APIs we talk to: endpoints, hard limits, the
field mask, and the columns those fields become.

The field mask is the expensive decision in this file — it decides which SKU
every search bills at, and therefore how many are free each month. See quota.py.
"""

from __future__ import annotations

from . import quota


APP_TITLE = "LeadMap"
APP_TAGLINE = "Business leads from Google Places  ·  csv · excel · pdf · json"
VERSION = "2.0.0"

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
DEFAULT_TILE_BUDGET = 25    # tiles per search unless --max-tiles says otherwise

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

# The spreadsheet, in reading order: who they are, how to reach them, where they
# are (broken up), then everything else Google knows.
COLUMNS = [
    "name", "category", "primary_type", "all_types",
    "phone", "international_phone", "website",
    "street", "area", "city", "district", "state", "state_code", "postal_code",
    "country", "formatted_address", "latitude", "longitude",
    "rating", "reviews_count", "price_level", "price_range", "business_status",
    "opened", "opening_hours", "open_now",
    "google_maps_url", "reviews_url", "directions_url",
    "summary", "place_id", "search_query", "searched_name",
]
