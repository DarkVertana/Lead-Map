#!/usr/bin/env python3
"""
Regenerates countries.json — the countries, states and cities a location is
checked against. Run it when you want fresher data from GeoNames:

    .venv/bin/python tools/build_countries.py

Everything it writes is meant to be read and edited afterwards: one line per
country, per state and per city, grouped by country code, so finding the entry
you want to correct is a search rather than a hunt. Editing the file is the
supported way to fix a name — nothing re-downloads behind your back, and running
this tool again is the only thing that overwrites your changes.

Alternate spellings are filtered on the way in. GeoNames carries ~353,000 of
them and most are machine transliterations of other scripts ("na xi ke" for
Nashik); since every name is folded to plain lower-case ASCII before it is
matched, those add nothing a capitalised spelling doesn't already cover. What
survives is the ~92,000 that are real alternative names: Bombay, Calcutta,
Bangalore, Allahabad.

GeoNames data is CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
ISO 3166-2 subdivisions come from pycountry (LGPL-2.1).
"""

from __future__ import annotations

import collections
import json
import re
import unicodedata
from pathlib import Path

import geonamescache
import pycountry

TARGET = Path(__file__).resolve().parent.parent / "countries.json"

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")

README = [
    "The places a location is checked against, offline, before any API call.",
    "Edit it freely: correct a name, add a city the data missed, delete a wrong",
    "entry. It is read on the next run — nothing is downloaded and no cache has",
    "to be cleared by hand.",
    "",
    "countries  one object each. 'code' is ISO 3166-1 alpha-2 and is what the",
    "           states and cities below are grouped by; 'also' holds other",
    "           names the country answers to; 'postal' is the pattern a postal",
    "           code beside it has to match, or null for no check.",
    "states     [code, name] per country — ISO 3166-2 subdivisions.",
    "cities     [name, ...other spellings] per country. The first is the one",
    "           shown back to you; the rest only have to be recognised.",
    "",
    "Names are matched case- and accent-insensitively, so 'Kolhapur' finds",
    "'Kolhāpur' and you never need to add a spelling that differs only in those.",
    "",
    "Regenerate from GeoNames with: python tools/build_countries.py",
    "That overwrites this file, so keep your own additions in the locations file",
    "(businesslead --locations) if you want them to survive it.",
]


def fold(text: str) -> str:
    """The same folding the checker uses: lower-case, unaccented, unpunctuated."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _SPACES.sub(" ", _PUNCT.sub(" ", stripped)).strip()


def worth_keeping(name: str, canonical: str, seen: set[str]) -> bool:
    """Is this alternate spelling one a person might actually type?

    Dropped: anything that isn't plain ASCII once folded, anything that folds to
    a spelling already held, anything all-lower-case (those are transliterations
    of other scripts, and their capitalised forms are kept where they are real),
    and short all-caps tokens, which are airport codes rather than place names.
    """
    folded = fold(name)
    if not folded or not folded.isascii() or folded == canonical or folded in seen:
        return False
    if name == name.lower():
        return False
    if name.isupper() and len(name) <= 4:
        return False
    return True


def alternates(entry: dict, canonical: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in sorted(entry.get("alternatenames") or ()):
        if worth_keeping(name, canonical, seen):
            seen.add(fold(name))
            out.append(name)
    return out


def build() -> dict:
    cache = geonamescache.GeonamesCache()

    continents = sorted(c["name"] for c in cache.get_continents().values())

    countries = []
    for iso2, country in sorted(cache.get_countries().items()):
        names = {fold(country["name"])}
        also = []
        for entry in (pycountry.countries.get(alpha_2=iso2),):
            for attribute in ("name", "common_name", "official_name"):
                value = getattr(entry, attribute, None) if entry else None
                if value and fold(value) not in names:
                    names.add(fold(value))
                    also.append(value)
        countries.append({
            "code": iso2,
            "iso3": country["iso3"],
            "name": country["name"],
            "also": also,
            "postal": (country.get("postalcoderegex") or "").strip() or None,
            # Only used to order the guesses when a bare postal code has to be
            # attributed to a country — biggest first.
            "population": country.get("population") or 0,
        })

    states: dict[str, list] = collections.defaultdict(list)
    for subdivision in pycountry.subdivisions:
        code = subdivision.code.split("-", 1)[-1]
        states[subdivision.country_code].append([code, subdivision.name])
    for state in cache.get_us_states().values():          # 'CA' → California
        states["US"].append([state["code"], state["name"]])
    for iso2 in states:
        seen, unique = set(), []
        for code, name in sorted(states[iso2], key=lambda row: row[1]):
            if fold(name) not in seen:
                seen.add(fold(name))
                unique.append([code, name])
        states[iso2] = unique

    cities: dict[str, list] = collections.defaultdict(list)
    for entry in cache.get_cities().values():
        canonical = fold(entry["name"])
        if not canonical:
            continue
        cities[entry["countrycode"]].append([entry["name"], *alternates(entry, canonical)])
    for iso2 in cities:
        cities[iso2].sort(key=lambda row: row[0])

    return {"_readme": README, "continents": continents, "countries": countries,
            "states": dict(sorted(states.items())),
            "cities": dict(sorted(cities.items()))}


def dump(data: dict) -> str:
    """JSON with one line per place, which is what makes it editable at all.

    json.dumps with an indent puts every string in an array on its own line —
    35,000 cities become 300,000 lines and the file stops being something you
    can scroll. Each record is written compact, one to a line, instead.
    """
    out = ["{"]
    out.append(' "_readme": [')
    out.append(",\n".join(f"  {json.dumps(line, ensure_ascii=False)}"
                          for line in data["_readme"]))
    out.append(" ],")
    out.append(' "continents": ' + json.dumps(data["continents"]) + ",")

    out.append(' "countries": [')
    out.append(",\n".join(f"  {json.dumps(row, ensure_ascii=False)}"
                          for row in data["countries"]))
    out.append(" ],")

    for section in ("states", "cities"):
        out.append(f' "{section}": {{')
        blocks = []
        for iso2, rows in data[section].items():
            body = ",\n".join(f"   {json.dumps(row, ensure_ascii=False)}" for row in rows)
            blocks.append(f'  "{iso2}": [\n{body}\n  ]')
        out.append(",\n".join(blocks))
        out.append(" }," if section == "states" else " }")
    out.append("}")
    return "\n".join(out) + "\n"


def main() -> int:
    data = build()
    text = dump(data)
    json.loads(text)                       # never write something we can't read back
    TARGET.write_text(text, encoding="utf-8")
    print(f"  {TARGET}")
    print(f"  {len(data['countries']):,} countries · "
          f"{sum(len(v) for v in data['states'].values()):,} states · "
          f"{sum(len(v) for v in data['cities'].values()):,} cities · "
          f"{sum(len(r) - 1 for v in data['cities'].values() for r in v):,} other spellings")
    print(f"  {TARGET.stat().st_size / 1e6:.2f} MB, {text.count(chr(10)):,} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
