# How it's put together

One package, laid out by job. Nothing is longer than it needs to be — the largest module
is the search itself at ~320 lines.

```
leadmap/
├── cli.py                flags in; a search, a conversion or a usage report out
├── session.py            the guided session: questions, input box, commands
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
```

## What happens during a run

```
  leadmap -l "Nashik" -c barber -o leads.csv
        │
        ▼
  cli.main ──── config: flags › environment › .env ──────────────┐
        │                                                        │
        ▼                                                        ▼
  search.run                                            Settings (one object,
        │                                                passed everywhere)
        ├─▶ validate.gazetteer     "Nashik" — a real place?      offline
        ├─▶ validate.place_types   "barber" → barber_shop        offline
        ├─▶ quota.Quota            any calls left today?         offline
        │
        ├─▶ places.geocode         1 call  ──▶ lat, lng, radius
        │
        ├─▶ the sweep ─── geometry.build_tiles ──┐
        │      │                                 │
        │      ├─▶ places.search_text   1–3 calls per tile
        │      ├─▶ records.to_row       result → 33 columns
        │      └─▶ geometry.split_tile  if the tile came back full ──┘
        │
        ├─▶ export.write_dataframe   csv · xlsx · pdf · json
        ├─▶ history.record           one line, for /sessions
        └─▶ ui.tables                the preview and the summary
```

Every step before the geocode is free and offline. That ordering is the whole design: the
expensive thing happens last, and only if everything cheap agreed it should.

## Where to change things

**Add a column.** Add the field to `FIELD_MASK` in `constants.py`, pull it out in
`records.to_row`, and add its name to `COLUMNS`. If the new field belongs to a higher SKU
tier, `quota.sku_for_mask` notices and the enforced free allowance drops — that's
deliberate.

**Change what the PDF shows.** `PDF_COLUMNS` in `export.py`. Widths come from
`COLUMN_WEIGHTS` in the same file; the font shrinks automatically as columns are added.

**Tune the sweep.** `SATURATED`, `MIN_TILE_RADIUS` and `DEFAULT_TILE_BUDGET` in
`constants.py`.

**Add a slash command.** Write a `_cmd_*` function in `session.py` and add one `Command`
to the `COMMANDS` list. `/help` builds itself from that list.

**Add a category alias.** `ALIASES` in `validate/place_types.py` — the mapping from what
people type to what Google accepts.

**Refresh the postal codes.** `python tools/build_geodata.py` re-downloads them from
GeoNames and rewrites `validate/data/postal_codes.py`.

## The libraries

| Library | Used for |
|---|---|
| `requests` | HTTP with connection pooling and proper TLS |
| `tenacity` | Automatic retry with exponential backoff on 429 / 5xx / network errors |
| `rich` | Panels, tables, spinners, colour |
| `typer` | The CLI and its `--help` |
| `prompt-toolkit` | The inline input box of the guided session |
| `questionary` | Line prompts on the `--no-guided` path |
| `pandas` (+`openpyxl`) | Sorting, stats and CSV / XLSX / JSON output |
| `reportlab` | The PDF table |
| `geonamescache` | Offline continents, countries and cities |
| `pycountry` | Offline states / provinces / regions |
| `python-dotenv` | `.env` loading |

## Data and licences

LeadMap is MIT licensed. The datasets it ships are not ours:

| Data | Source | Licence |
|---|---|---|
| 1,080,715 postal codes, 34k cities, 252 countries | [GeoNames](https://www.geonames.org/) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| 4,880 states / provinces / regions | [pycountry](https://github.com/pycountry/pycountry) (ISO 3166-2) | LGPL-2.1 |
| 478 + 36 place types | [Google Places documentation](https://developers.google.com/maps/documentation/places/web-service/place-types) | Google's terms |

Business data comes from the Google Places API and is subject to the
[Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms). LeadMap uses
the official API — it does not scrape google.com/maps, which would violate those terms.

## Contributing

Issues and pull requests are welcome.

```bash
pip install -e . pyflakes
pyflakes leadmap tools                        # the check CI runs
python -m leadmap --help                      # the CLI still builds
python -m leadmap.validate.gazetteer "Austin, TX"
```

House style, such as it is: modules stay single-purpose, comments explain *why* rather
than *what*, and anything that spends an API call says so in the output.
