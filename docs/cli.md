# The command line

Every option below works in one-shot mode. Passing any of `--location`, `--name`,
`--category` or `--output` skips the guided session automatically.

```bash
leadmap -l "Nashik, India" -c barber -o barber_nashik.csv
```

Prefer `./run.sh` if you'd rather not think about the virtualenv — it takes the same
flags and forwards them straight through.

## Reference

### What to search for

| Flag | Default | What it does |
|---|---|---|
| `--location`, `-l` | — | Area to search, e.g. "Austin, TX" or "560001, Bangalore". |
| `--name`, `-n` | — | Optional business name, e.g. "Starbucks". |
| `--category`, `-c` | — | Business category, e.g. "coffee shop", "dentist". |
| `--type` | — | Restrict to a Places type id, e.g. restaurant, dentist. |
| `--output`, `-o` | — | Output file: .csv, .xlsx or .json. |

### How far to go

| Flag | Default | What it does |
|---|---|---|
| `--radius` | — | Search radius in metres (default: the geocoded area; max 50000). |
| `--grid` | `1` | Split the area into GRID x GRID sub-searches to exceed the 60-result cap. |
| `--max_tiles` | `25` | Cap the automatic sweep at this many searches of the area. |
| `--max_results` | — | Stop after this many unique businesses. |

### Filtering

| Flag | Default | What it does |
|---|---|---|
| `--min_rating` | — | Only places rated at least this. |
| `--open_now` | `False` | Only places open right now. |
| `--name_match` | `False` | With --name: keep only results whose name contains it. |
| `--with_website_only` | `False` | Drop results with no website. |
| `--operational_only` | `False` | Drop closed businesses. |

### Checks

| Flag | Default | What it does |
|---|---|---|
| `--verify-location/--no-verify-location` | `True` | Check the location and category against the offline data first. |

### Credentials

| Flag | Default | What it does |
|---|---|---|
| `--api_key` | — | Key override; normally comes from .env. |
| `--env_file` | — | Path to the .env file (default: nearest ./.env). |
| `--language` | — | Language code, e.g. en, hi, es. |
| `--region` | — | Region code, e.g. us, in, gb. |

### Free tier

| Flag | Default | What it does |
|---|---|---|
| `--daily_cap` | — | Calls allowed today (default: this month's free calls ÷ days left). |
| `--monthly_cap` | — | Free calls a month (default: Google's allowance for our field mask). |
| `--usage` | `False` | Show what's left of the free tier and exit. |
| `--sessions` | `False` | List the searches already run, and exit. |
| `--reset_quota` | `False` | Forget today's recorded usage (development only). |

### Files

| Flag | Default | What it does |
|---|---|---|
| `--json_out` | — | Also dump the raw API responses to this JSON file. |
| `--convert` | — | Rewrite an existing results file in other formats (no search, no API calls). |
| `--to` | `pdf,excel,json` | Formats for --convert: csv, excel, pdf, json. |
| `--pdf_all` | `False` | Put every column in the PDF, not just the useful dozen. |

### Output style

| Flag | Default | What it does |
|---|---|---|
| `--chat/--no-chat` | — | Ask for location, category and name one question at a time. Default: on when you run with no search options. |
| `--verbose`, `-v` | `False` | Log every tile of the sweep instead of one progress bar. |
| `--quiet`, `-q` | `False` | Suppress all output. |
| `--no_color` | `False` | Disable colour. |
| `--version` | `False` | Show the version and exit. |
## Exit codes

| Code | Meaning |
|---|---|
| `0` | The search ran. A file was written, or the search legitimately found nothing. |
| `1` | It refused before spending: no API key, a rejected location or category, an unwritable format, or no free calls left. |
| `130` | You interrupted it (`ctrl+c` twice, or `/quit`). Partial results are still written. |

## Recipes

**A whole city, exhaustively**

```bash
leadmap -l "Pune, India" -c "dentist" -o dentists.xlsx --max-tiles 40
```

`--max-tiles` is the ceiling on how hard it digs. 25 is the default; 40 buys deeper
coverage of a dense city at up to 120 API calls.

**Every branch of one chain**

```bash
leadmap -l "Bengaluru, India" -n "Apollo Pharmacy" -o apollo.csv --name-match
```

`--name-match` keeps only results whose name really contains what you asked for, which
drops the loosely related places Google likes to include.

**Only leads worth calling**

```bash
leadmap -l "Austin, TX" -c "coffee shop" -o cafes.csv \
        --min-rating 4.0 --with-website-only --operational-only
```

`--min-rating` is applied by Google; the other two are applied locally, after the
results come back.

**A list of towns, one file each**

```bash
for city in Nashik Pune Nagpur Aurangabad; do
  leadmap -l "$city, India" -c "gym" -o "gyms_${city}.csv" --max-tiles 10 || break
done
```

The `|| break` matters: when the daily free share runs out, LeadMap exits `1` rather
than spending, and the loop stops instead of hammering a wall.

**Nightly, from cron**

```cron
0 3 * * *  cd ~/projects/leadmap && ./run.sh -l "Nashik, India" -c "new restaurant" \
             -o "restaurants.csv" --max-tiles 8 --quiet >> ~/leadmap.log 2>&1
```

`--quiet` silences everything but errors. The dated output folder keeps each night's
file separate, so nothing is overwritten.

**Convert what you already have**

```bash
leadmap --convert output/2026-08-24/barber_nashik.csv --to pdf,excel
```

No search, no API call, no quota. See [Output](output.md#changing-format-later).

## Non-interactive behaviour

In a pipe, a cron job or a CI runner there's no terminal to ask questions with, so:

- the guided session never starts — `--guided` in a non-tty is an error, not a prompt;
- missing values are an error rather than a question: *"missing required input(s):
  location, output"*;
- the spinner and progress bar go quiet, but the `⏺` step lines still print (use
  `--quiet` to silence those too).
