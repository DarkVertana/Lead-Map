# Business Lead

**Business leads from Google Places — name, phone, website and a properly split address,
straight to csv, excel, pdf or json. Stays inside the free tier on purpose.**

[![CI](https://github.com/DarkVertana/Business-Lead/actions/workflows/ci.yml/badge.svg)](https://github.com/DarkVertana/Business-Lead/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
[![Places API](https://img.shields.io/badge/Google-Places%20API%20%28New%29-e08c48.svg)](https://developers.google.com/maps/documentation/places/web-service/overview)
[![Docs](https://img.shields.io/badge/docs-darkvertana.github.io-8a4a1c.svg)](https://darkvertana.github.io/Business-Lead/)

📖 **[Full documentation →](https://darkvertana.github.io/Business-Lead/)**

```
╭────────────────────────────────────╮
│ ✻ Welcome to Business Lead  v2.0.0 │
╰────────────────────────────────────╯

 ████  █   █  ████ █████ █   █ █████  ████  ████   █     █████  ███  ████
 █   █ █   █ █       █   ██  █ █     █     █       █     █     █   █ █   █
 ████  █   █  ███    █   █ █ █ ████   ███   ███    █     ████  █████ █   █
 █   █ █   █     █   █   █  ██ █         █     █   █     █     █   █ █   █
 ████   ███  ████  █████ █   █ █████ ████  ████    █████ █████ █   █ ████
  ████   ███  ████  █████ █   █ █████ ████  ████    █████ █████ █   █ ████

  Business leads from Google Places  ·  csv · excel · pdf · json
  cwd: ~/projects/businesslead
```

Point it at a **location** and a **category** (or a specific business **name**) and it
comes back with every matching business Google will give up — 34 columns per row,
deduplicated, sorted by review count.

### What makes it different

- **It doesn't stop at 60.** Google truncates any text search at 60 places. Business Lead
  notices a truncated tile and re-searches that ground in quarters, over and over, until
  the results stop hitting the ceiling. A real run on Nashik barbers: 121 businesses from
  25 tiles.
- **It won't quietly bill you.** Google's free tier is per-SKU now, and this field mask
  bills at **1,000 searches a month**. Business Lead counts every call in a local ledger, splits
  the month across its days, and *stops* — there is no flag that spends money.
- **It checks before it spends.** Locations and categories are validated against 1.4M
  offline records (GeoNames + ISO 3166-2 + Google's own 478 place types) so a typo costs
  nothing instead of a geocoding call.
- **The address is actually split.** street · area · city · district · state · postcode —
  including the two-thirds of Indian addresses that carry no `route` component at all.
- **The terminal is the interface.** A Claude-Code-style guided session: one question at
  a time, a live progress bar, and slash commands (`/quota`, `/category`, `/sessions`).

### Quickstart

```bash
git clone https://github.com/DarkVertana/Business-Lead.git
cd Business-Lead
cp .env.example .env          # then put your Google API key in it
./run.sh                      # creates the venv, installs, starts the session
```

On Windows, `.\run.ps1` (PowerShell) or `run.cmd` (cmd) do the same thing — see
[Setup → On Windows](https://darkvertana.github.io/Business-Lead/#/setup?id=on-windows).

One-shot instead:

```bash
./run.sh -l "Nashik, India" -c barber -o barber_nashik.csv
```

You need a Google Cloud project with **Places API (New)** and **Geocoding API** enabled —
see [Setup](#setup), or the [setup guide](https://darkvertana.github.io/Business-Lead/#/setup)
in the docs.

---

Two ways to drive it:

* **Guided mode** (default when you run it bare) — asks one question at a time
  (**File → Location → Category → Name**) in a Claude-Code-style terminal interface,
  then sweeps the area and writes the file.
* **CLI mode** (whenever you pass search options) — one-shot, scriptable, cron-safe.

Either way the location and category are checked against bundled offline data first, so a
typo costs you nothing instead of a geocoding call.

## Guided mode

```bash
./run.sh
```

No chat window, no bubbles: output scrolls in your real terminal as `⏺` steps with `⎿`
detail lines, and the only live element is a rounded input box that appears, takes one
answer, and disappears — leaving the answer behind as a line of output.

```
⏺ Free tier · Text Search Enterprise + Atmosphere
  ⎿ this month 103 of 1,000 used  ·  897 left  ·  resets 01 Sep 2026
  ⎿ today      17 of 111 used  ·  94 left  ▰▰▱▱▱▱▱▱▱▱
  ⎿ by day     Mon 0   Tue 24   Wed 8   Thu 0   Fri 31   Sat 12   today 17

⏺ File
  ⎿ Which file should these results go in? Enter to name it after the search.

╭──────────────────────────────────────────────────────────────────────╮
│ › austin_cafes                                                       │
╰──────────────────────────────────────────────────────────────────────╯
  1/4   enter to submit   ctrl+c twice to quit

  › austin_cafes.csv
  ⎿ · Business Lead/austin_cafes.csv — new file

⏺ Location
  ⎿ Where should I search? Name the country — the rest is optional.

  › Austin, TX, USA

⏺ Category
  ⎿ What kind of business? Leave empty if you want one named place.

  › coffee shop

⏺ Name
  ⎿ A particular business — or skip it and take the whole category.
  4/4   enter runs the search   ctrl+c twice to quit

  › any name

⏺ Locating Austin, TX, USA
  ⎿ resolved   Austin, TX, USA
  ⎿ coords     30.26720, -97.74310
```

The last answer runs the search — nothing to confirm. `/back` at any question steps back
one, with every answer kept as the default.

**The File question comes first, and skipping it is fine.** Press enter and the file is
named after your search, the way it always was — `Business Lead/coffee_shop_austin_tx.csv`.
Answer it and *you* decide which file the results join, which is the point: a **Mumbai**
search and a **Bombay** search are the same city, and naming the same file for both puts
them in one list instead of two. As you answer, it tells you what's already in there:

```
  › mumbai_dentists.csv
  ⎿ · Business Lead/mumbai_dentists.csv — 221 rows already, this search adds to them
```

**Name a file it has written before and it picks that search back up** — location and
category come from the run that last wrote to it, and it jumps straight to the last
question, so topping a list up is one answer and one enter. `/back` from there reaches
category and location when you want to vary it.

A name with no extension gets the one `.env` asks for — `PLACES_FORMAT=csv` (or `excel`,
`pdf`, `json`), set once and never asked about. A name with a directory in it
(`~/Desktop/cafes.pdf`, `reports/leads.xlsx`) is left exactly where you put it, and
`BUSINESSLEAD_OUTPUT_DIR` moves the root. **The file you name sticks for the rest of the
session** — every search after it offers the same file as the default, so a run of related
searches collects in one place without retyping it. CSV and Excel carry all 34 columns;
the PDF is a landscape table of the essential twelve.

**One search, one file.** Run the same location and category next week and what it finds
is added to the file that search already has, under the rows already in it — so a lead
list grows instead of scattering across a folder of near-identical files. The
`extracted_on` column dates every row, so you can always see which run brought what in.
Nothing already delivered is rewritten: a business found twice keeps the date it first
arrived, and the file is replaced only once the new one is written whole.

**Coverage isn't a question any more.** Business Lead sweeps the whole area on its own — see
below.

Confirm and it runs the search right there, with the same renderer CLI mode uses. When
it's written the file it offers the same results in other formats — that costs nothing,
it just re-writes what's already on disk — and then another search:

```
⏺ Another copy?
  ⎿ pdf, excel, json or csv — costs nothing, it just re-writes what you have.

  › pdf excel
  ⎿ ✓ barber_nashik.pdf
  ⎿ ✓ barber_nashik.xlsx
```

Nothing is ever typed into the box for you — a default is shown greyed out and applied
if you just press Enter, so you never delete someone else's text to write your own.
Up/down recalls what you answered to that same question earlier in the session.

| At the box | |
|---|---|
| `enter` | submit — or accept the greyed-out default |
| `ctrl+c` | clear the line; pressed twice in a row, leave the session |
| `/help` | the commands below |

### Commands

Any answer starting with `/` is a command. They work at every question, print what they
have to say, and hand the question straight back — nothing is lost.

| Command | | Does |
|---|---|---|
| `/help` | `/?` | lists all of this |
| `/back` | `/b` | change the previous answer |
| `/category [word]` | `/cat` | the 478 place types Google accepts — by group, or searched |
| `/quota` | `/usage` | what's left today and this month, day by day |
| `/switch [plan]` | `/plan` | pick a billing SKU from a list — 1,000/mo up to unlimited |
| `/borrow N` | | N more calls today, taken from the month's remainder |
| `/daily-cap [N]` | `/limit` | set today's whole allowance |
| `/sessions` | `/history` | the searches you've already run: rows, calls, files |
| `/settings` | `/config` | the answers and options in play right now |
| `/formats` | `/output` | what each file format carries, and where it lands |
| `/where` | `/paths` | output folder, usage ledger, history, `.env` |
| `/open` | `/reveal` | open the output folder in Finder |
| `/clear` | `/cls` | clear the screen |
| `/version` | `/v` | version, Python, and which SKU you're billing at |
| `/reset-quota` | | forget today's recorded usage — **development only** |
| `/quit` | `/exit`, `/q` | leave |

`/category` is the one to reach for when a category is rejected:

```
› /category coffee
⏺ Categories matching “coffee”
  ⎿ coffee_roastery              coffee_shop                  coffee_stand
  ⎿ also understood  coffee → coffee_shop, coffee_house → coffee_shop

› /category health
⏺ Health and Wellness · 20 types
  ⎿ chiropractor    dental_clinic    dentist
  ⎿ doctor          drugstore        general_hospital
  …
```

**Running out of calls doesn't end the conversation.** Searching is what the free tier
limits; talking to the tool isn't — and `/reset-quota` would be useless if being out of
quota were what locked you out of it. So when the day's share is spent the session drops
into a commands-only prompt and waits:

```
✗ Out of free calls for today
  ⎿ today's share is spent · 889 left this month, back tomorrow
  ⎿ /borrow N takes N more calls from the rest of the month
  ⎿ commands still work — /borrow, /reset-quota, /quota, /sessions, /help

› /borrow 40
✓ Borrowed 40 calls for today
  ⎿ left today       40
  ⎿ left this month  889 of 1,000

✓ 40 calls available — carrying on
```

`/borrow N` is the honest way out: it takes N more calls from the month's remainder and
can never exceed it. `/reset-quota` is the other way — it clears Business Lead's own counters
so a development loop isn't blocked, but **it resets nothing at Google**: those calls
have been made and Google still counts them. The real limit is the one in the Cloud
console.

Three of these also work from the command line, for scripts and cron:

```bash
businesslead --usage          # same as /quota  (--verbose adds the day-by-day list)
businesslead --sessions       # same as /sessions
businesslead --locations      # the places you've added by hand
businesslead --reset-quota    # same as /reset-quota
```

`ctrl+c` deliberately takes two presses. Editors type into the terminal on their own —
VS Code activates the project virtualenv a moment after a terminal opens, and it clears
the line with `ctrl+c` first — which used to end the session before you had typed a
thing. That activation command is now recognised and ignored if it lands in the box
instead of being taken as your answer.

The questions live in `QUESTIONS` in [`session.py`](businesslead/session.py) — a fixed,
offline list, not a model. Location is required, and you need a category, a name, or
both: skip the category and the name becomes required.

## CLI mode

Passing any search option skips the questions and runs straight through:

```
⏺ Locating Austin, TX, USA
  ⎿ resolved   Austin, TX, USA
  ⎿ coords     30.26720, -97.74310

⏺ Search plan
  ⎿ looking for coffee shop
  ⎿ area       12.0 km radius  ·  everything in it
  ⎿ sweep      until today's 125 calls run out  ·  splits where it's dense
  ⎿ no repeats 312 delivered before  ·  left out of this file
  ⎿ output     cafes.csv
  ⎿ api key    AIzaSy…0099 · from .env

⏺ Searching Google Places
  ⎿ query      "coffee shop in Austin, TX, USA"
  ⎿ ✓ 147 unique businesses in 9.4s · 5 tiles · 7 API requests

⏺ Top results
 Business              Rating   Reviews   Phone            City     Website
 ────────────────────────────────────────────────────────────────────────────────
 Houndstooth Coffee       4.6       900   (512) 555-0100   Austin   houndstooth.com
 …

╭─ summary ──────────────────────╮
│ ✓ Done  ·  147 businesses saved│
│                                │
│ businesses    147              │
│ with phone    141/147 ▰▰▰▰▰▰▰▰▰▱│
│ with website  118/147 ▰▰▰▰▰▰▰▰▱▱│
│ avg rating    4.41 ★           │
│ elapsed       9.8s             │
│ tiles swept   5                │
│ api requests  7                │
│                                │
│ CSV  cafes.csv                 │
╰────────────────────────────────╯
```

While it works, a pulsing `✻` spinner reports live progress
(`✻ Percolating… ▰▰▰▰▰▰▱▱▱▱▱▱  tile 3/4 · 29 found  (4s · ctrl+c to stop)`).

## Setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project,
   enable **Places API (New)** and **Geocoding API**, and create an API key
   (billing must be enabled on the project; the free tier below still applies).
2. Put the key in `.env` (already created for you, and git-ignored):

   ```bash
   GOOGLE_MAPS_API_KEY=AIza...
   ```
3. Install into a virtualenv:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt      # just the dependencies
   .venv/bin/pip install -e .                     # …or the package, for a `businesslead` command
   ```

`./run.sh` does steps 3 + run in one go, if you prefer.

```bash
./run.sh -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv
./run.sh -l "Pune, India" -n "Apollo Pharmacy" -o apollo.xlsx

# or, with the venv activated
source .venv/bin/activate
python -m businesslead --help        # `businesslead --help` after pip install -e .
```

Force either mode with `--guided` / `--no-guided` (`--chat` / `--no-chat` still work).
With `--no-guided`, or in a non-interactive shell, missing values are asked for as
simple line prompts.

## Field checks

### Location

Before anything is geocoded, the location is checked against open data shipped with the
tool — no network, no API call:

| Data | Rows | Where |
|---|---|---|
| continents, countries, states, cities | 7 · 252 · 4,880 · 34,006 cities under 118,938 spellings | [`countries.json`](countries.json) — GeoNames CC BY 4.0 + ISO 3166-2 |
| postal codes | 1,080,715 across 121 countries | [`validate/data/postal_codes.py`](businesslead/validate/data/postal_codes.py) — GeoNames, CC BY 4.0 |

**`countries.json` is the data, not a copy of it.** It sits in the project root, one
record per line grouped by country code. Correct a name in it and the next run uses the
correction — nothing is downloaded and no cache needs clearing, because the index is
stamped with the file's size and mtime and rebuilds when it changes. A file that won't
parse names the line that broke and falls back to the packaged data, so a bad edit never
stops a search being checked. `tools/build_countries.py` regenerates it from GeoNames,
overwriting your edits — see [Field checks](https://darkvertana.github.io/Business-Lead/#/checks).

```bash
$ .venv/bin/python -m businesslead.validate.gazetteer "Austin, TX, USA" "560999, India" "asdkjh"
✓ Austin, TX, USA  →  city Austin · state TX · country USA
✗ 560999, India  →  “560999” is not a postal code in India
✗ asdkjh  →  I don't know any place in “asdkjh”

$ .venv/bin/python -m businesslead.validate.gazetteer --stats
```

A location passes if **any** part of it is a place the data knows — a city, a state, a
country, a continent or a postal code — and if one of those parts is a **country**.
Beyond that it is deliberately generous: `Baner, Pune, India` passes on Pune, and a street
address passes on its city, because the job is catching a typo rather than second-guessing
an address Google can resolve. Diacritics and local names are folded in, so `Kolhapur`,
`Bengaluru`, `Bangalore`, `Bombay` and `münchen` all match.

**The country is the one part you have to give.** State, city, district, street and
postcode are all optional — `India` alone is a fine location, `Delhi` alone is not:

```
✗ Delhi  →  name the country — did you mean “Delhi, India”? (or PLACES_REGION=in in .env)
```

There are Delhis in California and Ontario and a Paris in Texas. Google geocodes a bare
name to *somewhere*, chosen by nothing your search said, and the whole sweep then lands on
an area you didn't ask for. Where a part belongs to exactly one country — `TX`, `560001` —
the message finishes the location for you. `PLACES_REGION=in` in `.env` names the country
once for every search.

It is strict about one thing: a postal code on its own. India has 19,238 of them and
`560999` is not one, so that fails.

A word it can't place but *nearly* recognises is reported without blocking the search:

```
  › Bengalru, Karnataka
  ⎿ ! “Bengalru” — did you mean Bengaluru or Bengalurus?
```

In the guided session, send the same answer twice to search for it anyway. On the CLI
that's `--no-verify`.

Both of those are per-search. When a place is simply *missing* from the data — a city
that was renamed, a district split off last year, a suburb below GeoNames'
15,000-population cut, a country spelled differently — add it to
[`countries.json`](countries.json) directly. Regenerating that file overwrites your
edits, so for anything you want to keep permanently there's a second file the generator
never touches:

```bash
businesslead --locations      # prints the path, creating the file if there isn't one
```

The file arrives as a commented template. One place per line, under the heading that says
what kind of place it is:

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
$ .venv/bin/python -m businesslead.validate.gazetteer "Chhatrapati Sambhajinagar, 431001, India"
✓ Chhatrapati Sambhajinagar, 431001, India  →  city Chhatrapati Sambhajinagar · country India · postcode 431001
  · “Chhatrapati Sambhajinagar” — from your locations.txt
```

**The heading is the point.** A name under `[countries]` counts as a country, which is
what lets a location built on it pass the rule above; one under `[cities]` is a city and
still wants a country beside it. The `:country` half is optional — an ISO code (`IN`,
`IND`) or a name (`India`) — and only decides whose postal codes a code standing next to
that name is checked against, so `431001` above passes and `999999` still fails.

It lives at `locations.txt` beside your `.env` if there is one, otherwise
`~/.config/businesslead/locations.txt`; `BUSINESSLEAD_LOCATIONS_FILE` moves it. It is read
fresh every run and **never baked into the cached index**, so a line you add takes effect
immediately with nothing to rebuild. `businesslead --locations` lists what's in it,
`/where` in the session shows the path, and a heading it can't read is reported with its
line number until you fix it. Delete the file to go back to the shipped data alone.

For one place and no file, `PLACES_EXTRA_LOCATIONS=Prayagraj:IN, Baner Gaon` in `.env`
still works — it treats every entry as a generic place, so it can't name a country.

The postal codes come from
[`tools/build_geodata.py`](tools/build_geodata.py), which re-downloads them from GeoNames and
rewrites `businesslead/validate/data/postal_codes.py` — front-coded and compressed, 1.1 million codes take 1.1 MB.

### Category

The category is checked against **Google's own place types** — the 478 in Table A that a
search may be filtered by, plus the 36 in Table B that Google returns on a place but
refuses as a filter. Both tables live in [`validate/place_types.py`](businesslead/validate/place_types.py), copied from
[the Places documentation](https://developers.google.com/maps/documentation/places/web-service/place-types).

```bash
$ .venv/bin/python -m businesslead.validate.place_types "coffee shop" "chemist" "bakery" "dentst"
✓ coffee shop  →  coffee_shop  (Food and Drink)
✓ chemist  →  pharmacy  (Health and Wellness)
  · “chemist” → Google's pharmacy
✓ best artisan bakery  →  bakery  (Food and Drink)
✗ dentst  →  “dentst” is not one of Google's 478 place categories   did you mean: dentist?

$ .venv/bin/python -m businesslead.validate.place_types --list "Health and Wellness"
$ .venv/bin/python -m businesslead.validate.place_types --stats
```

What you type is tidied before matching: spacing and punctuation fold (`Coffee Shop` →
`coffee_shop`), plurals are trimmed (`bakeries` → `bakery`), British spellings are
folded (`parlour` → `parlor`, `centre` → `center`), a bare cuisine grows its noun
(`chinese` → `chinese_restaurant`), and a table of 150 everyday and Indian-English names
is applied — `chemist` → `pharmacy`, `petrol pump` → `gas_station`, `kirana store` →
`grocery_store`, `saloon` → `barber_shop`, `PG` → `guest_house`, `railway station` →
`train_station`. Longer phrases are scanned for a type inside them, so `best artisan
bakery` passes on `bakery`.

The category still reaches Google as free text — the check only catches typos, and the
same send-it-twice override applies. `--type`, which really is passed to the API as
`includedType`, is checked strictly instead: an unknown id or a Table B id is refused
outright, because Google would refuse it too.

```
✗ --type point_of_interest is a Table B type: Google returns it on a place but rejects
  it as a search filter
```

## How much it finds

One Google text search returns **at most 60 places**, however many are really there. So
Business Lead searches the area, and whenever a search comes back full — a sure sign Google
truncated it — it splits that circle into four and searches each one, over and over
until the results stop hitting the ceiling:

While it runs, one line rewrites itself in place:

```
✻ Percolating… ▰▰▰▰▰▰▰▱▱▱▱▱  tile 14/22 · 8 queued · 153 found  (9s · ctrl+c to stop)
```

and when it's done that line is gone, leaving:

```
⏺ Searching Google Places
  ⎿ query      “coffee shop in Pune, Maharashtra, India”
  ⎿ ✓ 179 unique businesses in 11.3s · 22 tiles · 61 API requests
```

`--verbose` puts the tile-by-tile log back if you want to watch it subdivide.

Empty countryside costs one search; a dense high street keeps subdividing. Results are
deduplicated by `place_id` throughout.

**Each tile is a billed query**, and nothing else bounds the sweep: it keeps subdividing
until the area stops giving or **today's free calls are gone**, whichever comes first. It
says which one stopped it rather than pretending it found everything:

```
  ⎿ ! 15 areas still had more to give · today's free calls are spent — the rest keeps until tomorrow
```

The run always reports `tiles swept` and `api requests` so the bill is never a surprise.
`--max-results N` stops early on count, and `--max-tiles N` puts a ceiling back on the
sweep if you want a smaller, predictable spend.

## Changing format later

A finished file can be rewritten in any other format without searching again — no API
call, no quota, it reads the rows off disk:

```bash
./run.sh --convert barber_nashik.csv                 # → .pdf, .xlsx and .json
./run.sh --convert barber_nashik.csv --to pdf        # just the one
./run.sh --convert leads.xlsx --to "csv, json"
```

```
⏺ Converting barber_nashik.csv
  ⎿ rows       121 × 34 columns
  ⎿ ✓ pdf   barber_nashik.pdf
  ⎿ ✓ xlsx  barber_nashik.xlsx

  no API calls — the data came off disk
```

It reads `.csv`, `.xlsx` and `.json`, and writes any of those plus `.pdf`. `--pdf-all`
puts every column in the PDF instead of the essential twelve.

## Staying inside the free tier

Google retired the $200 monthly credit in March 2025. Every SKU now has its own monthly
allowance of free calls, and the call after it is billed. The ones Business Lead touches
(checked against [Google's pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
on 2026-08-23):

| SKU | Free / month | Then |
|---|---|---|
| Geocoding | 10,000 | $5 / 1k |
| Text Search Essentials (IDs only) | unlimited | free |
| Text Search Essentials | 10,000 | $32 / 1k |
| Text Search Pro | 5,000 | $32 / 1k |
| Text Search Enterprise | 1,000 | $35 / 1k |
| **Text Search Enterprise + Atmosphere** | **1,000** | $40 / 1k |

A request bills at **the highest tier any field in its mask belongs to**. Business Lead asks
for phone, website, rating and review count (Enterprise) plus the editorial summary
(Atmosphere), so it bills at the last row: **1,000 free searches a month**. One geocode
per run, and up to 3 calls per tile — so roughly **330 tiles, or a dozen full 25-tile
sweeps, per month** at no cost.

[`quota.py`](businesslead/quota.py) works that SKU out from `FIELD_MASK` itself, so trimming the mask
raises the allowance it enforces. `--usage` shows where you stand:

```bash
$ ./run.sh --usage
  ledger  ~/.local/state/businesslead/usage.json
  billed as  Text Search Enterprise + Atmosphere  (1,000 free/month, then $40/1k)

  Text Search Enterprise + Atmosphere
    today       17 used       94 left
    Aug 2026   103 used      897 left of 1,000
  Geocoding
    today        3 used    1,108 left
    Aug 2026    14 used    9,986 left of 10,000

  a bigger free allowance would mean giving up fields:
     5,000/month as Text Search Pro — drop editorialSummary, nationalPhoneNumber, rating …
    10,000/month as Text Search Essentials — drop businessStatus, displayName, websiteUri …
```

Every start of the guided session opens with the same figures and the week behind them,
so you always know what a search is about to spend. `./run.sh --usage --verbose` adds a
day-by-day list for the whole month.

**The month is split across its days** so one afternoon can't eat it: today's share is
whatever is left of the month divided by the days remaining in it — 1,000 on the 1st is
32 a day, and days you don't search roll forward into a bigger share later. Every call
is written to a ledger at `~/.local/state/businesslead/usage.json` (`BUSINESSLEAD_USAGE_FILE` to
move it), which survives ctrl+c: the `finally` that saves it runs whatever happens.

When the share runs out mid-sweep the search stops, keeps what it found and writes the
file:

```
  ⎿ ■ today's share of the free tier is used up (111 of 111 calls) — 889 left this
    month, back tomorrow or use --daily-cap to borrow from it
```

Start a run with nothing left and it refuses before spending a geocode. `--daily-cap N`
borrows against the rest of the month, `--monthly-cap N` sets a different ceiling (if
Google changes the allowance, or you want a stricter one). To make either the standing
rule rather than a one-run flag, put it in `.env`:

```bash
BUSINESSLEAD_DAILY_CAP=60      # calls allowed per day, instead of remainder ÷ days left
BUSINESSLEAD_MONTHLY_CAP=800   # the month's ceiling the ledger enforces
```

Flags still win over `.env` for a single run, `/borrow` and `/daily-cap` still win
inside a session, and both values must be whole numbers of at least 1 — a bad value
stops the run rather than silently not protecting you. The caps govern searches;
geocoding keeps its own 10,000/month allowance. Nothing here can bill you: past the
allowance, Business Lead simply stops.

One caveat worth knowing: **the ledger only counts calls made through this machine.** If
the same key is used elsewhere, the real total is higher. The guarantee lives in Google
Cloud Console — APIs & Services → Places API (New) → Quotas → set *Requests per day* to
around 33 and you cannot be billed regardless of what any client does.

## Searching by business name

`--name` is **optional** and works alone or with `--category`; both feed the text query.

```bash
# every branch of a named business in a city
./run.sh -l "Bengaluru, India" -n "Apollo Pharmacy" -o apollo.csv

# only results whose name really contains it (drops loosely related places)
./run.sh -l "Bengaluru, India" -n "Apollo Pharmacy" -o apollo.csv --name-match
```

You need a location, an output file, and at least one of `--name` / `--category`.

## Options

| Flag | Meaning |
|---|---|
| `-l, --location` | Area to search (address, city, ZIP, landmark) — geocoded to a lat/lng |
| `-n, --name` | **Optional** business name (`Starbucks`, `Apollo Pharmacy`) |
| `-c, --category` | Category / keyword — optional if `--name` is given |
| `-o, --output` | Output file: `.csv`, `.xlsx`, `.pdf` or `.json` (format follows the extension) |
| `--api-key` / `--env-file` | Key override / path to the `.env` file |
| `--radius` | Search radius in metres (default: size of the geocoded area; max 50000) |
| `--max-tiles N` | Cap the sweep at N searches (default: whatever today's free calls allow) |
| `--include-seen` | Write businesses earlier runs delivered (default: only what's new) |
| `--resweep` | Search the whole area again instead of carrying on where the last run stopped |
| `--forget-seen` | Forget every delivered business and part-searched area, and exit |
| `--convert FILE` | Rewrite an existing results file in other formats — no search |
| `--to FORMATS` | Formats for `--convert` (default `pdf,excel,json`) |
| `--verbose` / `-v` | Log every tile instead of one progress bar |
| `--pdf-all` | Put all 34 columns in the PDF instead of the essential twelve |
| `--usage` | Show what's left of the free tier, and exit |
| `--daily-cap N` | Calls allowed today (default: the month's free calls ÷ days left) — `BUSINESSLEAD_DAILY_CAP` in `.env` makes it standing |
| `--monthly-cap N` | Free calls a month (default: Google's allowance for our field mask) — `BUSINESSLEAD_MONTHLY_CAP` in `.env` makes it standing |
| `--max-results` | Stop after N unique businesses |
| `--type` | Restrict to a Places type id (`restaurant`, `dentist`, `gym`, …) — must be Table A |
| `--min-rating` / `--open-now` | Server-side filters |
| `--name-match` | With `--name`: keep only results whose name contains it |
| `--plan NAME` | Which SKU to bill at: `atmosphere` (default), `enterprise`, `pro`, `essentials`, `ids` — fewer fields, bigger free allowance |
| `--no-verify` | Skip the offline checks on the location and category |
| `--with-website-only` / `--operational-only` | Local filters |
| `--language` / `--region` | e.g. `en` / `us` |
| `--json-out` | Also dump the raw API responses to JSON |
| `--guided` / `--no-guided` | Force the question-at-a-time session on/off |
| `--no-color` / `-q` | Plain output / silence everything |

## Configuration

Business Lead reads `./.env` (nearest one found), or `--env-file path/to/.env`. The optional
default variables keep their `PLACES_` prefix, so an existing `.env` still works after
the rename.

**Precedence** — `--api-key` flag › real environment variable › `.env`, so a key already
exported in your shell is never silently overridden. The run header shows the masked key
and where it came from.

Optional defaults, each still overridable by its flag:
`PLACES_LOCATION`, `PLACES_CATEGORY`, `PLACES_NAME`, `PLACES_TYPE`, `PLACES_RADIUS`,
`PLACES_GRID`, `PLACES_LANGUAGE`, `PLACES_REGION`. The free-tier caps live here too:
`BUSINESSLEAD_DAILY_CAP` and `BUSINESSLEAD_MONTHLY_CAP` (the `PLACES_` spellings are
accepted, as are the `LEADMAP_` ones this tool used before it was renamed), each still
overridable by `--daily-cap` / `--monthly-cap`. See `.env.example`.

`PLACES_EXTRA_LOCATIONS` has no flag: it lists places the offline check should treat as
real — see [Location](#location) above.

## Output columns

34 columns, in reading order — who they are, how to reach them, where they are, then
everything else Google knows:

| | |
|---|---|
| **who** | `name`, `category`, `primary_type`, `all_types` |
| **reach** | `phone`, `international_phone`, `website` |
| **where** | `street`, `area`, `city`, `district`, `state`, `state_code`, `postal_code`, `country`, `formatted_address`, `latitude`, `longitude` |
| **standing** | `rating`, `reviews_count`, `price_level`, `price_range`, `business_status`, `opened` |
| **hours** | `opening_hours`, `open_now` |
| **links** | `google_maps_url`, `reviews_url`, `directions_url` |
| **provenance** | `summary`, `place_id`, `search_query`, `searched_name` |

**The address is split properly.** Google returns it twice — as typed components and as
a printed line — and the components are authoritative when they're there. Plenty of the
world has no `route`, though: an Indian shop reads *"Shop No. 4, Ace Residences, near RD
Circle, Karmayogi Nagar, Govind Nagar, Nashik"* and carries no street component at all.
So when a component is missing, the printed line is parsed instead — the city, state,
postcode and country are stripped off the end and what's left becomes `street`, with its
last piece as `area`. On a real run of 121 barbers in Nashik that took `street` from
75/121 rows to 121/121.

Rows are deduplicated by `place_id` and sorted by review count. CSV is written with a
UTF-8 BOM so Excel opens it cleanly.

**CSV, Excel and JSON carry all 34 columns.** The **PDF is a landscape sheet of the
essential twelve** — name, type, phone, website, street, area, city, state, postcode,
rating, reviews, status — because a page has edges and 34 columns lands at 4pt type.
It says so in its own header, and `--pdf-all` overrides it if you want the whole grid
(A3 landscape, ~4pt).

## Libraries

| Library | Used for |
|---|---|
| `requests` | HTTP with connection pooling and proper TLS |
| `tenacity` | Automatic retry with exponential backoff on 429 / 5xx / network errors |
| `rich` | Panels, tables, spinners, colour |
| `typer` | CLI and rich-formatted `--help` |
| `prompt-toolkit` | The inline input box of the guided session |
| `questionary` | Line prompts on the `--no-guided` path |
| `geonamescache` | Source for `countries.json`, and the fallback if it won't parse (GeoNames, CC BY 4.0) |
| `pycountry` | States / provinces / regions for the same (ISO 3166-2) |
| `python-dotenv` | `.env` loading |
| `pandas` (+`openpyxl`) | Sorting, stats and CSV / XLSX / JSON output |
| `reportlab` | The PDF table |

## Layout

```
businesslead/                  the package — python -m businesslead, or `businesslead` once installed
├── cli.py                flags in; a search, a conversion or a usage report out
├── session.py            the guided session: questions, input box, flow
├── search.py             one run end to end: check, locate, sweep, write, report
├── places.py             the HTTP client — one call per quota unit
├── geometry.py           tiles, and the maths that splits one into four
├── records.py            a Places result → one flat row
├── export.py             csv / xlsx / pdf / json, and converting between them
├── config.py             Settings, and the flags / environment / .env behind them
├── constants.py          endpoints, limits, the field mask, the columns
├── errors.py             PlacesError (fatal) and RetryableError (transient)
├── quota.py              the free tier: SKUs, the ledger, today's share
├── history.py            a line per finished search, behind /sessions
├── ui/
│   ├── theme.py          one console, one palette, one spinner
│   ├── report.py         the ⏺ / ⎿ voice, paths and progress bars
│   ├── tables.py         the results preview and the summary panel
│   └── banner.py         the 5×5 pixel font and the opening screen
└── validate/
    ├── gazetteer.py      is that a real place?
    ├── place_types.py    is that a real Google category?
    └── data/
        └── postal_codes.py   1,080,715 codes, generated — don't hand-edit

countries.json            every country, state and city — edit it to correct a name

countries.json           every country, state and city — edit it to fix a name
tools/build_countries.py  rebuilds countries.json from GeoNames
tools/build_geodata.py    rebuilds postal_codes.py from GeoNames
Business Lead/            where results land
pyproject.toml            metadata, dependencies, the `businesslead` command
run.sh · run.ps1 · run.cmd  venv + deps + run — bash, PowerShell, cmd
```

Each module has its own CLI where that's useful:

```bash
businesslead --usage                                        # or python -m businesslead --usage
python -m businesslead.validate.gazetteer "Austin, TX, USA"
python -m businesslead.validate.place_types --stats
python tools/build_geodata.py
```

## Notes on limits & cost

* One text search returns **at most 60 places** (3 pages × 20). The automatic sweep works
  around this by re-searching saturated areas in quarters — each tile is a separate billed
  query, and the sweep runs until the day's free calls are spent unless `--max-tiles`
  caps it.
* **No business is ever delivered twice.** Every id written into a file is remembered in
  `delivered.db`, so tomorrow's run of the same search returns only what yesterday's
  didn't. When there is nothing new left the run writes no file and exits `1`.
* **And it carries on where it stopped.** A sweep also records the circles it covered and
  the ones still queued (`frontier.json`), so a daily run works through a city a slice at
  a time instead of paying to re-read yesterday's ground. Once the queue empties, the next
  run says the area is mined out without spending a single call — `--resweep` overrides.
* `FIELD_MASK` includes contact and atmosphere fields (phone, website, hours, rating,
  editorial summary), which put every request in the 1,000-a-month SKU. Trimming it moves
  you to a bigger allowance — and `businesslead/quota.py` picks the change up automatically.
* Transient failures retry automatically (4 attempts, exponential backoff); a bad key or
  invalid request fails immediately instead of burning retries.
* Google does not expose email addresses through the Places API.
* Scraping google.com/maps directly violates Google's ToS — this uses the official API.

## Data and licences

Business Lead is MIT licensed — see [LICENSE](LICENSE). The datasets it ships are not ours:

| Data | Source | Licence |
|---|---|---|
| 1,080,715 postal codes, 34k cities, 252 countries | [GeoNames](https://www.geonames.org/) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| 4,880 states / provinces / regions | [pycountry](https://github.com/pycountry/pycountry) (ISO 3166-2) | LGPL-2.1 |
| 478 + 36 place types | [Google Places documentation](https://developers.google.com/maps/documentation/places/web-service/place-types) | Google's terms |

Business data comes from the Google Places API and is subject to
[Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms). Business Lead uses
the official API — it does not scrape google.com/maps, which would violate those terms.
Google does not expose email addresses through the API, so neither does this.

## Security

**Never commit `.env`.** It holds your API key and is git-ignored; `.env.example` is the
one that belongs in the repo. If a key ever leaks, rotate it in the Cloud console
immediately — a Places key is billable.

Two things worth doing on day one:

- Restrict the key (API restrictions → Places API (New) + Geocoding API).
- Set a hard cap: **APIs & Services → Places API (New) → Quotas → Requests per day ≈ 33**.
  Business Lead's own ledger only knows about calls made through this machine; that quota is
  what actually makes overspending impossible.

## Documentation

The full documentation lives at **[darkvertana.github.io/Business-Lead](https://darkvertana.github.io/Business-Lead/)** —
it goes deeper than this README: a data dictionary for all 34 columns, the sweep
algorithm, the quota model, the command reference, and a troubleshooting guide.

It's [docsify](https://docsify.js.org/), so it's just markdown in [`docs/`](docs/) with no
build step. To preview a change locally:

```bash
python3 -m http.server 8000 --directory docs
# then open http://localhost:8000
```

| Page | |
|---|---|
| [Setup](docs/setup.md) | API key, billing, restricting the key, troubleshooting |
| [The guided session](docs/guided.md) | The three questions, the input box, what each one accepts |
| [Commands](docs/commands.md) | Every slash command, with output |
| [The command line](docs/cli.md) | Every flag, recipes, exit codes |
| [Output](docs/output.md) | Formats, and what every column means |
| [Field checks](docs/checks.md) | The offline validation, and the address split |
| [How much it finds](docs/coverage.md) | The adaptive sweep, and never delivering a business twice |
| [The free tier](docs/free-tier.md) | SKUs, the ledger, the daily share |
| [Architecture](docs/architecture.md) | Module map, data flow, where to change things |

## Contributing

Issues and pull requests are welcome. Before opening a PR:

```bash
pip install -e . pyflakes
pyflakes businesslead tools                  # the same check CI runs
python -m businesslead --help                # the CLI still builds
python -m businesslead.validate.gazetteer "Austin, TX, USA"
```

Keep the house style: modules stay single-purpose, comments explain *why* rather than
*what*, and anything that spends an API call says so in the output.
