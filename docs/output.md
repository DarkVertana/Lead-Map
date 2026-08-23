# Output

Every search writes one file. The format follows the extension you give it, and a bare
filename lands in a dated folder.

```
output/2026-08-24/barber_nashik.csv
```

`LEADMAP_OUTPUT_DIR` moves the root. A name with a directory in it — `~/Desktop/leads.pdf`,
`reports/q3.xlsx` — is left exactly where you put it.

## Formats

| Format | Columns | Good for |
|---|---|---|
| `.csv` | all 33 | Excel, Sheets, importing anywhere. Written with a UTF-8 BOM so Excel opens it without the encoding dance. |
| `.xlsx` | all 33 | A real workbook, one sheet named `businesses`. |
| `.json` | all 33 | Feeding another program. One object per business, `null` for blanks. |
| `.pdf` | the essential 12 | Reading, printing, sending to someone who won't open a spreadsheet. A4 landscape, header repeated on every page. |

The PDF carries **name, type, phone, website, street, area, city, state, postcode,
rating, reviews, status** — and says so in its own header line. `--pdf-all` puts all 33
in instead, at roughly 4pt on A3, which is legible but not pleasant.

## The columns

33 per row, in reading order.

### Who they are

| Column | Example | Notes |
|---|---|---|
| `name` | `Spikes & Curls` | The display name Google shows on the listing. |
| `category` | `barber` | What **you** searched for, echoed back — useful when merging files. |
| `primary_type` | `Hair Salon` | Google's own primary type, in words. |
| `all_types` | `barber_shop, hair_salon, spa` | Every type Google tags the place with, comma separated. |

### How to reach them

| Column | Example | Notes |
|---|---|---|
| `phone` | `077738 77781` | National format, as dialled locally. Empty on ~20% of listings. |
| `international_phone` | `+91 77738 77781` | E.164-ish, for dialling from abroad or importing into a CRM. |
| `website` | `https://spikesncurls.in/` | Empty far more often than the phone — 28/121 on a typical Indian small-business run. |

Google does **not** expose email addresses through the Places API, so there is no email
column. Anything claiming otherwise is scraping, which breaks Google's terms.

### Where they are

| Column | Example | Notes |
|---|---|---|
| `street` | `Shop No. 4, Ace Residences, near RD Circle` | The building/street line. From components where Google has them, parsed out of the printed address where it doesn't. |
| `area` | `Govind Nagar` | The locality inside the city — sublocality, neighbourhood or colony. |
| `city` | `Nashik` | Locality, falling back to postal town or the district. |
| `district` | `Nashik Division` | Administrative area level 2, where one exists. |
| `state` | `Maharashtra` | Administrative area level 1. |
| `state_code` | `MH` | The short form of the same. |
| `postal_code` | `422009` | PIN / ZIP / postcode. |
| `country` | `India` | Full country name. |
| `formatted_address` | `Shop No. 4, …, Nashik, Maharashtra 422009, India` | Google's printed one-liner, untouched, so nothing is lost in the split. |
| `latitude` | `20.0073032` | Decimal degrees. |
| `longitude` | `73.7652907` | Decimal degrees. |

See [Field checks → the address split](checks.md) for why this needs two strategies.

### How they're doing

| Column | Example | Notes |
|---|---|---|
| `rating` | `4.8` | Average, 1–5. Blank when nobody has rated the place. |
| `reviews_count` | `2537` | How many ratings that average rests on — the number that actually tells you something. |
| `price_level` | `Moderate` | Google's bucket: Free, Inexpensive, Moderate, Expensive, Very Expensive. |
| `price_range` | `INR 200 – INR 600` | The explicit range, where Google has one. Rarer, but more useful. |
| `business_status` | `OPERATIONAL` | Also `CLOSED_TEMPORARILY`, `CLOSED_PERMANENTLY`. Filter with `--operational-only`. |
| `opened` | `2019-04-01` | Opening date, where Google knows it. A good proxy for "new business". |

### When they're open

| Column | Example | Notes |
|---|---|---|
| `opening_hours` | `Monday: 10:00 AM – 9:00 PM \| Tuesday: …` | All seven days in one cell, pipe separated. |
| `open_now` | `True` | Whether it was open **at the moment of the search**. Goes stale immediately — don't treat it as data. |

### Links and provenance

| Column | Example | Notes |
|---|---|---|
| `google_maps_url` | `https://maps.google.com/?cid=15395…` | The listing itself. |
| `reviews_url` | `https://maps.google.com/…reviews` | Straight to the reviews tab. |
| `directions_url` | `https://maps.google.com/…dir` | Straight to directions. |
| `summary` | `Cosy salon offering …` | Google's editorial summary. Usually empty for small businesses — see the note in [Free tier](free-tier.md#what-your-field-mask-costs). |
| `place_id` | `ChIJn_pd_RHr3TsR8pQsW7k1qdU` | Google's stable id. Rows are deduplicated on this. |
| `search_query` | `barber in Nashik, Maharashtra, India` | The exact text sent to Google. |
| `searched_name` | `Apollo Pharmacy` | The `--name` you gave, if any. |

Rows are deduplicated by `place_id` and sorted by `reviews_count` descending, so the
best-known businesses are at the top of the file.

## Changing format later

A finished file can be rewritten in any other format without searching again — it reads
the rows off disk, so no API call and no quota:

```bash
leadmap --convert barber_nashik.csv                 # → .pdf, .xlsx and .json
leadmap --convert barber_nashik.csv --to pdf        # just the one
leadmap --convert leads.xlsx --to "csv, json"
leadmap --convert leads.csv --to pdf --pdf-all      # every column in the PDF
```

```
⏺ Converting output/2026-08-24/barber_nashik.csv
  ⎿ rows       121 × 33 columns
  ⎿ ✓ pdf   output/2026-08-24/barber_nashik.pdf
  ⎿ ✓ xlsx  output/2026-08-24/barber_nashik.xlsx

  no API calls — the data came off disk
```

It reads `.csv`, `.xlsx` and `.json`, and writes any of those plus `.pdf`. New files land
beside the original. In the guided session the same thing is offered automatically once a
search finishes — see [The guided session](guided.md#another-copy).

## Merging several runs

Every file has the same 33 columns and `place_id` is stable, so files combine cleanly:

```python
import pandas as pd, glob

frames = [pd.read_csv(path, encoding="utf-8-sig") for path in glob.glob("output/*/*.csv")]
leads = pd.concat(frames).drop_duplicates("place_id").sort_values("reviews_count",
                                                                  ascending=False)
leads.to_csv("all_leads.csv", index=False, encoding="utf-8-sig")
```
