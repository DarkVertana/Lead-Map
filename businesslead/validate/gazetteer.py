#!/usr/bin/env python3
"""
Offline check that a location is a real place, before we pay Google to tell us.

Two files on disk, nothing over the network:

    countries.json          every country, state and city, in the project root
    data/postal_codes.py    1.08M postal codes (GeoNames, CC BY 4.0)

countries.json is the data, not a copy of it — correct a name in it and the next
run uses the correction. The cached index is stamped with the file's size and
mtime, so an edit rebuilds it without anything being cleared by hand, and a file
that won't parse says which line and falls back to the packages it was made from.
Regenerate it from GeoNames with tools/build_countries.py.

A location has to name a country — "Delhi" is in three of them and Google would
geocode a bare one to whichever it liked. Everything else is optional, and beyond
that the check is deliberately generous: "Baner, Pune, India" passes on Pune, and
a street address passes on its city, because the point is to catch a typo rather
than second-guess an address Google can resolve.

The one thing it is strict about is a postal code on its own: "560999, India"
fails, because India has 19,238 codes and that is not one of them.

Two ways to change what counts as a real place:

    countries.json      the data itself. Fix a spelling, add a city, delete a
                        wrong entry. Regenerating it overwrites your edits.
    locations.txt       your own additions, kept apart so regenerating never
                        touches them. `--locations` prints the path.

PLACES_EXTRA_LOCATIONS still works for a quick one-off in .env.

    python -m businesslead.validate.gazetteer "Austin, TX, USA" "560001, India" "asdkjh"
    python -m businesslead.validate.gazetteer --locations
    python -m businesslead.validate.gazetteer --stats
"""

from __future__ import annotations

import base64
import difflib
import json
import marshal
import os
import re
import sys
import threading
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

CACHE_VERSION = 1

# Tokens shorter than this only count when they are an uppercase code (TX, IN):
# without that rule "in" inside an address would quietly match India.
MIN_NAME = 3
MAX_WORDS = 4          # longest city name we try to match, in words
MAX_CANDIDATES = 8     # countries whose codes we decode for a bare postal code

# Where you name places the shipped data doesn't know. Read from the environment
# (so .env carries it), never from the cached index — see extras().
EXTRA_ENV = ("PLACES_EXTRA_LOCATIONS", "BUSINESSLEAD_EXTRA_LOCATIONS",
             "LEADMAP_EXTRA_LOCATIONS")


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
# countries.json — the data itself
# ---------------------------------------------------------------------------

COUNTRIES_NAME = "countries.json"
COUNTRIES_ENV = ("BUSINESSLEAD_COUNTRIES_FILE", "PLACES_COUNTRIES_FILE")


def countries_path() -> Optional[Path]:
    """The countries.json this run reads, or None to fall back to the packages.

    Looked for where you would put it: named in the environment, in the
    directory you are running from, then in the project root — which is where
    the shipped one lives, and where an editable install still finds it.
    """
    override = next((os.environ[name] for name in COUNTRIES_ENV
                     if os.environ.get(name)), "")
    if override:
        path = Path(override).expanduser()
        return path if path.exists() else None
    candidates = []
    try:
        candidates.append(Path.cwd() / COUNTRIES_NAME)
    except OSError:
        pass                                       # cwd deleted: the others remain
    here = Path(__file__).resolve()
    candidates += [here.parents[2] / COUNTRIES_NAME,     # a checkout, or -e install
                   here.parent / "data" / COUNTRIES_NAME]  # shipped in the wheel
    return next((path for path in candidates if path.exists()), None)


