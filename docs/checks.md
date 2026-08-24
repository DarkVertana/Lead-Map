# Field checks

Everything on this page happens **offline**, before a single API call is spent. A typo in
a location used to cost a geocoding call and a confusing empty result; now it costs
nothing.

## What's on disk

| Data | Size | Where | Licence |
|---|---|---|---|
| Continents, countries, states, cities | 7 · 252 · 4,880 · 34,006 cities under 118,938 spellings | **`countries.json`** in the project root | CC BY 4.0 (GeoNames) + LGPL-2.1 (ISO 3166-2) |
| Postal codes | 1,080,715 across 121 countries | `validate/data/postal_codes.py` | CC BY 4.0 (GeoNames) |
| Place types | 478 filterable + 36 not | `validate/place_types.py` | Google's terms |

Both are in the repository, not downloaded at runtime. The postal codes compress to
1.1 MB because they're **front-coded** — each code stores only how much it shares with
the previous one, then the rest — which takes 7 MB of text to under 1 MB.

## `countries.json` — the place names, editable

`countries.json` **is** the data, not a copy of it. Open it, correct a name, save; the
next run uses the correction. Nothing is downloaded, and no cache has to be cleared —
the index is stamped with the file's size and modification time, so an edit rebuilds it
on its own.

It's written one record per line, grouped by country code, so finding what you want to
change is a search rather than a hunt:

```json
 "countries": [
  {"code": "IN", "iso3": "IND", "name": "India", "also": [], "postal": "^(\\d{6})$", "population": 1352617328},

 "states": {
  "IN": [
   ["BR", "Bihār"],
   ["MH", "Mahārāshtra"],

 "cities": {
  "IN": [
   ["Mumbai", "Bombai", "Bombay", "Bombej", …],
   ["Nashik", "Nasik", "Nasikas", "Naszik"],
```

| Section | Shape | |
|---|---|---|
| `continents` | a list of names | |
| `countries` | one object each | `code` is ISO 3166-1 alpha-2 and is what the two sections below are grouped by. `also` holds other names the country answers to. `postal` is the pattern a postal code beside it must match, or `null` for no check. `population` only orders the guesses when a bare postal code has to be attributed to a country. |
| `states` | `[code, name]` per country | ISO 3166-2 subdivisions |
| `cities` | `[name, ...other spellings]` per country | The first is what's shown back to you; the rest only have to be recognised |

Names are matched **case- and accent-insensitively**, so `Kolhapur` already finds
`Kolhāpur` — you never need to add a spelling that differs only in those. That's also
why the diacritics you'll see in `states` (`Bihār`, `Mahārāshtra`) don't stop anything
matching; correct them if you'd rather read them plain.

**A file that won't parse can't take the checker down.** It says which line broke and
falls back to the packages the file was generated from, so a location still gets checked
while you fix it:

```
! countries.json couldn't be read (Expecting value: line 22391 column 23) — using the packaged data for now
```

`--stats` says which file is in play, and `/where` in the session shows it too.

### Regenerating it

```bash
.venv/bin/python tools/build_countries.py
```

