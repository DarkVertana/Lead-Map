# Staying inside the free tier

Google retired the $200 monthly credit in March 2025. Every SKU now has its own monthly
allowance of free calls, and the call after it is billed. LeadMap is built so that call
never happens by accident.

## The allowances

Checked against [Google's pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
on 2026-08-23:

| SKU | Free / month | Then |
|---|---|---|
| Geocoding | 10,000 | $5 / 1k |
| Text Search Essentials (IDs only) | unlimited | free |
| Text Search Essentials | 10,000 | $32 / 1k |
| Text Search Pro | 5,000 | $32 / 1k |
| Text Search Enterprise | 1,000 | $35 / 1k |
| **Text Search Enterprise + Atmosphere** | **1,000** | $40 / 1k |

## What your field mask costs

A request bills at **the highest tier any field in its mask belongs to**. LeadMap asks for
phone, website, rating and review count (Enterprise) plus the editorial summary
(Atmosphere), so it bills at the last row: **1,000 free searches a month**.

One geocode per run, and up to three calls per tile — so roughly **330 tiles, or a dozen
full 25-tile sweeps, a month at no cost**.

`quota.py` works the SKU out from `FIELD_MASK` itself, so trimming the mask raises the
allowance it enforces. `--usage` shows what you'd have to give up:

```
  a bigger free allowance would mean giving up fields:
     5,000/month as Text Search Pro — drop editorialSummary, nationalPhoneNumber, rating …
    10,000/month as Text Search Essentials — drop businessStatus, displayName, websiteUri …
```

Which is not a trade worth making for a lead tool — phone and website *are* the product.

?> **Worth knowing:** `editorialSummary` is the single field pushing you from *Enterprise*
($35/1k) to *Enterprise + Atmosphere* ($40/1k), and on small businesses it comes back
empty every time — 0 of 121 rows on a real Nashik run. Same 1,000 free either way, so it
costs nothing today; drop it from `FIELD_MASK` and you'd save 12.5% if you ever go paid.

## The month, split across its days

Today's share is **what's left of the month divided by the days remaining in it**. Unused
days roll forward, so nothing is stranded:

| Day of a fresh September | Today's share |
|---|---|
| 1 Sep | 33 requests |
| 10 Sep | 47 |
| 20 Sep | 90 |
| 25 Sep | 166 |
| 30 Sep | 1,000 (whatever is left) |

Spend 900 early and it collapses accordingly — 4/day on the 10th, 100 on the last day.

The unit is **API requests**, not searches: one geocode per run, one request per page of
a tile. So 33 requests is about eleven dense tiles.

## The ledger

Every call is written to `~/.local/state/leadmap/usage.json`:

```json
{
 "days": { "2026-08-24": { "geocoding": 2, "text_atmosphere": 111 } },
 "version": 1
}
```

- Saved in a `finally`, so `ctrl+c` still records what was spent.
- Retries and 429/5xx responses are refunded — Google doesn't bill those.
- `LEADMAP_USAGE_FILE` moves it, which is how the test suite avoids touching real numbers.

## When it runs out

It stops rather than spending. Mid-sweep:

```
  ⎿ ■ today's share of the free tier is used up (111 of 111 calls) — 889 left this
    month, back tomorrow or use --daily-cap to borrow from it
```

The partial results are kept and the file is written. At startup, the session drops into
a [commands-only prompt](commands.md#running-out-of-calls-doesnt-end-the-session) so you
can `/borrow`, `/quota` or `/sessions` your way forward.

There is no flag that spends money.

## Borrowing, and the honest limits

| Want | Do |
|---|---|
| More calls today | `/borrow 40` in the session, or `--daily-cap N` on the CLI |
| A different monthly ceiling | `--monthly-cap N` |
| To ignore today's counter entirely | `/reset-quota` — **development only** |

`/borrow` is honest: it takes from the month's remainder and can't exceed it.
`/reset-quota` is not — it clears LeadMap's bookkeeping while Google's meter keeps
running.

## The one guarantee LeadMap can't give you

The ledger only counts calls made **through this machine**. Use the same key from another
laptop, a script, or a colleague's checkout, and the real total is higher than anything
LeadMap knows about.

The guarantee lives in the Google Cloud console:

> **APIs & Services → Places API (New) → Quotas → Requests per day → 33**

Set that and you cannot be billed, whatever any client does. Do it as well as this, not
instead of it.
