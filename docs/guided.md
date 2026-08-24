# The guided session

Run Business Lead with no arguments and it asks three questions, one at a time, then sweeps the
area and writes the file.

```bash
./run.sh          # or: businesslead
```

No chat window and no bubbles. Output scrolls in your real terminal as `⏺` steps with `⎿`
detail lines; the only live element is a rounded input box that appears, takes one answer,
and disappears — leaving the answer behind as a line of output.

## The opening screen

```
╭────────────────────────────────────╮
│ ✻ Welcome to Business Lead  v2.0.0 │
╰────────────────────────────────────╯

 ████  █   █  ████ █████ █   █ █████  ████  ████   █     █████  ███  ████
 █   █ █   █ █       █   ██  █ █     █     █       █     █     █   █ █   █
 ████  █   █  ███    █   █ █ █ ████   ███   ███    █     ████  █████ █   █
 █   █ █   █     █   █   █  ██ █         █     █   █     █     █   █ █   █
 ████   ███  ████  █████ █   █ █████ ████  ████    █████ █████ █   █ ████
  ████   ███  ████  █████ █   █ █████ ████  ████    █████ █████ █   █ ████
 …

⏺ Free tier · Text Search Enterprise + Atmosphere
  ⎿ this month 103 of 1,000 used  ·  897 left  ·  resets 01 Sep 2026
  ⎿ today      17 of 111 used  ·  94 left  ▰▰▱▱▱▱▱▱▱▱
  ⎿ by day     Mon 0   Tue 24   Wed 8   Thu 0   Fri 31   Sat 12   today 17

⏺ Location
  ⎿ Where should I search? Name the country — the rest is optional.
```

The free-tier block is the whole opening — it's there before you type anything, so a
search never starts without you knowing what it will spend. `/help` lists the commands. See [Staying inside the free tier](free-tier.md).

## The four questions

### 1 · File

```
⏺ File
  ⎿ Which file should these results go in? Enter to name it after the search.

╭──────────────────────────────────────────────────────────────────────╮
│ › mumbai_dentists                                                    │
╰──────────────────────────────────────────────────────────────────────╯
  1/4   enter to submit   ctrl+c twice to quit

  › mumbai_dentists.csv
  ⎿ · Business Lead/mumbai_dentists.csv — 221 rows already, this search adds to them
```

**Skipping it is fine** — press enter and the file is named after the search, which is
what happened before this question existed. Answer it and you decide which file the
results join.

That matters when two searches are really the same list. A **Mumbai** search and a
**Bombay** search are the same city; pointing both at `mumbai_dentists.csv` gives you one
lead list instead of two half-lists you have to merge later. The same goes for sweeping a
city district by district, or a category across neighbouring towns.

As you answer, it says what it found there — `new file`, or how many rows are already in
it — so you can see you've named the file you meant.

**Name a file it has written before and it picks that search back up**, and jumps straight
to the last step:

```
  › mumbai_dentists.csv
  ⎿ · Business Lead/mumbai_dentists.csv — 124 rows already, this search adds to them
  ⎿ · last searched for dentist · Mumbai, Maharashtra, India on 24 Aug 2026 18:14 — taking that
      again; /back to change any of it

⏺ Name
  ⎿ A particular business — or skip it and take the whole category.
  4/4   enter runs the search   ctrl+c twice to quit
```

Location and category come from the run that last wrote to that file, so topping a list up
is one answer and one enter instead of retyping the whole search. `/back` from there walks
into category and location if you want to vary it — which is how you point a **Bombay**
search at the file your **Mumbai** rows are in.

It only fills what's blank, so anything you set in `.env` or typed before a `/back` wins.
If the recovered search isn't complete enough to run on its own, the questions are asked
as usual rather than half-skipped.

| | |
|---|---|
| No extension | gets the one `PLACES_FORMAT` asks for, so `mumbai_dentists` becomes `mumbai_dentists.csv` |
| A bare name | lands in `Business Lead/` |
| A name with a directory | `~/Desktop/clients.xlsx`, `reports/q3.csv` — left exactly where you put it |
| A `.pdf` | says so: a PDF can't be added to, so each search writes its own |
| For the rest of the session | the file you name is offered as the default at every later search, so a run of related searches collects in one place |