def _source_stamp() -> tuple:
    """What the cached index was built from — its name, size and mtime.

    Held in the cache file so that editing countries.json rebuilds the index on
    the very next run. Without it a corrected name would sit there unused until
    something else happened to invalidate a cache measured in weeks.
    """
    path = countries_path()
    if path is None:
        return ("packages", CACHE_VERSION)
    try:
        info = path.stat()
        return (str(path), info.st_size, info.st_mtime_ns)
    except OSError:
        return (str(path), None, None)


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
        """From countries.json where there is one, from the packages otherwise."""
        path = countries_path()
        if path is not None:
            try:
                return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                # A file someone is midway through editing must not take the
                # checker down with it: say so once, and fall back to the data
                # the packages carry, which is what the file was made from.
                print(f"  ! {path.name} couldn't be read ({exc}) — using the "
                      f"packaged data for now", file=sys.stderr)
        return cls.from_packages()

    @classmethod
    def from_json(cls, data: dict) -> "Index":
        """Build the index from countries.json. See tools/build_countries.py."""
        index = cls()
        index.continents = {fold(name) for name in data.get("continents") or ()}

        ordered = []
        for country in data["countries"]:
            iso2 = country["code"]
            index.country_names[iso2] = country["name"]
            index.country_codes[iso2] = iso2
            if country.get("iso3"):
                index.country_codes[country["iso3"]] = iso2
            for name in (country["name"], *(country.get("also") or ())):
                index.countries.setdefault(fold(name), iso2)
            if country.get("postal"):
                ordered.append((iso2, country["postal"], country.get("population") or 0))
        ordered.sort(key=lambda item: -item[2])
        index.postal_formats = [(iso2, pattern) for iso2, pattern, _ in ordered]

        for iso2, rows in (data.get("states") or {}).items():
            for code, name in rows:
                index.states.setdefault(fold(name), iso2)
                index.state_codes.setdefault(code, iso2)

        for rows in (data.get("cities") or {}).values():
            for row in rows:
                index.cities.update(fold(name) for name in row)
        index.cities.discard("")
        return index

    @classmethod
    def from_packages(cls) -> "Index":
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
        from ..paths import cache_dir          # lazy: keeps this module standalone
        return cache_dir() / f"gazetteer-v{CACHE_VERSION}.marshal"

    @classmethod
    def load(cls) -> "Index":
        """From the cache when it's still current, otherwise built and cached."""
        path = cls._cache_path()
        stamp = _source_stamp()
        try:
            with path.open("rb") as handle:
                cached = marshal.load(handle)
            was, data = cached[0], cached[1:]
            if tuple(was) != stamp:               # countries.json has been edited
                raise ValueError("stale")
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
                marshal.dump((stamp, *index._fields), handle)
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
# The locations file — countries, states and cities you add by hand
# ---------------------------------------------------------------------------

# How a location is cut into parts — and how the environment separates one extra
# place name from the next.
_SPLIT = re.compile(r"[,;/|]+")

LOCATIONS_NAME = "locations.txt"
LOCATIONS_ENV = ("BUSINESSLEAD_LOCATIONS_FILE", "PLACES_LOCATIONS_FILE",
                 "LEADMAP_LOCATIONS_FILE")

# What each heading is called, and the singular and looser spellings people
# reach for. The value is the field on Locations it fills.
HEADINGS = {
    "countries": "countries", "country": "countries",
    "states": "states", "state": "states", "provinces": "states",
    "province": "states", "regions": "states", "region": "states",
    "cities": "cities", "city": "cities", "towns": "cities", "town": "cities",
    "districts": "cities", "district": "cities", "areas": "cities",
    "area": "cities", "suburbs": "cities", "suburb": "cities",
}
KINDS = ("countries", "states", "cities")
# What one entry of each becomes when it matches: the singular, as Match wants.
AS_MATCH = {"countries": "country", "states": "state", "cities": "city"}

