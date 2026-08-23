# How much it finds

One Google text search returns **at most 60 places**, however many are really there. That
cap is the central problem this tool solves.

## The sweep

LeadMap searches the area, and whenever a search comes back full — a sure sign Google
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
| Tile budget | 25, `--max-tiles` | Each tile is billed. This is the ceiling on spend. |
| Result cap | none, `--max-results` | Stop early on count instead. |
| Dedupe | `place_id` | The same shop found by four tiles is one row. |

Empty countryside costs one search. A dense high street keeps subdividing until it runs
out of ceiling or budget.

## It never pretends

If the budget stops the sweep while areas still had more to give, it says so:

```
  ⎿ ! stopped at the 25-tile cap · 19 areas still had more to give — raise --max-tiles
```

and the summary always reports what was actually spent:

```
│ tiles swept   25         │
│ api requests  76         │
```

## Tuning it

**More coverage:** raise `--max-tiles`. A dense city keeps rewarding you up to roughly 40;
past that you're mostly re-finding the same places.

**Predictable spend:** `--grid N` pins a fixed N×N layout and turns the adaptive sweep
off. `--grid 2` is four tiles, always.

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
| default | ≤ 25 | 75 | 30–76 |
| `--max-tiles 40` | ≤ 40 | 120 | 60–110 |

At 1,000 free calls a month, the default sweep is about a dozen searches a month at no
cost. See [Staying inside the free tier](free-tier.md).

## Notes on limits

- One text search returns **at most 60 places** (3 pages × 20). Everything above is
  working around that.
- Transient failures retry automatically (4 attempts, exponential backoff); a bad key or
  an invalid request fails immediately rather than burning retries.
- `ctrl+c` mid-sweep keeps what was found and writes the file.
- Google does not expose email addresses through the Places API.
- Scraping google.com/maps directly violates Google's terms — this uses the official API.