Rows from different searches are told apart by the `extracted_on` and `search_query`
columns — see [Output](output.md#run-it-again-and-the-file-grows).

### 2 · Location

```
⏺ Location
  ⎿ Where should I search? Name the country — the rest is optional.

╭──────────────────────────────────────────────────────────────────────╮
│ › Austin, TX, USA                                                    │
╰──────────────────────────────────────────────────────────────────────╯
  2/4   enter to submit   ctrl+c twice to quit
```

Takes a city, an area, a postcode, or a full street address — anything Google can
geocode. It's checked against the offline gazetteer first, so `Bangalre` is caught before
it costs anything:

```
  › Bangalre
  ⎿ ✗ I don't know any place in “Bangalre”
  ⎿ did you mean Bangalore · Bangalur · Bangalor?
  ⎿ send it again to use it anyway
```

Send the same answer twice to override the check. Details in [Field checks](checks.md).

### 3 · Category

```
⏺ Category
  ⎿ What kind of business? Leave empty if you want one named place.
```

Everyday words work — `chemist`, `petrol pump`, `beauty parlour` — and are mapped to the
place type Google actually understands:

```
  › chemist
  ⎿ · “chemist” → Google's pharmacy
```

`/category` lists all 478 of them, or searches: `/category coffee`.

### 4 · Name

```
⏺ Name
  ⎿ A particular business — or skip it and take the whole category.
```

Optional, unless you skipped the category — you need one or the other. Give a name and
the search narrows to it; add `--name-match` on the CLI to keep only results whose name
really contains it.

## It never asks which format

The File question takes a name, not a format. What it's written as comes from `.env`, set
once:

```ini
PLACES_FORMAT=csv        # or excel, pdf, json
```

That's the extension a bare name gets, so answering `mumbai_dentists` writes
`mumbai_dentists.csv`. Skip the question entirely and the file is named after the search —
`coffee_shop_austin_tx.csv`. Either way it lands in `Business Lead/`, and `/formats` shows
which format is in play and where that setting lives. After a search you're offered the
same results in another format for free — no API calls, it just re-writes what's already
on disk. See [Output](output.md).

## Then it runs

The last answer starts the search — there is no confirmation step. The search opens with
what it is about to do, and what it will cost:

```
⏺ Search plan
  ⎿ looking for coffee shop
  ⎿ area       12.0 km radius  ·  everything in it
  ⎿ sweep      until today's 94 calls run out  ·  splits where it's dense
  ⎿ no repeats 312 delivered before  ·  left out of this file
  ⎿ output     Business Lead/coffee_shop_austin_tx.csv
  ⎿ free tier  94 calls left today  ·  1,000 this month
```

The sweep spends the day's remaining free calls on this one search, subdividing wherever
Google truncates the results, and it never returns a business an earlier run already
delivered — see [How much it finds](coverage.md).

To change an answer, `/back` at any question steps back one, with every answer kept as
the default — so changing one thing costs one keystroke. `ctrl+c` mid-sweep keeps whatever
has been found and writes the file.

## Another copy

When the file is written, Business Lead offers the same results in other formats. That costs
nothing — it re-writes what's already on disk:

```
⏺ Another copy?
  ⎿ pdf, excel, json or csv — costs nothing, it just re-writes what you have.

  › pdf excel
  ⎿ ✓ Business Lead/barber_nashik.pdf
  ⎿ ✓ Business Lead/barber_nashik.xlsx
```

Then it offers another search, keeping your API key and options.

## The input box

| Key | Does |
|---|---|
| `enter` | submit — or accept the greyed-out default |
| `ctrl+c` | clear the line; pressed twice in a row, leave the session |
| `↑` / `↓` | recall what you answered to *this* question earlier in the session |
| `←` `→`, `ctrl+a`, `ctrl+e`, `ctrl+w` | ordinary line editing |
| `ctrl+d` | on an empty line, the same as `ctrl+c` |

Three details that matter in practice:

- **Nothing is ever typed into the box for you.** A default shows greyed out and applies
  if you press Enter, so you never delete someone else's text to write your own.
- **`ctrl+c` takes two presses.** Editors type into terminals on their own — VS Code
  activates the project virtualenv a moment after a terminal opens, and clears the line
  with `ctrl+c` first. One stray press used to end the session before you'd typed a thing.
- **Commands your editor types are ignored.** If `source .venv/bin/activate` lands in the
  box, Business Lead recognises it and says so rather than taking it as your answer.

## Commands

Any answer starting with `/` is a command — see the [command reference](commands.md).
They work at every question, print what they have to say, and hand the question straight
back. Nothing you've typed is lost.