TEMPLATE = """\
# Business Lead — places you have added by hand.
#
# The shipped data knows 252 countries, ~5,000 states and provinces and about a
# quarter of a million city names, but it does not know everything: a city that
# was renamed, a district that was only just split off, a suburb below the
# 15,000-population cut GeoNames makes. Name it here and it is a real place from
# the next run on — nothing is re-downloaded and no cache has to be rebuilt.
#
# One place per line, under the heading it belongs to. Blank lines and anything
# after a # are ignored. The heading matters: a location has to name a country,
# so a country you add here is what lets a search use it.
#
# After the name you may put a colon and the country it belongs to, as an ISO
# code or a name. That does one job — it decides whose postal codes a code
# standing next to the name is checked against.
#
#     Prayagraj:IN
#     Chhatrapati Sambhajinagar:India
#
# Delete this file to go back to the shipped data alone.

[countries]
# A country the shipped list doesn't carry, or one you would rather spell
# your own way.
# Kosovo:XK

[states]
# States, provinces, regions — anything between a country and a city.
# Telangana:IN

[cities]
# Cities, towns, districts, suburbs, neighbourhoods.
# Prayagraj:IN
# Chhatrapati Sambhajinagar:India
# Baner Gaon:IN
"""


@dataclass
class Locations:
    """The places named in the locations file, by what kind of place each is."""

    path: Optional[Path] = None
    exists: bool = False
    countries: dict[str, tuple[str, str]] = field(default_factory=dict)
    states: dict[str, tuple[str, str]] = field(default_factory=dict)
    cities: dict[str, tuple[str, str]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.countries) + len(self.states) + len(self.cities)

    def lookup(self, folded: str) -> Optional[tuple[str, str, str]]:
        """A folded name → (kind, name as written, country hint), or None.

        Countries first: the heading a name is filed under is the whole point of
        the file, and the widest one wins where somebody has listed a name twice.
        """
        for kind in KINDS:
            entry = getattr(self, kind).get(folded)
            if entry is not None:
                return AS_MATCH[kind], entry[0], entry[1]
        return None

    def names(self) -> dict[str, tuple[str, str]]:
        """Every name in the file, folded → (as written, hint) — for suggesting."""
        return {**self.cities, **self.states, **self.countries}


def parse_locations(text: str) -> Locations:
    """The text of a locations file → the places it names.

    A line before any heading is taken as a city, which is what someone who
    pastes a bare list of place names into the file almost always means.
    """
    found = Locations()
    kind = "cities"
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            heading = line[1:-1].strip().lower()
            if heading not in HEADINGS:
                found.problems.append(
                    f"line {number}: [{heading}] isn't a heading I know — "
                    f"use {', '.join('[' + k + ']' for k in KINDS)}")
                continue                    # keep filing under the last good one
            kind = HEADINGS[heading]
            continue
        name, _, hint = line.partition(":")
        name, folded = name.strip(), fold(name)
        if not folded:
            found.problems.append(f"line {number}: no name in {line!r}")
            continue
        getattr(found, kind)[folded] = (name, hint.strip())
    return found


def locations_path() -> Path:
    """The locations file this run reads.

    Looked for beside the .env you are already editing, so a project can carry
    its own list, then in the config directory, so a machine can have one that
    every project sees. The environment overrides both.
    """
    override = next((os.environ[name] for name in LOCATIONS_ENV
                     if os.environ.get(name)), "")
    if override:
        return Path(override).expanduser()
    try:
        beside_env = Path.cwd() / LOCATIONS_NAME
        if beside_env.exists():
            return beside_env
    except OSError:
        pass          # cwd deleted or unreadable: the config directory still is
    from ..paths import config_dir
    return config_dir() / LOCATIONS_NAME


_locations: Optional[Locations] = None
_locations_stamp: Optional[tuple] = None


def custom() -> Locations:
    """The locations file, re-read whenever it changes on disk.

    Deliberately not part of the index: that is built once and cached for weeks,
    and a name you add to the file has to count on the very next run.
    """
    global _locations, _locations_stamp
    path = locations_path()
    try:
        info = path.stat()
        stamp = (str(path), info.st_mtime_ns, info.st_size)
    except OSError:
        stamp = (str(path), None, None)
    if stamp == _locations_stamp and _locations is not None:
        return _locations

    found = Locations(path=path)
    try:
        found = parse_locations(path.read_text(encoding="utf-8"))
        found.path, found.exists = path, True
    except FileNotFoundError:
        pass                                # not having one is the normal case
    except OSError as exc:
        found.problems.append(f"couldn't read {path}: {exc}")
    except UnicodeDecodeError:
        found.problems.append(f"{path} isn't UTF-8 text — save it as UTF-8")
    _locations_stamp, _locations = stamp, found
    return found


