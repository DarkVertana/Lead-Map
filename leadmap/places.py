"""The Places (New) + Geocoding client: one HTTP call per quota unit."""

from __future__ import annotations

import json
from typing import Any

import requests
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from . import quota
from .constants import (CORE_FIELD_MASK, FIELD_MASK, GEOCODE_URL, MAX_PAGES,
                        PAGE_SIZE, PLACES_SEARCH_URL, SEARCH_SKU, VERSION)
from .errors import PlacesError, RetryableError
from .geometry import Tile, haversine


class PlacesClient:
    """Thin wrapper over the Places (New) + Geocoding endpoints."""

    def __init__(self, api_key: str, timeout: int = 30, budget=None,
                 field_mask: str = FIELD_MASK, sku=SEARCH_SKU):
        self.api_key = api_key
        self.timeout = timeout
        self.requests = 0           # billed calls, so the run can report them
        self.budget = budget        # a quota.Quota, or None to count nothing
        self.field_mask = field_mask    # the plan decides how much we ask for
        self.sku = sku                  # and therefore what it bills at
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": f"places-scraper/{VERSION}"})

    # tenacity handles the transient cases; everything else surfaces immediately
    @retry(retry=retry_if_exception_type(RetryableError),
           wait=wait_exponential(multiplier=1, min=1, max=12),
           stop=stop_after_attempt(4), reraise=True)
    def _request(self, method: str, url: str, sku=None, **kwargs) -> dict[str, Any]:
        if self.budget is not None and sku is not None:
            self.budget.take(sku)                 # raises QuotaExceeded, spends nothing
        self.requests += 1
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            self._refund(sku)                     # never reached Google, never billed
            raise RetryableError(f"network error: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            self._refund(sku)                     # Google doesn't bill these
            raise RetryableError(f"HTTP {response.status_code} from Google, retrying")
        if response.status_code >= 400:
            raise PlacesError(f"HTTP {response.status_code}: {self._error_text(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise PlacesError(f"malformed response from Google: {exc}") from exc

    def _refund(self, sku) -> None:
        if self.budget is not None and sku is not None:
            self.budget.record(sku, -1)
            self.requests -= 1

    @staticmethod
    def _error_text(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip()[:400]
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if payload.get("error_message"):
                return str(payload["error_message"])
        return json.dumps(payload)[:400]

    def geocode(self, location: str, language: str | None = None,
                region: str | None = None) -> tuple[float, float, str, float | None]:
        """Resolve free text to (lat, lng, formatted_address, viewport_radius_m)."""
        params = {"address": location, "key": self.api_key}
        if language:
            params["language"] = language
        if region:
            params["region"] = region

        data = self._request("GET", GEOCODE_URL, sku=quota.GEOCODING, params=params)
        status = data.get("status")
        if status != "OK" or not data.get("results"):
            detail = data.get("error_message", "")
            raise PlacesError(f"Geocoding failed for {location!r}: {status} {detail}".strip())

        result = data["results"][0]
        loc = result["geometry"]["location"]
        radius = None
        viewport = result["geometry"].get("viewport")
        if viewport:
            ne, sw = viewport["northeast"], viewport["southwest"]
            radius = haversine(ne["lat"], ne["lng"], sw["lat"], sw["lng"]) / 2
        return loc["lat"], loc["lng"], result.get("formatted_address", location), radius

    def search_text(self, query: str, tile: Tile, limit: int,
                    included_type: str | None = None, language: str | None = None,
                    region: str | None = None, open_now: bool = False,
                    min_rating: float | None = None,
                    on_warn=None) -> list[dict[str, Any]]:
        """One text search, following pagination up to the API's 3-page cap."""
        headers = {"X-Goog-Api-Key": self.api_key,
                   "X-Goog-FieldMask": self.field_mask}
        body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": PAGE_SIZE,
            "locationBias": {"circle": {
                "center": {"latitude": tile.lat, "longitude": tile.lng},
                "radius": float(tile.radius),
            }},
        }
        if included_type:
            body["includedType"] = included_type
        if language:
            body["languageCode"] = language
        if region:
            body["regionCode"] = region
        if open_now:
            body["openNow"] = True
        if min_rating:
            body["minRating"] = float(min_rating)

        collected: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(MAX_PAGES):
            if token:
                body["pageToken"] = token
            try:
                data = self._request("POST", PLACES_SEARCH_URL, sku=self.sku,
                                     json=body, headers=headers)
            except PlacesError as exc:
                # Nor should a field Google has renamed: drop the optional ones
                # and ask again with the mask we know it accepts.
                trimmed = ",".join(f for f in self.field_mask.split(",")
                                   if f in CORE_FIELD_MASK.split(","))
                if headers["X-Goog-FieldMask"] != trimmed and "field" in str(exc).lower():
                    headers["X-Goog-FieldMask"] = trimmed
                    if on_warn:
                        on_warn("Google rejected part of the field mask — "
                                "retrying without priceRange / openingDate / "
                                "googleMapsLinks")
                    data = self._request("POST", PLACES_SEARCH_URL, sku=self.sku,
                                         json=body, headers=headers)
                # An unrecognised type id shouldn't kill the run: drop the filter
                # and fall back to a plain text search.
                elif "includedType" in body and "includedtype" in str(exc).lower():
                    bad = body.pop("includedType")
                    if on_warn:
                        on_warn(f"type {bad!r} not accepted by the API — "
                                "falling back to text search")
                    data = self._request("POST", PLACES_SEARCH_URL, sku=self.sku,
                                         json=body, headers=headers)
                else:
                    raise
            collected.extend(data.get("places") or [])
            token = data.get("nextPageToken")
            if not token or len(collected) >= limit:
                break
        return collected
