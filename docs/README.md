# LeadMap

**Business leads from Google Places — name, phone, website and a properly split address,
straight to csv, excel, pdf or json. Stays inside the free tier on purpose.**






```
╭──────────────────────────────╮
│ ✻ Welcome to LeadMap  v2.0.0 │
╰──────────────────────────────╯

 ██          ██████████    ██████    ████████
 ██          ██          ██      ██  ██      ██
 ██          ████████    ██████████  ██      ██
 ██          ██          ██      ██  ██      ██
 ██████████  ██████████  ██      ██  ████████

 ██      ██    ██████    ████████
 ████  ████  ██      ██  ██      ██
 ██  ██  ██  ██████████  ████████
 ██      ██  ██      ██  ██
 ██      ██  ██      ██  ██

  Business leads from Google Places  ·  csv · excel · pdf · json
  cwd: ~/projects/leadmap
```

Point it at a **location** and a **category** (or a specific business **name**) and it
comes back with every matching business Google will give up — 33 columns per row,
deduplicated, sorted by review count.

### What makes it different

- **It doesn't stop at 60.** Google truncates any text search at 60 places. LeadMap
  notices a truncated tile and re-searches that ground in quarters, over and over, until
  the results stop hitting the ceiling. A real run on Nashik barbers: 121 businesses from
  25 tiles.
- **It won't quietly bill you.** Google's free tier is per-SKU now, and this field mask
  bills at **1,000 searches a month**. LeadMap counts every call in a local ledger, splits
  the month across its days, and *stops* — there is no flag that spends money.
- **It checks before it spends.** Locations and categories are validated against 1.4M
  offline records (GeoNames + ISO 3166-2 + Google's own 478 place types) so a typo costs
  nothing instead of a geocoding call.
- **The address is actually split.** street · area · city · district · state · postcode —
  including the two-thirds of Indian addresses that carry no `route` component at all.
- **The terminal is the interface.** A Claude-Code-style guided session: one question at
  a time, a live progress bar, and slash commands (`/quota`, `/category`, `/sessions`).

### Quickstart

```bash
git clone https://github.com/DarkVertana/Lead-Map.git
cd leadmap
cp .env.example .env          # then put your Google API key in it
./run.sh                      # creates the venv, installs, starts the session
```

One-shot instead:

```bash
./run.sh -l "Nashik, India" -c barber -o barber_nashik.csv
```

You need a Google Cloud project with **Places API (New)** and **Geocoding API** enabled —
see [Setup](#setup).

---

Two ways to drive it:

* **Guided mode** (default when you run it bare) — asks one question at a time
  (**Location → Category → Name → Output**) in a Claude-Code-style terminal interface,
  then sweeps the area and writes the file.
* **CLI mode** (whenever you pass search options) — one-shot, scriptable, cron-safe.

Either way the location and category are checked against bundled offline data first, so a
typo costs you nothing instead of a geocoding call.
