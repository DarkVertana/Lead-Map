# Setup

Ten minutes, most of it in the Google Cloud console.

## 1 · A Google API key

1. Open the [Cloud console](https://console.cloud.google.com/) and create a project —
   any name.
2. Enable both APIs. Business Lead needs each for a different thing:
   - **Places API (New)** — the business search itself.
     ([enable](https://console.cloud.google.com/apis/library/places.googleapis.com))
   - **Geocoding API** — turning "Nashik, India" into a point and a radius.
     ([enable](https://console.cloud.google.com/apis/library/geocoding-backend.googleapis.com))
3. **APIs & Services → Credentials → Create credentials → API key.** Copy it.
4. Attach a billing account. This feels alarming, but the free tier below still applies —
   Google simply won't serve these APIs without a billing account on file. Without one
   every request comes back `REQUEST_DENIED`.

### Restrict the key

On the key's page, **API restrictions → Restrict key** → tick *Places API (New)* and
*Geocoding API*. A leaked unrestricted key can be spent against anything in your project.

### Cap it in the console

**APIs & Services → Places API (New) → Quotas → Requests per day → 33.**

This is the only hard guarantee against a bill. Business Lead's own ledger is careful, but it
only knows about calls made through this machine — see
[the free tier](free-tier.md#the-one-guarantee-businesslead-cant-give-you).

## 2 · The key goes in `.env`

```bash
cp .env.example .env
```

```bash
GOOGLE_MAPS_API_KEY=AIza...
```

`.env` is git-ignored and must stay that way. `.env.example` is the one that belongs in
the repo.

**Precedence:** `--api-key` flag › a real environment variable › `.env`. A key exported in
your shell is never silently overridden, and the run header always shows which won:

```
  ⎿ api key    AIzaSy…0099 · from .env
```

### Optional defaults

Any of these can sit in `.env` and be overridden by the matching flag:

| Variable | Same as |
|---|---|
| `PLACES_LOCATION` | `--location` |
| `PLACES_CATEGORY` | `--category` |
| `PLACES_NAME` | `--name` |
| `PLACES_TYPE` | `--type` |
| `PLACES_RADIUS` | `--radius` |
| `PLACES_LANGUAGE` | `--language` |
| `PLACES_REGION` | `--region` |

One has no flag:

| Variable | Does |
|---|---|
| `PLACES_REGION` | the country every search belongs to — `in`, `us`. A location has to name a country; setting this names it once, so `Delhi` passes on its own. |
| `PLACES_EXTRA_LOCATIONS` | names places the offline check doesn't know yet, so a location using one isn't rejected — `Prayagraj:IN, Baner Gaon`. For anything more than a place or two, use the locations file instead. See [Field checks](checks.md#adding-places-it-doesnt-know). |

A few more control where Business Lead keeps things:

| Variable | Default | Moves |
|---|---|---|
| `BUSINESSLEAD_OUTPUT_DIR` | `output` | where results are written |
| `BUSINESSLEAD_USAGE_FILE` | `~/.local/state/businesslead/usage.json` | the usage ledger |
| `BUSINESSLEAD_DELIVERED_FILE` | `~/.local/state/businesslead/delivered.db` | the businesses already handed over |
| `BUSINESSLEAD_FRONTIER_FILE` | `~/.local/state/businesslead/frontier.json` | where each search got to |
| `BUSINESSLEAD_GEOCACHE_FILE` | `~/.local/state/businesslead/geocode.json` | remembered locations, kept for good |
| `BUSINESSLEAD_LOCATIONS_FILE` | `./locations.txt`, else `~/.config/businesslead/locations.txt` | the countries, states and cities you add by hand — `businesslead --locations` prints the path and creates it |

This tool used to be called LeadMap. Anything you set under the old `LEADMAP_`
spelling still works — `BUSINESSLEAD_` wins where you have both — and the ledger,
the history and the rest move themselves out of `~/.local/state/leadmap` the first
time you run it, so nothing you have spent is forgotten.

## 3 · Install

The wrapper does everything — virtualenv, dependencies, run:

```bash
./run.sh
```

Or install the package properly and get a `businesslead` command:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
businesslead --version
```

Python 3.10 or newer. The heaviest dependencies are pandas (tables), reportlab (PDF) and
prompt-toolkit (the input box); the offline datasets ship inside the package, so nothing
is downloaded at runtime.

### On Windows

`run.sh` is a bash script — it needs Git Bash or WSL. Windows has its own launchers
instead, doing exactly the same thing:

```powershell
.\run.ps1                                        # PowerShell
.\run.ps1 -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv
```

```bat
run.cmd                                          :: cmd.exe, or double-click it
run.cmd -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv
```

Or skip the launcher entirely — the package needs no script:

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e .
businesslead
```

Three Windows notes:

- **Use Windows Terminal** if you can. The interface draws with `⏺ ⎿ ▰ ✻` and rounded
  box corners; Windows Terminal renders them and handles the input box properly. The old
  `conhost` console works, but both launchers set the UTF-8 code page for it first.
- **`.\run.ps1` may be blocked** by execution policy. Either run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `run.cmd`, which has
  no such restriction.
- **Files land in the same places**, addressed the Windows way:
  `%LOCALAPPDATA%\businesslead\state\` for the ledger, the search history, the delivered
  businesses and where each sweep got to, `%LOCALAPPDATA%\businesslead\cache\` for the
  gazetteer index, and `Business Lead\` for results.

## 4 · Check it works

None of these spend an API call:

```bash
businesslead --version
businesslead --usage
python -m businesslead.validate.gazetteer "Nashik, India"
python -m businesslead.validate.place_types "chemist"
```

Then the real thing:

```bash
businesslead -l "Nashik, India" -c barber -o test.csv --max-tiles 2
```

Two tiles is a deliberate first run: it proves the key works for about six calls.

## Troubleshooting

**`REQUEST_DENIED … You must enable Billing`**
No billing account on the project. Attach one — the free tier still applies.

**`REQUEST_DENIED … API key not valid` / `This API project is not authorized`**
One of the two APIs isn't enabled, or the key restriction excludes it. Check both.

**`I don't know any place in “…”`**
The offline gazetteer didn't recognise it. Send the same answer twice, or use
`--no-verify`. If the place is genuinely missing — renamed, new, or too small for
GeoNames — add it to your locations file (`businesslead --locations` prints the
path) so it passes every run. See [Field checks](checks.md).

**`name the country — did you mean “…”?`**
A location has to say which country it's in: there are Delhis in three countries
and a Paris in Texas. Add the country, or set `PLACES_REGION=in` in `.env` to name
it once for every search. See [Field checks](checks.md#the-country-is-required).

**`today's free share is spent`**
Working as intended. `/borrow N`, `--daily-cap N`, or wait for tomorrow.
See [the free tier](free-tier.md).

**The session exits the moment it starts, in VS Code**
Your editor is typing its venv-activation command into the terminal, `ctrl+c` first.
Business Lead handles this now — if you're seeing it, you're on an old checkout.

**`no businesses matched`**
Usually too narrow a filter. Drop `--name-match`, widen `--radius`, or check the
category with `/category`.

**Nothing prints while it searches, in a pipe or cron**
The live progress line needs a terminal. The `⏺` step lines still print; `--verbose`
adds the per-tile log.
