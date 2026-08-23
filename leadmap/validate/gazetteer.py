#!/usr/bin/env python3
"""
Offline check that a location is a real place, before we pay Google to tell us.

Three open datasets, all on disk — nothing here touches the network:

    continents, countries, cities   geonamescache  (GeoNames, CC BY 4.0)
    states / provinces / regions    pycountry      (ISO 3166-2)
    postal codes                    data/postal_codes.py (GeoNames, CC BY 4.0)

A location passes if any part of it is a place one of those knows: a city, a
state, a country, a continent or a postal code. That is deliberately generous —
"Baner, Pune" passes on Pune, and a street address passes on its city — because
the point is to catch a typo, not to second-guess an address Google can resolve.

The one thing it is strict about is a postal code on its own: "560999, India"
fails, because India has 19,238 codes and that is not one of them.

    python -m leadmap.validate.gazetteer "Austin, TX" "560001" "asdkjh"
    python -m leadmap.validate.gazetteer --stats
"""

from __future__ import annotations

import base64
import difflib
import marshal
import re
import sys
import threading
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

CACHE_VERSION = 1
CACHE_DIR = Path.home() / ".cache" / "leadmap"

# Tokens shorter than this only count when they are an uppercase code (TX, IN):
# without that rule "in" inside an address would quietly match India.
MIN_NAME = 3
MAX_WORDS = 4          # longest city name we try to match, in words
MAX_CANDIDATES = 8     # countries whose codes we decode for a bare postal code


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Match:
    kind: str            # continent | country | state | city | postcode
    text: str            # what the user typed
    detail: str = ""     # country code it belongs to, when we know one

    def __str__(self) -> str:
        return f"{self.kind} {self.text}" + (f" ({self.detail})" if self.detail else "")


@dataclass
class Verdict:
    location: str
    matches: list[Match] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)   # recognised, but one word looks off
    notes: list[str] = field(default_factory=list)   # recognised, worth mentioning

    @property
    def ok(self) -> bool:
        return bool(self.matches) and not self.problems

    def summary(self) -> str:
        """'city Austin · state TX' — what the check actually recognised."""
        seen, parts = set(), []
        for match in self.matches:
            label = f"{match.kind} {match.text}"
            if label not in seen:
                seen.add(label)
                parts.append(label)
        return " · ".join(parts)

    def reason(self) -> str:
        if self.problems:
            return self.problems[0]
        return f"I don't know any place in “{self.location}”"


# ---------------------------------------------------------------------------
# Normalising
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def fold(text: str) -> str:
    """Lower-case, strip accents and punctuation: 'Kolhāpur' → 'kolhapur'."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _SPACES.sub(" ", _PUNCT.sub(" ", stripped)).strip()


# ---------------------------------------------------------------------------
# The indexes
# ---------------------------------------------------------------------------

class Index:
    """Folded place names, built once and cached on disk between runs."""

    available = True     # False when the datasets aren't installed

    def __init__(self) -> None:
        self.cities: set[str] = set()
        self.countries: dict[str, str] = {}        # folded name → ISO2
        self.country_codes: dict[str, str] = {}    # ISO2 / ISO3 → ISO2
        self.country_names: dict[str, str] = {}    # ISO2 → display name
        self.states: dict[str, str] = {}           # folded name → ISO2
        self.state_codes: dict[str, str] = {}      # subdivision code → ISO2
        self.continents: set[str] = set()
        self.postal_formats: list[tuple[str, str]] = []   # (ISO2, regex), big countries first

    # -- construction --------------------------------------------------------
    @classmethod
    def build(cls) -> "Index":
        import geonamescache
        import pycountry

        cache = geonamescache.GeonamesCache()
        index = cls()

        for code, continent in cache.get_continents().items():
            index.continents.add(fold(continent["name"]))

        countries = cache.get_countries()
        for iso2, country in countries.items():
            index.countries[fold(country["name"])] = iso2
            index.country_codes[iso2] = iso2
            index.country_codes[country["iso3"]] = iso2
            index.country_names[iso2] = country["name"]
        for entry in pycountry.countries:                  # common/official names
            iso2 = entry.alpha_2
            for attribute in ("name", "common_name", "official_name"):
                name = getattr(entry, attribute, None)
                if name:
                    index.countries.setdefault(fold(name), iso2)

        for subdivision in pycountry.subdivisions:
            iso2 = subdivision.country_code
            index.states.setdefault(fold(subdivision.name), iso2)
            index.state_codes.setdefault(subdivision.code.split("-", 1)[-1], iso2)
        for state in cache.get_us_states().values():       # 'CA' → California
            index.states.setdefault(fold(state["name"]), "US")

        for city in cache.get_cities().values():
            index.cities.add(fold(city["name"]))
            for alternate in city.get("alternatenames") or ():
                index.cities.add(fold(alternate))
        index.cities.discard("")

        formats = []
        for iso2, country in countries.items():
            pattern = (country.get("postalcoderegex") or "").strip()
            if pattern:
                formats.append((iso2, pattern, country.get("population") or 0))
        formats.sort(key=lambda item: -item[2])
        index.postal_formats = [(iso2, pattern) for iso2, pattern, _ in formats]
        return index

    # -- disk cache ----------------------------------------------------------
    @property
    def _fields(self) -> tuple:
        return (self.cities, self.countries, self.country_codes, self.country_names,
                self.states, self.state_codes, self.continents, self.postal_formats)

    @staticmethod
    def _cache_path() -> Path:
        return CACHE_DIR / f"gazetteer-v{CACHE_VERSION}.marshal"

    @classmethod
    def load(cls) -> "Index":
        """From the cache when it's there, otherwise built and then cached."""
        path = cls._cache_path()
        try:
            with path.open("rb") as handle:
                data = marshal.load(handle)
            index = cls()
            (index.cities, index.countries, index.country_codes, index.country_names,
             index.states, index.state_codes, index.continents,
             index.postal_formats) = data
            index.cities = set(index.cities)
            index.continents = set(index.continents)
            index.postal_formats = [tuple(pair) for pair in index.postal_formats]
            return index
        except Exception:                                   # noqa: BLE001 — any miss rebuilds
            pass

        index = cls.build()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                marshal.dump(tuple(index._fields), handle)
        except OSError:
            pass                                            # a read-only home is fine
        return index


