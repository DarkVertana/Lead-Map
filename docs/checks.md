# Field checks

Everything on this page happens **offline**, before a single API call is spent. A typo in
a location used to cost a geocoding call and a confusing empty result; now it costs
nothing.

## What's on disk

| Data | Size | Source | Licence |
|---|---|---|---|
| Continents, countries, cities | 7 · 252 · 310,274 name spellings | [geonamescache](https://github.com/yaph/geonamescache) (GeoNames) | CC BY 4.0 |
| States, provinces, regions | 4,880 | [pycountry](https://github.com/pycountry/pycountry) (ISO 3166-2) | LGPL-2.1 |
| Postal codes | 1,080,715 across 121 countries | GeoNames, bundled as `postal_codes.py` | CC BY 4.0 |
| Place types | 478 filterable + 36 not | Google's own documentation | Google's terms |

The postal codes are in the repository, not downloaded at runtime. They compress to
1.1 MB because they're **front-coded** — each code stores only how much it shares with
the previous one, then the rest — which takes 7 MB of text to under 1 MB.

## Checking a location

```bash
python -m leadmap.validate.gazetteer "Austin, TX" "560999, India" "Bangalre"
```

```
✓ Austin, TX  →  city Austin · state TX
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

A location **passes if any part is a place we know**. That's deliberately generous:
`Baner, Pune` passes on Pune, and a street address passes on its city. The job is
catching typos, not second-guessing an address Google can resolve.

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

### Cost

| | |
|---|---|
| First run ever | ~700 ms to build the index |
| Every run after | ~100 ms, from a 5 MB cache in `~/.cache/leadmap` |
| `verify()` itself | ~1 ms |
| Memory | +50 MB while loaded, almost entirely the 310k city names |

In the guided session even that is invisible: a background thread warms the index while
you read the first question.

## Checking a category

```bash
python -m leadmap.validate.place_types "coffee shop" "chemist" "dentst"
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
rejects a bad one outright. So LeadMap does too, before spending the call:

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
