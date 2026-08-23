# Commands

Any answer starting with `/` is a command. They work at every question in the guided
session, print what they have to say, and hand the question back — nothing you've already
typed is lost.

Arguments work too: `/category health`, `/borrow 40`.

| Command | Aliases | What it does |
|---|---|---|
| `/help` | `/?` | these commands |
| `/back` | `/b` | change the previous answer |
| `/category [word]` | `/categories`, `/cat` | the place types Google accepts |
| `/quota` | `/usage` | what's left of the free tier today |
| `/borrow N` | — | N more calls today, taken from the month |
| `/daily-cap [N]` | `/limit` | set today's whole allowance |
| `/sessions` | `/history` | searches you've already run |
| `/settings` | `/config` | the answers and options in play |
| `/formats` | `/output` | what each file format carries |
| `/where` | `/paths` | where files and records are kept |
| `/open` | `/reveal` | open the output folder |
| `/clear` | `/cls` | clear the screen |
| `/version` | `/v` | what's running, and what it bills as |
| `/reset-quota` | — | forget today's usage (development only) |
| `/quit` | `/exit`, `/q` | leave the session |
## /category — what Google will accept

Without an argument it lists all 19 groups and how many types each holds. With one, it
either opens that group or searches every type and alias:

```
› /category coffee
⏺ Categories matching “coffee”
  ⎿ coffee_roastery              coffee_shop                  coffee_stand
  ⎿ also understood  coffee → coffee_shop, coffee_house → coffee_shop

› /category health
⏺ Health and Wellness · 20 types
  ⎿ chiropractor    dental_clinic    dentist
  ⎿ doctor          drugstore        general_hospital
  ⎿ hospital        massage          massage_spa
  …
```

This is the command to reach for when a category is rejected.

## /quota — what's left

```
⏺ Free tier · Text Search Enterprise + Atmosphere
  ⎿ this month 111 of 1,000 used  ·  889 left  ·  resets 01 Sep 2026
  ⎿ today      111 of 111 used  ·  0 left  ▰▰▰▰▰▰▰▰▰▰
  ⎿ by day     Tue 0   Wed 0   Thu 0   Fri 0   Sat 0   Sun 0   today 111
  ⎿ geocoding  3 of 10,000 used this month
```

## /borrow and /daily-cap — more calls today

`/borrow 40` takes forty more calls from the month's remainder. It can never exceed what
is actually left, and the monthly free tier still holds:

```
✓ Borrowed 40 calls for today
  ⎿ left today       40
  ⎿ left this month  889 of 1,000
```

`/daily-cap N` sets today's whole allowance instead of adding to it — which does nothing
if you have already used more than N. When you're blocked, `/borrow` is the one you want.

## /reset-quota — for development only

Clears LeadMap's own counters so a development loop isn't blocked by the daily share:

```
⚠ Today's counters cleared
  ⎿ text_atmosphere  111 calls forgotten
  ⎿ this clears LeadMap's bookkeeping only — Google has still been called, and
    still counts every one of them
  ⎿ for development. The real limit lives in the Cloud console.
```

**It resets nothing at Google.** Those calls were made and Google still counts them.
Reset repeatedly and you can walk past the free tier into billing — the only thing that
would stop you is the [quota cap in the Cloud console](setup.md#cap-it-in-the-console).

## /sessions — what you've already run

```
⏺ Recent searches · 2 shown
  ⎿ 24 Aug 2026 00:49  barber · Nashik  ·  121 rows  ·  76 calls  ·  output/2026-08-24/barber_nashik.csv
  ⎿ 23 Aug 2026 22:14  coffee shop · Pune  ·  58 rows  ·  14 calls  ·  output/2026-08-23/coffee_shop_pune.pdf
```

Every finished search appends one JSON line to `~/.local/state/leadmap/sessions.jsonl` —
what was searched, how many rows, how many calls, which file. Never the API key.

## Running out of calls doesn't end the session

Searching is what the free tier limits; talking to the tool isn't. When the day's share
is spent, the session drops into a commands-only prompt instead of exiting:

```
✗ Out of free calls for today
  ⎿ today's share is spent · 889 left this month, back tomorrow
  ⎿ /borrow N takes N more calls from the rest of the month
  ⎿ commands still work — /borrow, /reset-quota, /quota, /sessions, /help

› /borrow 40
✓ Borrowed 40 calls for today

✓ 40 calls available — carrying on

⏺ Location
```

## Three of them work from the shell

```bash
leadmap --usage             # /quota   (--verbose adds the day-by-day list)
leadmap --sessions          # /sessions
leadmap --reset-quota       # /reset-quota
```
