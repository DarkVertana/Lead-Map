# The command line

Every option below works in one-shot mode. Passing any of `--location`, `--name`,
`--category` or `--output` skips the guided session automatically.

```bash
businesslead -l "Nashik, India" -c barber -o barber_nashik.csv
```

Prefer `./run.sh` if you'd rather not think about the virtualenv — it takes the same
flags and forwards them straight through.

## Reference

### What to search for

| Flag | Default | What it does |
|---|---|---|
| `--location`, `-l` | — | Area to search, e.g. "Austin, TX, USA" or "560001, Bangalore, India". |
| `--name`, `-n` | — | Optional business name, e.g. "Starbucks". |
| `--category`, `-c` | — | Business category, e.g. "coffee shop", "dentist". |
| `--type` | — | Restrict to a Places type id, e.g. restaurant, dentist. |
| `--output`, `-o` | — | Output file: .csv, .xlsx or .json. |

### How far to go

| Flag | Default | What it does |
|---|---|---|
| `--radius` | — | Search radius in metres (default: the geocoded area; max 50000). |
| `--max_tiles` | — | Cap the sweep at this many searches (default: as many as today's free calls allow). |
| `--max_results` | — | Stop after this many unique businesses. |
| `--include-seen` | `False` | Write businesses earlier runs delivered (default: only what's new). |
| `--forget-seen` | `False` | Forget delivered businesses and part-searched areas, and exit. |
| `--resweep` | `False` | Search the whole area again instead of carrying on where the last run stopped. |

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
| `--daily_cap` | — | Calls allowed today (default: this month's free calls ÷ days left). `BUSINESSLEAD_DAILY_CAP` in `.env` sets it permanently. |
| `--monthly_cap` | — | Free calls a month (default: Google's allowance for our field mask). `BUSINESSLEAD_MONTHLY_CAP` in `.env` sets it permanently. |
| `--usage` | `False` | Show what's left of the free tier and exit. |
| `--sessions` | `False` | List the searches already run, and exit. |
| `--locations` | `False` | Show the countries, states and cities you've added by hand, creating the file if there isn't one, and exit. |
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
| `--chat/--no-chat` | — | Ask for the file, location, category and name one question at a time. Default: on when you run with no search options. |
| `--verbose`, `-v` | `False` | Log every tile of the sweep instead of one progress bar. |
| `--quiet`, `-q` | `False` | Suppress all output. |
| `--no_color` | `False` | Disable colour. |
| `--version` | `False` | Show the version and exit. |
## Exit codes

| Code | Meaning |
|---|---|
| `0` | The search ran. A file was written, or the search legitimately found nothing. |
| `1` | It refused before spending: no API key, a rejected location or category, an unwritable format, no free calls left, or the area has already been swept to the end — or it searched and every match had already been delivered, so there was no unique data to write. |
| `130` | You interrupted it (`ctrl+c` twice, or `/quit`). Partial results are still written. |

## Recipes

**A whole city, exhaustively**

```bash
businesslead -l "Pune, India" -c "dentist" -o dentists.xlsx
```

Nothing caps the sweep but today's free calls: it keeps subdividing dense ground until
the area stops giving or the day's share is gone. `--max-tiles 8` puts a ceiling back on
when you'd rather spend less than the day allows.

**Every branch of one chain**

```bash
businesslead -l "Bengaluru, India" -n "Apollo Pharmacy" -o apollo.csv --name-match
```

`--name-match` keeps only results whose name really contains what you asked for, which
drops the loosely related places Google likes to include.

**Only leads worth calling**

```bash
businesslead -l "Austin, TX, USA" -c "coffee shop" -o cafes.csv \
        --min-rating 4.0 --with-website-only --operational-only
```

`--min-rating` is applied by Google; the other two are applied locally, after the
results come back.

**A list of towns, one file each**

```bash
for city in Nashik Pune Nagpur Aurangabad; do
  businesslead -l "$city, India" -c "gym" -o "gyms_${city}.csv" --max-tiles 10 || break
done
```

The `|| break` matters: when the daily free share runs out, Business Lead exits `1` rather
than spending, and the loop stops instead of hammering a wall.

**Nightly, from cron**

```cron
0 3 * * *  cd ~/projects/businesslead && ./run.sh -l "Nashik, India" -c "new restaurant" \
             -o "restaurants.csv" --max-tiles 8 --quiet >> ~/businesslead.log 2>&1
```

`--quiet` silences everything but errors. The dated output folder keeps each night's
file separate, so nothing is overwritten.

**Map coverage cheaply, then enrich**

```bash
businesslead --plan pro -l "Nashik, India" -c gym -o gyms_survey.csv --max-tiles 40
businesslead -l "Nashik, India" -n "Gold's Gym" -o golds.csv        # full plan, phone + website
```

`--plan pro` bills against a separate 5,000-a-month allowance instead of the 1,000 one,
at the cost of the phone, website and rating columns. Good for answering *how many, and
where* before spending the expensive allowance on the shortlist.

**Convert what you already have**

```bash
businesslead --convert Business Lead/barber_nashik.csv --to pdf,excel
```

No search, no API call, no quota. See [Output](output.md#changing-format-later).

## Non-interactive behaviour

In a pipe, a cron job or a CI runner there's no terminal to ask questions with, so:

- the guided session never starts — `--guided` in a non-tty is an error, not a prompt;
- missing values are an error rather than a question: *"missing required input(s):
  location, output"*;
- the spinner and progress bar go quiet, but the `⏺` step lines still print (use
  `--quiet` to silence those too).
