"""
Turning a Places result into one flat, usable row.

Most of the work here is the address. Google returns it twice: as a printed
one-liner (`formattedAddress`) and as a list of typed components. The components
are authoritative when they're there — but plenty of the world doesn't have a
`route`. An Indian shop address reads "Shop No. 4, Ace Residences, near RD
Circle, Karmayogi Nagar, Govind Nagar, Nashik" and carries no street at all, so
falling back to the printed line is the difference between a filled column and
an empty one: on a real run of 121 barbers in Nashik it took `street` from
75/121 to 121/121.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Component types, in the order we'd like to find each part of an address.
STREET_TYPES = ("route", "premise", "subpremise", "establishment", "point_of_interest")
AREA_TYPES = ("sublocality_level_1", "sublocality", "neighborhood")
CITY_TYPES = ("locality", "postal_town", "administrative_area_level_3")
DISTRICT_TYPES = ("administrative_area_level_2",)


def address_part(components: Iterable[dict] | None, *wanted: str, short: bool = False) -> str:
    """The first component matching any of `wanted`, in the order asked for."""
    parts = list(components or [])
    for want in wanted:
        for comp in parts:
            if want in (comp.get("types") or []):
                if short:
                    return comp.get("shortText") or comp.get("longText") or ""
                return comp.get("longText") or comp.get("shortText") or ""
    return ""


def split_address(formatted: str, *, city: str = "", state: str = "", postal: str = "",
                  country: str = "", area: str = "") -> tuple[str, str]:
    """(street, area) read off the printed address, minus the parts we know.

    Strip the city, state, postcode and country off the end and what remains is
    the street line; its last comma-separated piece is usually the locality —
    "Cidco", "Govind Nagar" — so it becomes the area unless we already have one.
    """
    known = {value.strip().lower() for value in (city, state, country, area) if value}
    kept: list[str] = []
    for part in (piece.strip() for piece in (formatted or "").split(",")):
        if not part or part.lower() in known:
            continue
        if postal and postal in part:
            rest = part.replace(postal, "").strip(" ,-").lower()
            if not rest or rest in known:
                continue
        kept.append(part)

    if not kept:
        return "", area
    if area or len(kept) == 1:
        return ", ".join(kept), area
    return ", ".join(kept[:-1]), kept[-1]


def to_row(place: dict[str, Any], category: str, query: str, searched_name: str = "") -> dict:
    comps = place.get("addressComponents")
    loc = place.get("location") or {}
    hours = place.get("regularOpeningHours") or {}
    links = place.get("googleMapsLinks") or {}
    formatted = place.get("formattedAddress", "")

    # -- the address, components first and the printed line as backstop --------
    number, route = address_part(comps, "street_number"), address_part(comps, "route")
    street = " ".join(part for part in (number, route) if part).strip()
    if not street:
        street = address_part(comps, "premise", "subpremise")
    area = address_part(comps, *AREA_TYPES)
    city = address_part(comps, *CITY_TYPES)
    district = address_part(comps, *DISTRICT_TYPES)
    state = address_part(comps, "administrative_area_level_1")
    state_code = address_part(comps, "administrative_area_level_1", short=True)
    postal = address_part(comps, "postal_code")
    country = address_part(comps, "country")
    if not city:
        city = district
    if not street or not area:
        fallback_street, fallback_area = split_address(
            formatted, city=city, state=state, postal=postal, country=country, area=area)
        street = street or fallback_street
        area = area or fallback_area

    return {
        "name": (place.get("displayName") or {}).get("text", ""),
        "category": category,
        "primary_type": ((place.get("primaryTypeDisplayName") or {}).get("text", "")
                         or place.get("primaryType", "")),
        "all_types": ", ".join(place.get("types") or []),
        "phone": place.get("nationalPhoneNumber", ""),
        "international_phone": place.get("internationalPhoneNumber", ""),
        "website": place.get("websiteUri", ""),
        "street": street,
        "area": area,
        "city": city,
        "district": district,
        "state": state,
        "state_code": state_code,
        "postal_code": postal,
        "country": country,
        "formatted_address": formatted,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "rating": place.get("rating"),
        "reviews_count": place.get("userRatingCount"),
        "price_level": (place.get("priceLevel") or "").replace("PRICE_LEVEL_", "").title(),
        "price_range": price_range(place.get("priceRange")),
        "business_status": place.get("businessStatus", ""),
        "opened": opening_date(place.get("openingDate")),
        "opening_hours": " | ".join(hours.get("weekdayDescriptions") or []),
        "open_now": hours.get("openNow", ""),
        "google_maps_url": place.get("googleMapsUri", ""),
        "reviews_url": links.get("reviewsUri", ""),
        "directions_url": links.get("directionsUri", ""),
        "summary": (place.get("editorialSummary") or {}).get("text", ""),
        "place_id": place.get("id", ""),
        "search_query": query,
        "searched_name": searched_name,
    }


def price_range(value: dict | None) -> str:
    """{'startPrice': {'units': '200'}, …} → '₹200–500', as Google words it."""
    if not value:
        return ""
    def side(key):
        money = value.get(key) or {}
        units = money.get("units")
        return f"{money.get('currencyCode', '')} {units}".strip() if units else ""
    low, high = side("startPrice"), side("endPrice")
    return " – ".join(part for part in (low, high) if part)


def opening_date(value: dict | None) -> str:
    """{'year': 2019, 'month': 4, 'day': 1} → '2019-04-01'."""
    if not value or not value.get("year"):
        return ""
    return "-".join(str(value[key]).zfill(2) for key in ("year", "month", "day")
                    if value.get(key))


def name_matches(place_name: str, wanted: str) -> bool:
    """True when every word of the wanted name appears in the business name."""
    place_words = set(re.findall(r"[a-z0-9]+", (place_name or "").lower()))
    return all(any(w.startswith(word) for w in place_words)
               for word in re.findall(r"[a-z0-9]+", (wanted or "").lower()))
