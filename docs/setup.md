# Setup

Ten minutes, most of it in the Google Cloud console.

## 1 · A Google API key

1. Open the [Cloud console](https://console.cloud.google.com/) and create a project —
   any name.
2. Enable both APIs. LeadMap needs each for a different thing:
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

This is the only hard guarantee against a bill. LeadMap's own ledger is careful, but it
only knows about calls made through this machine — see
[the free tier](free-tier.md#the-one-guarantee-leadmap-cant-give-you).

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
| `PLACES_GRID` | `--grid` |
| `PLACES_LANGUAGE` | `--language` |
| `PLACES_REGION` | `--region` |

Two more control where LeadMap keeps things:

| Variable | Default | Moves |
|---|---|---|
| `LEADMAP_OUTPUT_DIR` | `output` | where results are written |
| `LEADMAP_USAGE_FILE` | `~/.local/state/leadmap/usage.json` | the usage ledger |

## 3 · Install

The wrapper does everything — virtualenv, dependencies, run:

```bash
./run.sh
```

Or install the package properly and get a `leadmap` command:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
leadmap --version
```

Python 3.10 or newer. The heaviest dependencies are pandas (tables), reportlab (PDF) and
prompt-toolkit (the input box); the offline datasets ship inside the package, so nothing
is downloaded at runtime.

## 4 · Check it works

None of these spend an API call:

```bash
leadmap --version
leadmap --usage
python -m leadmap.validate.gazetteer "Nashik, India"
python -m leadmap.validate.place_types "chemist"
```

Then the real thing:

```bash
leadmap -l "Nashik, India" -c barber -o test.csv --max-tiles 2
```

Two tiles is a deliberate first run: it proves the key works for about six calls.

## Troubleshooting

**`REQUEST_DENIED … You must enable Billing`**
No billing account on the project. Attach one — the free tier still applies.

**`REQUEST_DENIED … API key not valid` / `This API project is not authorized`**
One of the two APIs isn't enabled, or the key restriction excludes it. Check both.

**`I don't know any place in “…”`**
The offline gazetteer didn't recognise it. Send the same answer twice, or use
`--no-verify`. See [Field checks](checks.md).

**`today's free share is spent`**
Working as intended. `/borrow N`, `--daily-cap N`, or wait for tomorrow.
See [the free tier](free-tier.md).

**The session exits the moment it starts, in VS Code**
Your editor is typing its venv-activation command into the terminal, `ctrl+c` first.
LeadMap handles this now — if you're seeing it, you're on an old checkout.

**`no businesses matched`**
Usually too narrow a filter. Drop `--name-match`, widen `--radius`, or check the
category with `/category`.

**Nothing prints while it searches, in a pipe or cron**
The live progress line needs a terminal. The `⏺` step lines still print; `--verbose`
adds the per-tile log.
