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
| `/switch [plan]` | `/plan` | change which SKU searches bill at |
| `/borrow N` | — | N more calls today, taken from the month |
| `/daily-cap [N]` | `/limit` | set today's whole allowance |
| `/sessions` | `/history` | searches you've already run |
| `/seen [forget]` | `/delivered` | businesses already handed over — never sent twice |
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

## /switch — trade fields for a bigger allowance

Google prices a search by the most expensive field in it, so the free allowance isn't a
setting you can turn up: it's a consequence of what you ask for. `/switch` is that lever.

`/switch` on its own opens a picker — arrow keys, not typing:

```
⏺ Quota plans · on Text Search Enterprise + Atmosphere
╭────────────────────────────────────────────────────────────────────────────────────╮
│   atmosphere     1,000/mo ·    889 left   everything — phone, website, rating, …   │
│   enterprise     1,000/mo ·  1,000 left   drops the editorial summary, empty on …  │
│ ❯ pro            5,000/mo ·  5,000 left   drops phone, website, rating, reviews, … │
│   essentials    10,000/mo · 10,000 left   drops the business name too — ids, …     │
│   ids           unlimited                 place ids only, for counting or …        │
╰────────────────────────────────────────────────────────────────────────────────────╯
  ↑↓ to move   ·   enter to switch   ·   esc to keep this plan
```

`↑`/`↓` (or `tab`, or `ctrl+n`/`ctrl+p`) move, `enter` switches, `esc` leaves the plan
alone. `/switch pro` still works if you'd rather say it outright.

```
› /switch pro
✓ Now billing as Text Search Pro
  ⎿ free tier  5,000 a month (was 1,000)  ·  4,925 left  ·  540 today
  ⎿ giving up  nationalPhoneNumber, internationalPhoneNumber, websiteUri, rating …
  ⎿ those columns come back empty — the file still has all 34
  ⎿ each SKU has its own allowance — pro usage is counted separately from the rest
```

| Plan | Free / month | What you keep | What you lose |
|---|---|---|---|
| `atmosphere` *(default)* | 1,000 | everything | — |
| `enterprise` | 1,000 | everything useful | `summary` (empty on most small businesses anyway) |
| `pro` | **5,000** | name, address, type, coordinates, status, hours-free fields | phone, website, rating, reviews, price |
| `essentials` | **10,000** | ids, addresses, coordinates, types | the business name as well |
| `ids` | **unlimited** | place ids | everything else |

Aliases: `full`, `contact`, `basic`, `minimal`, `ids-only`, `free`.

**When it's worth it.** `pro` is the interesting one: five times the allowance, and you
still get name, address and coordinates. Use it to map coverage — *how many gyms are in
this district, and where* — then switch back to `atmosphere` and re-run the shortlist to
collect phone numbers. Two searches on two allowances beat one search that runs out.

**Each SKU is metered separately**, by Google and by Business Lead. Using up your 1,000
Atmosphere calls doesn't touch the 5,000 Pro ones — which is why `/switch pro` is
sometimes the answer to *"out of free calls for today"*.

The columns you gave up still exist in the output file; they're simply empty. From the
CLI it's `--plan pro`, and `BUSINESSLEAD_PLAN=pro` in `.env` makes it the default.

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

From the CLI it's `--daily-cap N` for one run, and `BUSINESSLEAD_DAILY_CAP=N` in `.env` makes
it every day's allowance (`BUSINESSLEAD_MONTHLY_CAP` does the same for the month's ceiling).
`/borrow` and `/daily-cap` override the `.env` value for the session; the `.env` value
is back the next time you launch.

## /reset-quota — for development only

Clears Business Lead's own counters so a development loop isn't blocked by the daily share:

```
⚠ Today's counters cleared
  ⎿ text_atmosphere  111 calls forgotten
  ⎿ this clears Business Lead's bookkeeping only — Google has still been called, and
    still counts every one of them
  ⎿ for development. The real limit lives in the Cloud console.
```

**It resets nothing at Google.** Those calls were made and Google still counts them.
Reset repeatedly and you can walk past the free tier into billing — the only thing that
would stop you is the [quota cap in the Cloud console](setup.md#cap-it-in-the-console).

## /sessions — what you've already run

```
⏺ Recent searches · 2 shown
  ⎿ 24 Aug 2026 00:49  barber · Nashik  ·  121 rows  ·  76 calls  ·  Business Lead/barber_nashik.csv
  ⎿ 23 Aug 2026 22:14  coffee shop · Pune  ·  58 rows  ·  14 calls  ·  Business Lead/coffee_shop_pune.pdf
```

Every finished search appends one JSON line to `~/.local/state/businesslead/sessions.jsonl` —
what was searched, how many rows, how many calls, which file. Never the API key.

## /seen — what has already been handed over

No search ever returns a business an earlier one delivered, so a run tomorrow brings back
what today's didn't. `/seen` is that record:

```
› /seen
⏺ Already delivered · 412 businesses
  ⎿ 22 Aug     121 businesses
  ⎿ 23 Aug      58 businesses
  ⎿ 24 Aug     233 businesses
  ⎿ queued     19 areas across 3 searches — the next run carries on there
  ⎿ kept in ~/.local/state/businesslead/delivered.db  ·  /seen forget starts over
```

The `queued` line is the other half: a sweep writes down which circles it covered and
which are still waiting, so the next run carries on there instead of paying to re-read the
same ground. Ids are written only once a results file exists, so a run that fails leaves
nothing behind and can be repeated. `/seen forget` empties both records — delivered businesses and part-searched areas — and
the next search starts from nothing. The command-line equivalents are `--forget-seen`,
`--resweep` to re-search one area without forgetting anything, and `--include-seen` to
write the repeats out.

When a search matches only businesses that have already been delivered, it writes no file
and says so:

```
✗ No unique data left — all 143 matches here were delivered by an earlier run.
```

## Running out of calls doesn't end the session

Searching is what the free tier limits; talking to the tool isn't. When the day's share
is spent, the session drops into a commands-only prompt instead of exiting:

```
✗ Out of free calls for today
  ⎿ today's share is spent · 889 left this month, back tomorrow

╭──────────────────────────────────────────────────────────────────────────────╮
│ › /borrow 40   ·   /switch pro   ·   /reset-quota   ·   /help                │
╰──────────────────────────────────────────────────────────────────────────────╯
  commands only — searching resumes the moment there's quota

› /borrow 40
✓ Borrowed 40 calls for today

✓ 40 calls available — carrying on

⏺ Location
```

## Three of them work from the shell

```bash
businesslead --usage             # /quota   (--verbose adds the day-by-day list)
businesslead --sessions          # /sessions
businesslead --reset-quota       # /reset-quota
```
