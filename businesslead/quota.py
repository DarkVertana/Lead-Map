#!/usr/bin/env python3
"""
Keeps Business Lead inside Google's free tier, and splits the month into days.

Since March 2025 there is no $200 credit: every Maps Platform SKU has its own
monthly allowance of free calls, and the first call past it is billed. The
allowances that matter here (checked against Google's pricing page on
2026-08-23) are:

    Geocoding                                  10,000 / month   then $5   /1k
    Text Search Essentials (IDs only)            unlimited      free
    Text Search Essentials                     10,000 / month   then $32  /1k
    Text Search Pro                             5,000 / month   then $32  /1k
    Text Search Enterprise                      1,000 / month   then $35  /1k
    Text Search Enterprise + Atmosphere         1,000 / month   then $40  /1k

A request bills at the **highest tier any field in its field mask belongs to**,
so the SKU below is worked out from FIELD_MASK itself: trim the mask and the
allowance this module enforces goes up with it.

Every call is written to a ledger (~/.local/state/businesslead/usage.json) and the
month's allowance is shared across the days left in it, so one afternoon can't
eat the month. Nothing is spent once a day's share is gone.

    businesslead --usage             # what's left today and this month
    businesslead --usage --verbose   # a day-by-day record of the current month

Both budgets can be moved: --daily-cap / --monthly-cap for one run, or
BUSINESSLEAD_DAILY_CAP / BUSINESSLEAD_MONTHLY_CAP in .env to make it standing policy.
The caps govern searches; Geocoding keeps its own 10,000/month allowance.

The ledger only knows about calls made through this machine. If the same key is
used elsewhere, set a hard cap in the Google Cloud console too.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import PlacesError
from .paths import FileLock, env, set_aside, state_dir, write_json_atomic

LEDGER_VERSION = 1
KEEP_DAYS = 400

# The caps can live in .env as well as on the command line. BUSINESSLEAD_ is the
# primary name (they govern spend, not one search); PLACES_ is accepted the
# same way PLACES_PLAN is.
ENV_DAILY_CAP = ("BUSINESSLEAD_DAILY_CAP", "PLACES_DAILY_CAP", "LEADMAP_DAILY_CAP")
ENV_MONTHLY_CAP = ("BUSINESSLEAD_MONTHLY_CAP", "PLACES_MONTHLY_CAP",
                   "LEADMAP_MONTHLY_CAP")


def parse_cap(label: str, raw) -> int:
    """A cap from a flag or .env: a whole number of calls, at least 1.

    Zero used to silently mean "use the default" (0 is falsy), so nobody can be
    relying on it — it is rejected rather than given a new meaning.
    """
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise PlacesError(f"{label} must be a whole number of calls, "
                          f"not {raw!r}") from None
    if value < 1:
        raise PlacesError(f"{label} must be at least 1 — "
                          "to spend nothing, just don't search")
    return value


def cap_from_env(names: tuple[str, ...]) -> tuple[Optional[int], str]:
    """(value, variable name) for the first of `names` that is set, parsed."""
    for name in names:
        raw = os.environ.get(name, "").strip()
        if raw:
            return parse_cap(name, raw), name
    return None, ""


def human_date(day: dt.date) -> str:
    """Dates are for reading: '01 Sep 2026', never 2026-09-01."""
    return day.strftime("%d %b %Y")


class QuotaExceeded(RuntimeError):
    """The free allowance for today (or the month) is used up."""


# ---------------------------------------------------------------------------
# What Google charges for
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sku:
    key: str                 # our own short name, used in the ledger
    label: str               # Google's name for it
    free_per_month: int
    price_per_1000: float

    def cost_of(self, calls: int) -> float:
        return max(0, calls - self.free_per_month) * self.price_per_1000 / 1000


GEOCODING = Sku("geocoding", "Geocoding", 10_000, 5.00)

TEXT_SEARCH = {
    "ids": Sku("text_ids", "Text Search Essentials (IDs Only)", 0, 0.0),
    "essentials": Sku("text_essentials", "Text Search Essentials", 10_000, 32.00),
    "pro": Sku("text_pro", "Text Search Pro", 5_000, 32.00),
    "enterprise": Sku("text_enterprise", "Text Search Enterprise", 1_000, 35.00),
    "atmosphere": Sku("text_atmosphere", "Text Search Enterprise + Atmosphere",
                      1_000, 40.00),
}
TIER_ORDER = ["ids", "essentials", "pro", "enterprise", "atmosphere"]

# Which tier each place field belongs to. Anything unlisted counts as Essentials.
FIELD_TIERS = {
    "pro": {
        "displayName", "primaryType", "primaryTypeDisplayName", "businessStatus",
        "googleMapsUri", "googleMapsLinks", "timeZone", "utcOffsetMinutes",
        "openingDate", "containingPlaces", "entrances", "navigationPoints",
        "subDestinations", "iconBackgroundColor", "iconMaskBaseUri",
    },
    "enterprise": {
        "nationalPhoneNumber", "internationalPhoneNumber", "websiteUri",
        "regularOpeningHours", "currentOpeningHours", "rating", "userRatingCount",
        "priceLevel", "priceRange", "paymentOptions", "parkingOptions",
        "accessibilityOptions", "fuelOptions", "evChargeOptions",
    },
    "atmosphere": {
        "editorialSummary", "reviews", "servesBeer", "servesBreakfast",
        "servesBrunch", "servesCocktails", "servesCoffee", "servesDessert",
        "servesDinner", "servesLunch", "servesVegetarianFood", "servesWine",
        "takeout", "delivery", "dineIn", "curbsidePickup", "reservable",
        "outdoorSeating", "liveMusic", "menuForChildren", "goodForChildren",
        "goodForGroups", "goodForWatchingSports", "allowsDogs", "restroom",
    },
}
ID_ONLY = {"id", "name", "nextPageToken", "attributions"}


def tier_of(field: str) -> str:
    """Which SKU tier one place field belongs to."""
    name = field.strip().split(".")[-1]
    if name in ID_ONLY:
        return "ids"
    for tier in ("atmosphere", "enterprise", "pro"):
        if name in FIELD_TIERS[tier]:
            return tier
    return "essentials"


def sku_for_tier(tier: str) -> Sku:
    return TEXT_SEARCH[tier]


def sku_for_mask(field_mask: str) -> Sku:
    """The SKU a request with this field mask bills at: the highest tier in it."""
    fields = [f.strip().split(".")[-1] for f in field_mask.split(",") if f.strip()]
    tier = "ids" if all(f in ID_ONLY for f in fields) else "essentials"
    for field in fields:
        for name in ("pro", "enterprise", "atmosphere"):
            if field in FIELD_TIERS[name] and TIER_ORDER.index(name) > TIER_ORDER.index(tier):
                tier = name
    return TEXT_SEARCH[tier]


def cheaper_masks(field_mask: str) -> list[tuple[Sku, list[str]]]:
    """What you'd have to drop to reach a bigger free allowance, tier by tier."""
    fields = [f.strip().split(".")[-1] for f in field_mask.split(",") if f.strip()]
    current = sku_for_mask(field_mask)
    out = []
    for tier in reversed(TIER_ORDER[:TIER_ORDER.index(
            next(k for k, v in TEXT_SEARCH.items() if v is current))]):
        if tier == "ids":
            continue
        above = [f for f in fields
                 for name in ("pro", "enterprise", "atmosphere")
                 if f in FIELD_TIERS[name]
                 and TIER_ORDER.index(name) > TIER_ORDER.index(tier)]
        if above and TEXT_SEARCH[tier].free_per_month > current.free_per_month:
            out.append((TEXT_SEARCH[tier], sorted(set(above))))
    return out


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------