def write_template(path: Optional[Path] = None) -> Path:
    """Put the commented starter file in place. Never overwrites one."""
    path = Path(path) if path else locations_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Extra places, from the environment
# ---------------------------------------------------------------------------

_extras_raw: Optional[str] = None
_extras: dict[str, tuple[str, str]] = {}


def parse_extras(raw: str) -> dict[str, tuple[str, str]]:
    """'Prayagraj, Gurugram:IN' → folded name → (name as written, country hint).

    The `:IN` half is optional, and may be an ISO code or a country name. It
    does one job: decide whose postal codes a code standing next to the name is
    checked against.
    """
    places: dict[str, tuple[str, str]] = {}
    for entry in _SPLIT.split(raw):
        name, _, hint = entry.partition(":")
        name = name.strip()
        folded = fold(name)
        if folded:
            places[folded] = (name, hint.strip())
    return places


def extras() -> dict[str, tuple[str, str]]:
    """What PLACES_EXTRA_LOCATIONS names, re-read whenever the value changes.

    Deliberately not part of the index: that is built once and cached on disk
    for weeks, and a line added to .env has to count on the very next run.
    """
    global _extras_raw, _extras
    raw = next((os.environ[name] for name in EXTRA_ENV if os.environ.get(name)), "")
    if raw != _extras_raw:
        _extras_raw, _extras = raw, parse_extras(raw)
    return _extras


def _country_hint(text: str, index: Index) -> str:
    """'IN', 'IND' or 'India' → 'IN'. Anything unrecognised is simply dropped."""
    code = text.strip().upper()
    if not code:
        return ""
    return index.country_codes.get(code) or index.countries.get(fold(text), "")


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _name_match(folded: str, raw: str, index: Index,
                standalone: bool = True) -> Optional[Match]:
    """Is this run of words a place we know?

    `standalone` says the run is a whole comma-separated part. Two-letter codes
    only count there: 'NW' in "Pennsylvania Avenue NW" is a compass point, not
    South Africa's North West province.
    """
    if not folded:
        return None
    # Yours before ours: a name you put in the environment is a place, full stop.
    added = extras().get(folded)
    if added is not None:
        return Match("place", raw.strip(), _country_hint(added[1], index))
    # The locations file says what kind of place each name is, so a country you
    # added counts as a country — which is what lets a location built on it pass
    # the rule that one must be named.
    mine = custom().lookup(folded)
    if mine is not None:
        kind, _, hint = mine
        return Match(kind, raw.strip(), _country_hint(hint, index))
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
    added = {**custom().names(), **extras()}      # yours spelled as you wrote them
    pool = list(dict.fromkeys(pool + list(added)))   # a name held twice suggests once
    close = difflib.get_close_matches(query, pool, n=limit, cutoff=0.78)
    return [added[name][0] if name in added else name.title() for name in close]


