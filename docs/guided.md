# The guided session

Run LeadMap with no arguments and it asks four questions, one at a time, then sweeps the
area and writes the file.

```bash
./run.sh          # or: leadmap
```

No chat window and no bubbles. Output scrolls in your real terminal as `⏺` steps with `⎿`
detail lines; the only live element is a rounded input box that appears, takes one answer,
and disappears — leaving the answer behind as a line of output.

## The opening screen

```
╭──────────────────────────────╮
│ ✻ Welcome to LeadMap  v2.0.0 │
╰──────────────────────────────╯

 ██          ██████████    ██████    ████████
 ██          ██          ██      ██  ██      ██
 ██          ████████    ██████████  ██      ██
 ██          ██          ██      ██  ██      ██
 ██████████  ██████████  ██      ██  ████████
 …

⏺ Free tier · Text Search Enterprise + Atmosphere
  ⎿ this month 103 of 1,000 used  ·  897 left  ·  resets 01 Sep 2026
  ⎿ today      17 of 111 used  ·  94 left  ▰▰▱▱▱▱▱▱▱▱
  ⎿ by day     Mon 0   Tue 24   Wed 8   Thu 0   Fri 31   Sat 12   today 17

⏺ Ready
  ⎿ api key    AIzaSy…0099 · from .env
  ⎿ asking     location, category, name — then a filename
  ⎿ commands   /help lists them · /category /quota /sessions /version
```

The free-tier block is there before you type anything, so a search never starts without
you knowing what it will spend. See [Staying inside the free tier](free-tier.md).

## The four questions

### 1 · Location

```
⏺ Location
  ⎿ Where should I search? City, area, postcode or full address.

╭──────────────────────────────────────────────────────────────────────╮
│ › Austin, TX                                                         │
╰──────────────────────────────────────────────────────────────────────╯
  1/4   enter to submit   ctrl+c twice to quit
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

### 2 · Category

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

### 3 · Name

```
⏺ Name
  ⎿ A particular business — or skip it and take the whole category.
```

Optional, unless you skipped the category — you need one or the other. Give a name and
the search narrows to it; add `--name-match` on the CLI to keep only results whose name
really contains it.

### 4 · Output

```
⏺ Output
  ⎿ csv, excel or pdf — or a filename if you want to choose it.
```

Type a format and the file is named after your search
(`coffee_shop_austin_tx.csv`); type a filename and it uses that. A bare name lands in
`output/<date>/`. See [Output](output.md).

## Then it runs

The plan block shows exactly what's about to happen, including what it will cost:

```
⏺ Ready when you are
  ⎿ location   Austin, TX
  ⎿ category   coffee shop
  ⎿ name       —
  ⎿ coverage   everything in the area
  ⎿ output     output/2026-08-24/coffee_shop_austin_tx.csv
  ⎿ free tier  94 calls left today
```

Enter runs it; `n` sends you back to the questions with every answer kept as the default,
so changing one thing costs one keystroke.

## Another copy

When the file is written, LeadMap offers the same results in other formats. That costs
nothing — it re-writes what's already on disk:

```
⏺ Another copy?
  ⎿ pdf, excel, json or csv — costs nothing, it just re-writes what you have.

  › pdf excel
  ⎿ ✓ output/2026-08-24/barber_nashik.pdf
  ⎿ ✓ output/2026-08-24/barber_nashik.xlsx
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
  box, LeadMap recognises it and says so rather than taking it as your answer.

## Commands

Any answer starting with `/` is a command — see the [command reference](commands.md).
They work at every question, print what they have to say, and hand the question straight
back. Nothing you've typed is lost.