_index: Optional[Index] = None
_lock = threading.Lock()


def warm() -> Index:
    """Build (or load) the indexes. Safe to call from a background thread."""
    global _index
    with _lock:
        if _index is None:
            try:
                _index = Index.load()
            except ImportError:          # datasets not installed — check nothing
                _index = Index()
                _index.available = False
        return _index


# ---------------------------------------------------------------------------
# Postal codes
# ---------------------------------------------------------------------------

_postal_cache: dict[str, frozenset[str]] = {}


def postal_codes(country: str) -> frozenset[str]:
    """Every postal code for one country, decoded from postal_data.py."""
    country = country.upper()
    if country not in _postal_cache:
        try:
            from .data import postal_codes as postal_data
        except ImportError:
            return frozenset()
        blob = postal_data.CODES.get(country)
        if blob is None:
            _postal_cache[country] = frozenset()
        else:
            raw = zlib.decompress(base64.b85decode(blob)).decode()
            codes, previous = [], ""
            for line in raw.split("\n"):
                code = previous[:ord(line[0]) - 48] + line[1:]
                codes.append(code)
                previous = code
            _postal_cache[country] = frozenset(codes)
    return _postal_cache[country]


def has_postal_data(country: str) -> bool:
    try:
        from .data import postal_codes as postal_data
    except ImportError:                  # generated file missing: format only
        return False
    return country.upper() in postal_data.CODES


def _format_matches(token: str, index: Index) -> list[str]:
    """Countries whose postal code format the token could be, biggest first."""
    out = []
    for iso2, pattern in index.postal_formats:
        try:
            if re.fullmatch(pattern.strip("^$"), token, re.IGNORECASE):
                out.append(iso2)
        except re.error:
            continue
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

_SPLIT = re.compile(r"[,;/|]+")


def _name_match(folded: str, raw: str, index: Index,
                standalone: bool = True) -> Optional[Match]:
    """Is this run of words a place we know?

    `standalone` says the run is a whole comma-separated part. Two-letter codes
    only count there: 'NW' in "Pennsylvania Avenue NW" is a compass point, not
    South Africa's North West province.
    """
    if not folded:
        return None
    if len(folded) < MIN_NAME:
        code = raw.strip().upper()
        if standalone and raw.strip().isupper():
            if code in index.country_codes:
                return Match("country", raw.strip(), index.country_codes[code])
            if code in index.state_codes:
                return Match("state", raw.strip(), index.state_codes[code])
        return None
    upper = raw.strip().upper()
    written_as_code = standalone and raw.strip().isupper()
    if folded in index.continents:
        return Match("continent", raw.strip())
    if folded in index.countries:
        return Match("country", raw.strip(), index.countries[folded])
    # ISO codes before city names: 'USA' is also a village in Japan, and
    # someone typing it in capitals means the country.
    if written_as_code and upper in index.country_codes:
        return Match("country", raw.strip(), index.country_codes[upper])
    # City before state: a bare "Paris" or "Tokyo" is nearly always the city,
    # even though both are also ISO subdivisions. If the name is a subdivision
    # too, borrow its country as the hint for any postal code alongside it.
    if folded in index.cities:
        return Match("city", raw.strip(), index.states.get(folded, ""))
    if folded in index.states:
        return Match("state", raw.strip(), index.states[folded])
    if written_as_code and upper in index.state_codes:
        return Match("state", raw.strip(), index.state_codes[upper])
    return None