def _needs_country(location: str, country: Optional[str], index: Index) -> str:
    """The 'name the country' problem, completed for them where we can see it.

    A part that belongs to exactly one country — a US state code, an Indian
    postcode — tells us which, so the message is the finished location rather
    than a rule to go and satisfy.
    """
    known = index.country_names.get((country or "").upper())
    if known:
        return (f"name the country — did you mean “{location.strip()}, {known}”? "
                f"(or PLACES_REGION={country.lower()} in .env, for every search)")
    return ("name the country — a city or state on its own belongs to several, "
            "and the search would land in whichever one Google picked")


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

    # The country is the one part that has to be there. A state, city, street or
    # postcode is optional — but on their own they belong to several countries,
    # and Google would geocode to whichever it liked, spending the search on an
    # area nobody asked for. PLACES_REGION names the country for every search.
    if not (any(match.kind == "country" for match in verdict.matches)
            or (region or "").upper() in index.country_codes):
        # Re-read the country off the matches: a postcode is only placed in the
        # scan above, so "560001" knows it is Indian by now even though the
        # country worked out before that scan was still None.
        seen = next((match.detail for match in verdict.matches if match.detail),
                    country)
        verdict.problems.append(_needs_country(location, seen, index))
        return verdict

    named = [match.text for match in verdict.matches if match.kind == "place"]
    if named:
        verdict.notes.append(f"“{', '.join(named)}” — a place you added in {EXTRA_ENV[0]}")

    mine = custom()
    yours = dict.fromkeys(match.text for match in verdict.matches
                          if mine.lookup(fold(match.text)) is not None)
    if yours:
        verdict.notes.append(f"“{', '.join(yours)}” — from your {LOCATIONS_NAME}")
    # A heading it couldn't read means places quietly filed as the wrong kind.
    # Say so on every search until it's fixed: a country filed as a city is the
    # difference between a location passing and being turned away.
    verdict.hints.extend(mine.problems)

    # Recognised overall, but a word we couldn't place looks like a near miss —
    # worth mentioning ("Austn, TX") without refusing to search.
    for part in unplaced:
        if len(part.split()) == 1 and len(part) >= 4 and not any(c.isdigit() for c in part):
            close = suggest(part, index, limit=2)
            if close:
                verdict.hints.append(f"“{part}” — did you mean {' or '.join(close)}?")
    return verdict


def source() -> str:
    """Where the countries, states and cities being checked against came from."""
    path = countries_path()
    return str(path) if path else "the geonamescache and pycountry packages"


def stats() -> dict[str, int]:
    from .data import postal_codes as postal_data
    index = warm()
    numbers = {
        "continents": len(index.continents),
        "countries": len({v for v in index.countries.values()}),
        "country names": len(index.countries),
        "states / provinces": len(index.states),
        "city names (with local spellings)": len(index.cities),
        "postal codes": postal_data.TOTAL,
        "countries with postal codes": len(postal_data.CODES),
    }
    mine = custom()
    for kind in KINDS:
        if getattr(mine, kind):
            numbers[f"{kind} you added"] = len(getattr(mine, kind))
    if extras():
        numbers["extra places from the environment"] = len(extras())
    return numbers


# ---------------------------------------------------------------------------
# CLI — handy for checking the data without running a search
# ---------------------------------------------------------------------------

def _load_env() -> None:
    """Best effort: this CLI should see the same .env the app reads."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:                  # python-dotenv not installed — env only
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    _load_env()
    if argv[0] == "--locations":
        had_one = locations_path().exists()
        path = write_template()
        mine = custom()
        print(f"  {path}")
        if not had_one:
            print("  created — open it and add your places under the headings")
            return 0
        for kind in KINDS:
            entries = getattr(mine, kind)
            if entries:
                print(f"\n  [{kind}]")
                for name, hint in entries.values():
                    print(f"    · {name}" + (f"  ({hint})" if hint else ""))
        if not len(mine):
            print("  no places added yet")
        for problem in mine.problems:
            print(f"  ! {problem}")
        return 1 if mine.problems else 0
    if argv[0] == "--stats":
        print(f"  from {source()}\n")
        for label, value in stats().items():
            print(f"  {label:36} {value:>10,}")
        for name, hint in extras().values():
            print(f"    · {name}" + (f"  ({hint})" if hint else ""))
        return 0
    worst = 0
    for location in argv:
        verdict = verify(location)
        if verdict.ok:
            print(f"✓ {location}  →  {verdict.summary()}")
            for hint in verdict.hints:
                print(f"  ! {hint}")
            for note in verdict.notes:
                print(f"  · {note}")
        else:
            worst = 1
            print(f"✗ {location}  →  {verdict.reason()}"
                  + (f"   did you mean: {', '.join(verdict.suggestions)}?"
                     if verdict.suggestions else ""))
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