def default_ledger_path() -> Path:
    override = env("USAGE_FILE")
    if override:
        return Path(override).expanduser()
    return state_dir() / "usage.json"


@dataclass
class Status:
    sku: Sku
    used_today: int
    used_month: int
    allowance_today: int
    month: str          # 'Aug 2026'
    monthly_free: int = 0    # the month's effective ceiling: the SKU's, or a cap

    def __post_init__(self) -> None:
        if not self.monthly_free:
            self.monthly_free = self.sku.free_per_month

    @property
    def left_month(self) -> int:
        return max(0, self.monthly_free - self.used_month)

    @property
    def left_today(self) -> int:
        return max(0, min(self.allowance_today - self.used_today, self.left_month))

    @property
    def unlimited(self) -> bool:
        return self.sku.free_per_month == 0 and self.sku.price_per_1000 == 0

    def line(self) -> str:
        if self.unlimited:
            return f"{self.sku.label}: free, unmetered"
        return (f"{self.left_today:,} left today · "
                f"{self.left_month:,} of {self.monthly_free:,} left this month")


class Quota:
    """Reads and writes the usage ledger, and decides what today may spend."""

    def __init__(self, path: Optional[Path] = None, *, daily_cap: Optional[int] = None,
                 monthly_cap: Optional[int] = None, today: Optional[dt.date] = None):
        self.path = Path(path) if path else default_ledger_path()
        self.daily_cap = daily_cap
        self.monthly_cap = monthly_cap
        self._today = today                # tests pin a date; live runs never do
        self.data = self._read()
        # What the file held when it was read: save() writes disk + (now − this),
        # so two runs at once each add their own spending instead of the later
        # one erasing the earlier one's.
        self._baseline = {day: dict(counts)
                          for day, counts in self.data["days"].items()}
        self._warned = False

    @property
    def today(self) -> dt.date:
        """The real date, every time it's asked — a sweep that crosses midnight
        books its later calls to the new day, the way Google's meter does."""
        return self._today or dt.date.today()

    # -- storage -------------------------------------------------------------
    def _read(self) -> dict:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"version": LEDGER_VERSION, "days": {}}
        except OSError as exc:
            # The file exists but can't be read. Say so — this module is the
            # billing protection, and pretending the month is unspent isn't it.
            print(f"! the usage ledger at {self.path} can't be read ({exc}) — "
                  "counts may be low until that's fixed", file=sys.stderr)
            return {"version": LEDGER_VERSION, "days": {}}
        try:
            data = json.loads(raw)
        except ValueError:
            set_aside(self.path, self.today)     # a year of usage, kept aside
            return {"version": LEDGER_VERSION, "days": {}}
        if isinstance(data, dict) and data.get("version") == LEDGER_VERSION:
            return data
        set_aside(self.path, self.today)
        return {"version": LEDGER_VERSION, "days": {}}

    def _merged_days(self, disk_days: dict) -> dict[str, dict]:
        """What's on disk now, plus what this process spent since it loaded."""
        merged = {day: {key: int(count) for key, count in counts.items()}
                  for day, counts in disk_days.items() if isinstance(counts, dict)}
        for day in set(self.data["days"]) | set(self._baseline):
            now = self.data["days"].get(day, {})
            before = self._baseline.get(day, {})
            for key in set(now) | set(before):
                delta = int(now.get(key, 0)) - int(before.get(key, 0))
                if not delta:
                    continue
                counts = merged.setdefault(day, {})
                counts[key] = max(0, int(counts.get(key, 0)) + delta)
        return {day: {key: count for key, count in counts.items() if count}
                for day, counts in merged.items() if any(counts.values())}

    def save(self) -> None:
        cutoff = (self.today - dt.timedelta(days=KEEP_DAYS)).isoformat()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(self.path.with_name(self.path.name + ".lock")):
                try:
                    raw = self.path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    raw = ""
                # any other read error propagates: better not to write at all
                # than to overwrite a ledger we couldn't read
                disk_days: dict = {}
                if raw:
                    try:
                        on_disk = json.loads(raw)
                    except ValueError:
                        set_aside(self.path, self.today)   # keep the evidence
                    else:
                        if (isinstance(on_disk, dict)
                                and on_disk.get("version") == LEDGER_VERSION
                                and isinstance(on_disk.get("days"), dict)):
                            disk_days = on_disk["days"]
                days = {day: counts
                        for day, counts in self._merged_days(disk_days).items()
                        if day >= cutoff}
                self.data = {"version": LEDGER_VERSION, "days": days}
                write_json_atomic(self.path, self.data, indent=1, sort_keys=True)
            self._baseline = {day: dict(counts) for day, counts in days.items()}
        except OSError as exc:
            if not self._warned:      # once is a warning, every save is noise
                self._warned = True
                print(f"! couldn't write the usage ledger at {self.path} ({exc}) "
                      "— calls made now may not be counted against the free tier",
                      file=sys.stderr)

    # -- counting ------------------------------------------------------------
    def used_on(self, sku: Sku, day: dt.date) -> int:
        return int(self.data["days"].get(day.isoformat(), {}).get(sku.key, 0))

    def used_in_month(self, sku: Sku, month: Optional[str] = None) -> int:
        prefix = month or self.today.strftime("%Y-%m")
        return sum(int(counts.get(sku.key, 0))
                   for day, counts in self.data["days"].items()
                   if day.startswith(prefix))

    def record(self, sku: Sku, calls: int = 1) -> None:
        day = self.data["days"].setdefault(self.today.isoformat(), {})
        day[sku.key] = max(0, int(day.get(sku.key, 0)) + calls)

    # -- budgets -------------------------------------------------------------
    def _capped(self, sku: Sku) -> bool:
        """The caps govern searches. Geocoding keeps Google's own allowance —
        one number in .env shouldn't quietly throttle a 10,000-call SKU."""
        return sku.key != GEOCODING.key

    def monthly_free(self, sku: Sku) -> int:
        """The month's ceiling for this SKU: Google's, unless a cap says
        otherwise — lower to stay safer, higher if Google changes its tier."""
        if self.monthly_cap is not None and self._capped(sku):
            return self.monthly_cap
        return sku.free_per_month

    def allowance_today(self, sku: Sku) -> int:
        """The most today may spend in total — not what it has left to spend.

        This month's remaining free calls, shared over the days left in it.
        Unused days carry forward — sit out a week and the daily share grows —
        but the month's total is never exceeded.
        """
        if sku.free_per_month == 0:
            return 10 ** 9                                    # unmetered SKU
        left = max(0, self.monthly_free(sku) - self.used_in_month(sku))
        if not left:
            return 0
        days_in_month = calendar.monthrange(self.today.year, self.today.month)[1]
        days_left = days_in_month - self.today.day + 1
        share = max(1, left // max(1, days_left))
        if self.daily_cap is not None and self._capped(sku):
            share = self.daily_cap
        # The ceiling is what the month can still afford *plus what today has
        # already spent*, because `left` counts today's calls as gone and this
        # is today's whole budget, not the rest of it. Clamping to `left` alone
        # subtracted them twice — Status.left_today takes them off again — so a
        # day that had spent the month's whole remainder could never be raised:
        # /borrow said "borrowed 40" and left you with nought.
        return min(share, left + self.used_on(sku, self.today))

    def status(self, sku: Sku) -> Status:
        return Status(sku=sku, used_today=self.used_on(sku, self.today),
                      used_month=self.used_in_month(sku),
                      allowance_today=self.allowance_today(sku),
                      month=self.month_name(),
                      monthly_free=self.monthly_free(sku))

    def left_today(self, sku: Sku) -> int:
        if sku.free_per_month == 0:
            return 10 ** 9
        return self.status(sku).left_today

    def take(self, sku: Sku, calls: int = 1) -> None:
        """Spend from today's share, or refuse. Callers should catch this."""
        if sku.free_per_month == 0:
            return
        if self.left_today(sku) < calls:
            status = self.status(sku)
            if status.left_month <= 0:
                message = (
                    f"the {status.monthly_free:,} free {sku.label} calls for "
                    f"{self.month_name()} are used up — the allowance resets on "
                    f"{human_date(self.next_month())}")
                if status.monthly_free != sku.free_per_month:
                    message += (" (a monthly cap set that ceiling — raise it to "
                                "keep going)")
                raise QuotaExceeded(message)
            raise QuotaExceeded(
                f"today's share of the free tier is used up "
                f"({status.used_today:,} of {status.allowance_today:,} "
                f"{sku.label} calls) — {status.left_month:,} left this month, "
                f"back tomorrow or use --daily-cap (BUSINESSLEAD_DAILY_CAP in .env) "
                "to borrow from it")
        self.record(sku, calls)

    def month_name(self) -> str:
        return self.today.strftime("%b %Y")

    def reset_today(self, *skus: Sku) -> dict[str, int]:
        """Zero today's counters and return what they were.

        This only clears Business Lead's own bookkeeping — Google's meter is untouched,
        so the calls it forgets have still been spent. For development.
        """
        day = self.data["days"].get(self.today.isoformat(), {})
        wanted = [sku.key for sku in skus] if skus else list(day)
        cleared = {key: int(day.get(key, 0)) for key in wanted if day.get(key)}
        for key in wanted:
            day.pop(key, None)
        if not day:
            self.data["days"].pop(self.today.isoformat(), None)
        self.save()
        return cleared

    def next_month(self) -> dt.date:
        year, month = self.today.year, self.today.month
        return dt.date(year + (month == 12), 1 if month == 12 else month + 1, 1)

    # -- reporting -----------------------------------------------------------
    def recent(self, sku: Sku, days: int = 7) -> list[tuple[dt.date, int]]:
        """The last `days` days, oldest first, each with what it spent."""
        span = [self.today - dt.timedelta(days=offset)
                for offset in reversed(range(days))]
        return [(day, self.used_on(sku, day)) for day in span]

    def month_rows(self, sku: Sku, month: Optional[str] = None
                   ) -> list[tuple[str, int]]:
        prefix = month or self.today.strftime("%Y-%m")
        return sorted((day, int(counts.get(sku.key, 0)))
                      for day, counts in self.data["days"].items()
                      if day.startswith(prefix) and counts.get(sku.key))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str], daily_cap: Optional[int] = None,
         monthly_cap: Optional[int] = None) -> int:
    from .constants import FIELD_MASK                # the live mask

    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0

    # The caps the flags didn't set can still come from .env / the environment,
    # so --usage reports the same numbers a search would enforce.
    try:
        daily_source = "--daily-cap" if daily_cap is not None else ""
        monthly_source = "--monthly-cap" if monthly_cap is not None else ""
        if daily_cap is None:
            daily_cap, daily_source = cap_from_env(ENV_DAILY_CAP)
        if monthly_cap is None:
            monthly_cap, monthly_source = cap_from_env(ENV_MONTHLY_CAP)
    except PlacesError as exc:
        print(f"  ! {exc}")
        return 1

    quota = Quota(daily_cap=daily_cap, monthly_cap=monthly_cap)
    search = sku_for_mask(FIELD_MASK)
    print(f"  ledger  {quota.path}")
    print(f"  billed as  {search.label}"
          f"  ({search.free_per_month:,} free/month, then ${search.price_per_1000:.0f}/1k)")
    caps = [f"{kind} {value:,} ({source})" for kind, value, source
            in (("daily", daily_cap, daily_source),
                ("monthly", monthly_cap, monthly_source))
            if value is not None]
    if caps:
        print(f"  capped  {' · '.join(caps)}")
    print()
    quota_month = quota.month_name()
    # every SKU with usage this month, plus the one we'd bill at right now:
    # switching plans moves you between separate allowances, not one shared pot.
    skus = [search] + [sku for sku in list(TEXT_SEARCH.values()) + [GEOCODING]
                       if sku.key != search.key and quota.used_in_month(sku)]
    if GEOCODING not in skus:
        skus.append(GEOCODING)
    for sku in skus:
        status = quota.status(sku)
        print(f"  {sku.label}")
        print(f"    {'today':<9}{status.used_today:>6,} used   "
              f"{status.left_today:>6,} left")
        print(f"    {quota_month:<9}{status.used_month:>6,} used   "
              f"{status.left_month:>6,} left of {status.monthly_free:,}")
    if argv and argv[0] == "--month":
        print(f"\n  day by day ({quota.month_name()})")
        for day, calls in quota.month_rows(search):
            shown = dt.date.fromisoformat(day).strftime("%d %b")
            print(f"    {shown}  {calls:>5,}  {'▰' * min(40, calls)}")
    savings = cheaper_masks(FIELD_MASK)
    if savings:
        print("\n  a bigger free allowance would mean giving up fields:")
        for sku, fields in savings:
            print(f"    {sku.free_per_month:>6,}/month as {sku.label}"
                  f" — drop {', '.join(fields[:6])}"
                  + (" …" if len(fields) > 6 else ""))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