def _windows(words: list[str]) -> Iterable[tuple[int, int]]:
    """Word spans, longest first: 'new york city' before 'new york' before 'new'."""
    for size in range(min(MAX_WORDS, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            yield start, start + size


def _scan(part: str, index: Index) -> list[Match]:
    """Every place name inside one comma-separated part of the input."""
    whole = _name_match(fold(part), part, index)
    if whole:
        return [whole]

    words = [word for word in part.split() if word]
    taken: set[int] = set()
    found: list[Match] = []
    for start, end in _windows(words):
        if taken.intersection(range(start, end)):
            continue
        piece = " ".join(words[start:end])
        match = _name_match(fold(piece), piece, index, standalone=False)
        if match:
            found.append(match)
            taken.update(range(start, end))
    return found


def _code_shaped(part: str) -> bool:
    """'560001' or 'SW1A 1AA' — short enough to be a postal code and nothing else."""
    compact = part.strip()
    return bool(compact) and len(compact) <= 12 and len(compact.split()) <= 2


def _postal_scan(part: str, index: Index,
                 country: Optional[str]) -> tuple[list[Match], list[str]]:
    """Postal codes in one part, and complaints about ones that don't exist."""
    matches: list[Match] = []
    problems: list[str] = []
    alone = _code_shaped(part)
    tokens = ([part.strip()] if alone
              else [w for w in part.split() if any(c.isdigit() for c in w)])

    for token in tokens:
        token = token.strip().upper()
        if not token or not any(character.isdigit() for character in token):
            continue
        candidates = [country] if country else []
        if alone:                       # a bare code can belong to any country
            candidates += [c for c in _format_matches(token, index) if c != country]
        elif not country:
            candidates = _format_matches(token, index)
        if not candidates:
            continue

        checked = []
        for iso2 in candidates[:MAX_CANDIDATES]:
            if not has_postal_data(iso2):
                continue
            checked.append(iso2)
            if token in postal_codes(iso2):
                matches.append(Match("postcode", token, iso2))
                break
        else:
            if not checked:                       # no country here has code data
                matches.append(Match("postcode", token, candidates[0]))
            elif alone and country in checked and country in _format_matches(token, index):
                name = index.country_names.get(country, country)
                problems.append(f"“{token}” is not a postal code in {name}")
    return matches, problems


def suggest(text: str, index: Index, limit: int = 3) -> list[str]:
    """Close spellings from the city / country / state names we hold."""
    folded = fold(text)
    words = folded.split()
    query = max(words, key=len) if words else folded
    if len(query) < MIN_NAME:
        return []
    pool = [name for name in index.cities
            if name[:1] == query[:1] and abs(len(name) - len(query)) <= 3]
    pool += [name for name in list(index.countries) + list(index.states)
             if name[:1] == query[:1]]
    close = difflib.get_close_matches(query, pool, n=limit, cutoff=0.78)
    return [name.title() for name in close]


def verify(location: str, *, region: Optional[str] = None) -> Verdict:
    """Check a location against the offline data. See the module docstring."""
    index = warm()
    verdict = Verdict(location=location)
    if not location.strip():
        verdict.problems.append("no location given")
        return verdict
    if not index.available:              # nothing installed to check against
        verdict.matches.append(Match("unchecked", location.strip()))
        return verdict

    parts = [part for part in _SPLIT.split(location) if part.strip()]
    unplaced: list[str] = []
    for part in parts:                                  # names first: they hint a country
        found = _scan(part, index)
        verdict.matches.extend(found)
        if not found:
            unplaced.append(part.strip())

    country = (region or "").upper() or None
    for match in verdict.matches:
        if match.detail:
            country = match.detail
            break

    for part in parts:
        matches, problems = _postal_scan(part, index, country)
        verdict.matches.extend(matches)
        verdict.problems.extend(problems)

    if not verdict.matches:
        verdict.suggestions = suggest(location, index)
        return verdict

    # Recognised overall, but a word we couldn't place looks like a near miss —
    # worth mentioning ("Austn, TX") without refusing to search.
    for part in unplaced:
        if len(part.split()) == 1 and len(part) >= 4 and not any(c.isdigit() for c in part):
            close = suggest(part, index, limit=2)
            if close:
                verdict.hints.append(f"“{part}” — did you mean {' or '.join(close)}?")
    return verdict


def stats() -> dict[str, int]:
    from .data import postal_codes as postal_data
    index = warm()
    return {
        "continents": len(index.continents),
        "countries": len({v for v in index.countries.values()}),
        "country names": len(index.countries),
        "states / provinces": len(index.states),
        "city names (with local spellings)": len(index.cities),
        "postal codes": postal_data.TOTAL,
        "countries with postal codes": len(postal_data.CODES),
    }


# ---------------------------------------------------------------------------
# CLI — handy for checking the data without running a search
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if argv[0] == "--stats":
        for label, value in stats().items():
            print(f"  {label:36} {value:>10,}")
        return 0
    worst = 0
    for location in argv:
        verdict = verify(location)
        if verdict.ok:
            print(f"✓ {location}  →  {verdict.summary()}")
            for hint in verdict.hints:
                print(f"  ! {hint}")
        else:
            worst = 1
            print(f"✗ {location}  →  {verdict.reason()}"
                  + (f"   did you mean: {', '.join(verdict.suggestions)}?"
                     if verdict.suggestions else ""))
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