That rebuilds the file from GeoNames and ISO 3166-2 — and **overwrites your edits**. Keep
anything you want to survive it in the [locations file](#adding-places-it-doesnt-know)
instead, which the tool never touches.

The tool filters alternate spellings on the way in. GeoNames carries ~353,000 and most
are machine transliterations of other scripts (`na xi ke` for Nashik); since every name is
folded to plain lower-case ASCII before matching, those add nothing a capitalised spelling
doesn't already cover. The ~92,000 that survive are the real ones — Bombay, Calcutta,
Bangalore, Allahabad.

## Checking a location

```bash
python -m businesslead.validate.gazetteer "Austin, TX, USA" "Austin, TX" "560999, India" "Bangalre"
```

```
✓ Austin, TX, USA  →  city Austin · state TX · country USA
✗ Austin, TX  →  name the country — did you mean “Austin, TX, United States”?
✗ 560999, India  →  “560999” is not a postal code in India
✗ Bangalre  →  I don't know any place in “Bangalre”   did you mean: Bangalore, Bangalur?
```

### How it decides

1. The answer is split on commas.
2. Each part is folded — lower-cased, accents stripped, punctuation flattened — so
   `Kolhāpur` and `kolhapur` are the same string.
3. Each part is looked up whole, then as sliding windows of up to four words, so
   `New York City` matches before `New`.
4. Anything numeric is tested as a postal code, against the country already matched if
   there is one.

A location **passes if any part is a place we know** — and if one of those parts is a
country. Apart from that it's deliberately generous: `Baner, Pune, India` passes on Pune,
and a street address passes on its city. The job is catching typos, not second-guessing an
address Google can resolve.

### The country is required

Everything else — state, city, district, street, postcode — is optional. `India` on its
own is a fine location. `Delhi` on its own is not:

```
✗ Delhi  →  name the country — did you mean “Delhi, India”? (or PLACES_REGION=in in .env)
```

There are Delhis in California and Ontario, a Springfield in most US states, and a Paris
in Texas. Google will geocode a bare one to *somewhere*, and which somewhere depends on
nothing your search says — so the whole sweep, and everything it spends, lands on an area
nobody asked for. Naming the country is what makes the answer the one you asked for.

Where a part belongs to exactly one country the message finishes the location for you, as
above: `TX` is a US state, `560001` is an Indian postcode.

Two ways to not type it every time:

| | |
|---|---|
| `PLACES_REGION=in` in `.env` | names the country for every search, so `Delhi` passes |
| Override once | send the same answer twice in the session, or `--no-verify` on the CLI |

The strict case is a postal code on its own: India has 19,238 and `560999` is not one of
them, so that fails.

### Near misses

A word it can't place but nearly recognises is reported without blocking:

```
  › Bengalru, Karnataka
  ⎿ ! “Bengalru” — did you mean Bengaluru or Bengalurus?
```

The search still runs — `Karnataka` is real, so the answer is usable — but you're told.

### Overriding it

Send the same answer twice in the session, or pass `--no-verify` on the CLI. Worth
knowing when you'd need to: the city list is GeoNames' populated-places-over-15,000 set,
so a village or a brand-new suburb genuinely won't be in it.

### Adding places it doesn't know

You can always add the place to [`countries.json`](#countriesjson--the-place-names-editable)
directly. The one thing to know is that regenerating that file overwrites it — so for
places you want to keep permanently, there's a second file the generator never touches:

```bash
businesslead --locations          # prints the path, creating the file if there isn't one
```

```
~/.config/businesslead/locations.txt
created — add your places under the headings in it
```

It arrives as a commented template. Add a line per place, under the heading saying what
kind of place it is:

```ini
[countries]
Kosovo:XK

[states]
Telangana:IN

[cities]
Prayagraj:IN
Chhatrapati Sambhajinagar:India
Baner Gaon:IN
```

```
$ python -m businesslead.validate.gazetteer "Chhatrapati Sambhajinagar, 431001, India"
✓ Chhatrapati Sambhajinagar, 431001, India  →  city Chhatrapati Sambhajinagar · country India · postcode 431001
  · “Chhatrapati Sambhajinagar” — from your locations.txt
```

| | |
|---|---|
| Where it lives | `locations.txt` beside your `.env` if there is one, otherwise `~/.config/businesslead/locations.txt` (`%LOCALAPPDATA%\businesslead\config\` on Windows). `BUSINESSLEAD_LOCATIONS_FILE` overrides both. |
| Headings | `[countries]`, `[states]`, `[cities]` — singular and looser spellings (`[province]`, `[towns]`, `[districts]`) work too. Lines before any heading are taken as cities. |
| Comments | `#` to end of line; blank lines ignored |
| `:country` | optional; an ISO code (`IN`, `IND`) or a name (`India`) |
| **Why the heading matters** | a location has to name a country, so a name under `[countries]` is what lets a search built on it pass. A city under `[cities]` still needs a country beside it, same as any other city. |
| What the country half does | decides whose postal codes a code next to that name is checked against: above, `431001` passes and `999999` still fails |
| Also | typos suggest it — `Prayagrj` → *did you mean Prayagraj?* |

The file is read fresh on every run and **never written into the cached index**, so a line
you add counts on the very next run — nothing to rebuild, nothing re-downloaded. Delete
the file to go back to the shipped data alone.

`businesslead --locations` lists what's in it, `/where` in the session shows the path, and
`--stats` counts it:

```
  countries you added                                   1
  cities you added                                      3
```

A heading it can't read is reported with its line number, on every check until you fix it
— places filed under the wrong kind is exactly the failure you wouldn't otherwise notice:

```
  ! line 12: [countys] isn't a heading I know — use [countries], [states], [cities]
```

Adding places only widens what passes — a name you add can never make a real place fail.
If a location matches one, the session and the CLI both say so, so a search that ran on
your own spelling is never silent about it.

#### The quick way, for one place

`PLACES_EXTRA_LOCATIONS` in `.env` still works and needs no file. It takes the same
`Name:Country` pairs, separated by commas, and treats every one as a generic place rather
than a typed country/state/city — so it can't be used to name a country:

```bash
PLACES_EXTRA_LOCATIONS=Prayagraj:IN, Chhatrapati Sambhajinagar:India, Baner Gaon
```

### Cost

| | |
|---|---|
| First run ever | ~700 ms to build the index |
| Every run after | ~100 ms, from a 5 MB cache in `~/.cache/businesslead` |
| `verify()` itself | ~1 ms |
| Memory | +50 MB while loaded, almost entirely the 310k city names |

In the guided session even that is invisible: a background thread warms the index while
you read the first question.

## Checking a category

```bash
python -m businesslead.validate.place_types "coffee shop" "chemist" "dentst"
```

```
✓ coffee shop  →  coffee_shop  (Food and Drink)
✓ chemist  →  pharmacy  (Health and Wellness)
  · “chemist” → Google's pharmacy
✗ dentst  →  “dentst” is not one of Google's 478 place categories   did you mean: dentist?
```

What you type is tidied before matching:

| Input | Becomes | Why |
|---|---|---|
| `Coffee Shop` | `coffee_shop` | spacing and case folded |
| `bakeries` | `bakery` | plurals trimmed |
| `beauty parlour` | `beauty_salon` | British spelling, then an alias |
| `chinese` | `chinese_restaurant` | a bare cuisine grows its noun |
| `best artisan bakery` | `bakery` | longer phrases are scanned for a type inside them |
| `petrol pump` | `gas_station` | one of 150 everyday and Indian-English aliases |

Aliases cover the words people actually use: `chemist`, `medical store`, `kirana store`,
`saloon`, `PG`, `railway station`, `car mechanic`, `dhaba`, `tiffin`, `cyber cafe`,
`sweet shop`, `advocate`, `packers and movers`.

The category still reaches Google as free text, so the check only catches typos — the
same send-it-twice override applies.

## `--type` is checked strictly

`--category` is a hint; `--type` becomes `includedType` in the request, and Google
rejects a bad one outright. So Business Lead does too, before spending the call:

```
✗ --type dentst is not a Google place type. Did you mean dentist?
✗ --type point_of_interest is a Table B type: Google returns it on a place but
  rejects it as a search filter
```

Table A holds the 478 types you may filter by; Table B holds 36 more that come back on a
place but can't be searched for.

## The address split

The same data solves a related problem. Google returns an address twice — as typed
components and as a printed line — and the components are authoritative when they're
there. Plenty of the world has no `route`:

> Shop No. 4, Ace Residences, near RD Circle, Karmayogi Nagar, Govind Nagar, Nashik,
> Maharashtra 422009, India

So when a component is missing, the printed line is parsed instead: the city, state,
postcode and country are stripped off the end, what remains becomes `street`, and its
last piece becomes `area`.

| | Components only | With the fallback |
|---|---|---|
| `street` filled | 75 / 121 | **121 / 121** |
| `area` filled | — | 118 / 121 |

Measured on a real run of 121 barbers in Nashik.
