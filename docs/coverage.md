# How much it finds

One Google text search returns **at most 60 places**, however many are really there. That
cap is the central problem this tool solves.

## The sweep

Business Lead searches the area, and whenever a search comes back full — a sure sign Google
truncated it — it splits that circle into four and searches each one, over and over,
until the results stop hitting the ceiling.

```
        one search of the whole area           full → split it
        ┌───────────────────────┐              ┌───────┬───────┐
        │                       │              │  60   │  33   │
        │          60           │   ────────▶  ├───────┼───────┤
        │                       │              │  41   │  12   │
        └───────────────────────┘              └───────┴───────┘
                                                   ▲
                                          still full → split again
```

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

## The rules it follows

| Rule | Value | Why |
|---|---|---|
| Saturated | ≥ 55 of 60 places | Anything that full has almost certainly been truncated. |
| Smallest tile | 300 m radius | Below this, splitting stops finding anything new. |
| Tile budget | today's free calls, or `--max-tiles` | Each tile is billed, so the day's share is the ceiling. |
| Result cap | none, `--max-results` | Stop early on count instead. |
| Dedupe | `place_id` | The same shop found by four tiles is one row. |
| Never twice | `delivered.db` | A business delivered by any earlier run is left out. |

Empty countryside costs one search. A dense high street keeps subdividing until today's
free calls are gone.

## It never pretends

If the day's calls stop the sweep while areas still had more to give, it says so:

```
  ⎿ ! 19 areas still had more to give · today's free calls are spent — the rest keeps until tomorrow
```

and the summary always reports what was actually spent:

```
│ tiles swept     25                          │
│ api requests    76                          │
│ never repeated  312 businesses delivered so far │
```

## No business twice

Every place id written into a file is remembered in `delivered.db` (a SQLite table next
to the usage ledger — half a million businesses is 56 MB and opens in a millisecond). Later searches drop anything already in it, whatever query finds it again — so
running the same search tomorrow returns tomorrow's new businesses and nothing else.

When a search finds matches but every one has been delivered before, no file is written
and the run exits `1`:

```
✗ No unique data left — all 143 matches here were delivered by an earlier run.
```

`/seen` in the guided session shows how many have been handed over and when; `/seen
forget` (or `--forget-seen`) empties the record, and `--include-seen` writes the repeats
out anyway without clearing anything.

## It carries on where it stopped

Uniqueness alone wouldn't save a call: yesterday's circles would be searched again, their
results recognised and thrown away. So a sweep also writes down where it got to —
the circles it covered and the ones still queued — under a fingerprint of the search
(location, category, name, region, language, radius), in `frontier.json`.

Ask for the same thing tomorrow and it picks that queue back up:

```
  ⎿ carrying on 19 areas still queued  ·  22 searched since 22 Aug 2026
```

So a daily run on the same inputs works through a city a slice at a time — every day's
file is new businesses, and no call is spent re-reading ground already covered.

Two things end a sweep early and keep the rest for next time: the day's calls running out,
and ten searches in a row that turn up nothing new (`DRY_TILES`) — a picked-over area
stops eating the allowance:

```
  ⎿ ! 10 searches in a row turned up nothing new — stopping with 63 calls still yours
```

When the queue finally empties, the area is mined out, and the next run says so without
spending anything at all:

```
✗ Nothing left to search here — this area was swept to the end on 24 Aug 2026.
```

`--resweep` starts that one search over from the whole area; `--forget-seen` clears both
records — every delivered business and every part-searched area.

## Tuning it

**More coverage:** nothing to raise — the sweep already digs until today's free calls
run out. `/borrow N` or `--daily-cap N` takes more of the month's allowance for today.

**Predictable spend:** `--max-tiles N` caps the sweep at N searches of the area, so a run
costs at most 3N calls.

**A hard stop on volume:** `--max-results 200` ends the search once 200 unique businesses
are in hand, whatever the sweep was doing.

**A smaller area:** `--radius 2000` searches a 2 km circle instead of the whole geocoded
region. Often better than more tiles — a tight radius on a specific neighbourhood beats a
loose one on a metro.

## What it costs

Each tile is one to three billed requests (one per page of results). So:

| Setting | Tiles | Worst-case requests | Realistic |
|---|---|---|---|
| `--max-tiles 8` | ≤ 8 | 24 | 10–18 |
| `--max-tiles 40` | ≤ 40 | 120 | 60–110 |
| default | as many as fit | today's whole share | today's whole share |

The default spends what the day has and no more: at 1,000 free calls a month that's
roughly 30 a day, and a dense city will use all of them. See
[Staying inside the free tier](free-tier.md).

## Notes on limits

- One text search returns **at most 60 places** (3 pages × 20). Everything above is
  working around that.
- Transient failures retry automatically (4 attempts, exponential backoff); a bad key or
  an invalid request fails immediately rather than burning retries.
- `ctrl+c` mid-sweep keeps what was found and writes the file.
- Google does not expose email addresses through the Places API.
- Scraping google.com/maps directly violates Google's terms — this uses the official API.
