"""One search, start to finish: check, locate, sweep, write, report."""

from __future__ import annotations

import datetime as dt
import json
import time
from collections import deque
from pathlib import Path

import pandas as pd
from rich.box import ROUNDED
from rich.panel import Panel
from rich.text import Text

from . import delivered, frontier, geocache, history, quota
from .config import Settings
from .constants import (COLUMNS, ENV_KEYS, ERROR_TILES, MAX_PAGES, MAX_RADIUS_M,
                        MIN_TILE_RADIUS, PAGE_SIZE, SATURATED, UNMETERED_TILES,
                        DRY_TILES, mask_for, sku_for_plan)
from .errors import PlacesError, RetryableError
from .export import (READABLE, fold_into_existing, output_path_for, unique_path,
                     write_dataframe)
from .geometry import Tile, split_tile
from .paths import state_dir
from .places import PlacesClient
from .records import name_matches, to_row
from .ui.report import Reporter, mask_key, progress_bar, short_path
from .ui.tables import results_table, summary_panel
from .ui.theme import BRANCH, WORK_VERBS, console


def run(settings: Settings) -> int:
    report = Reporter(console, settings.quiet)

    if not settings.api_key:
        report.error("No API key.")
        if settings.env_path:
            console.print(f"  {short_path(settings.env_path)} has no {ENV_KEYS[0]}= value.",
                          style="muted")
        else:
            console.print("  Create a [path].env[/path] file next to the script containing:",
                          style="muted")
            console.print(f"    {ENV_KEYS[0]}=AIza...", style="muted")
        console.print("  (or export it, or pass --api-key)", style="muted")
        console.print("  Enable 'Places API (New)' + 'Geocoding API' at "
                      "console.cloud.google.com", style="muted")
        return 1

    if settings.included_type:
        from .validate import place_types    # Table A / Table B, no heavy imports
        complaint = place_types.check_type_id(settings.included_type)
        if complaint:
            raise PlacesError(complaint)

    if settings.verify_location:
        from .validate import gazetteer      # lazy: builds an index on first use
        verdict = gazetteer.verify(settings.location, region=settings.region)
        if not verdict.ok:
            hint = (f" Did you mean {', '.join(verdict.suggestions)}?"
                    if verdict.suggestions else "")
            raise PlacesError(f"{verdict.reason()}.{hint} "
                              "Pass --no-verify to search for it anyway, or "
                              f"name it in {gazetteer.EXTRA_ENV[0]}.")
        for note in verdict.hints:
            report.note(note, mark="!", style="warn")
        for note in verdict.notes:
            report.note(note, mark="·", style="muted")

    if settings.verify_category and settings.category:
        from .validate import place_types
        verdict = place_types.verify(settings.category)
        if not verdict.ok:
            hint = (f" Did you mean {', '.join(verdict.suggestions)}?"
                    if verdict.suggestions else "")
            raise PlacesError(f"{verdict.reason()}.{hint} "
                              "Pass --no-verify to search for it anyway.")
        for note in verdict.notes:
            report.note(note, mark="·", style="muted")

    field_mask = mask_for(settings.plan)          # the plan decides both of these
    search_sku = sku_for_plan(settings.plan)
    ledger = quota.Quota(daily_cap=settings.daily_cap,
                         monthly_cap=settings.monthly_cap)
    already = delivered.Delivered()      # what earlier runs have handed over
    search_left = ledger.left_today(search_sku)
    if search_left <= 0:
        status = ledger.status(search_sku)
        if status.left_month <= 0:
            raise PlacesError(
                f"the {status.monthly_free:,} free {search_sku.label} calls for "
                f"{ledger.month_name()} are gone — they come back on "
                f"{quota.human_date(ledger.next_month())}")
        raise PlacesError(
            f"today's free share is spent ({status.used_today:,} calls) — "
            f"{status.left_month:,} left this month, back tomorrow. "
            "Use --daily-cap N (or BUSINESSLEAD_DAILY_CAP in .env) to borrow from "
            "the rest of the month.")

    client = PlacesClient(settings.api_key, budget=ledger,
                          field_mask=field_mask, sku=search_sku)
    # One search, one file: running the same location and category again adds
    # what it finds to the file already there rather than starting another. The
    # earlier rows are never rewritten, and `extracted_on` dates each arrival.
    # A PDF is the exception — it can't be read back, so it still gets its own.
    output_path = output_path_for(settings)
    if output_path.suffix.lower() not in READABLE:
        output_path = unique_path(output_path)
    settings.output = str(output_path)
    # Stamped once, so a sweep running through midnight dates every row it
    # writes to the day the search was asked for.
    extracted_on = dt.date.today().isoformat()
    if output_path.suffix.lower() not in (".csv", ".xlsx", ".pdf", ".json"):
        report.note(f"{output_path.suffix} isn't a format I write — "
                    f"putting CSV inside {output_path.name}", mark="!", style="warn")

    # ---- resolve the area ---------------------------------------------------
    report.step(f"Locating {settings.location}")
    started = time.monotonic()
    cache = geocache.GeoCache()
    remembered = cache.get(settings.location, settings.language, settings.region)
    if remembered:                    # a place doesn't move: no call, ever again
        lat, lng, resolved, viewport_radius = remembered
        cache.save()
    else:
        report.start_work("Geocoding…")
        try:
            lat, lng, resolved, viewport_radius = client.geocode(
                settings.location, settings.language, settings.region)
        finally:
            report.stop_work()
            ledger.save()    # the geocode unit is spent even when it failed
        cache.put(settings.location, settings.language, settings.region,
                  lat, lng, resolved, viewport_radius)
        cache.save()

    radius = min(max(settings.radius or viewport_radius or 10_000.0, 100.0), MAX_RADIUS_M)
    # Nothing bounds the sweep but the day's free calls. A tile costs at least
    # one, so today's share is also the most tiles this run could ever open —
    # except on the unmetered SKU, where there is no share to run out of.
    metered = search_sku.free_per_month > 0
    budget = max(1, settings.max_tiles
                 or (search_left if metered else UNMETERED_TILES))
    tiles = [Tile(lat, lng, radius)]
    query = f"{settings.search_terms} in {resolved}"
    limit = settings.max_results or MAX_PAGES * PAGE_SIZE * budget

    # Where this exact search got to last time. Re-searching yesterday's circles
    # would cost a call each and hand back places already delivered, so the queue
    # they left behind is what today starts from.
    sweeps = frontier.Frontier()
    sweep_key = frontier.fingerprint(
        settings.location, settings.category, settings.name, settings.region,
        settings.language, radius,
        # Filters change what comes back, so a filtered sweep must never mark
        # the unfiltered one (or a differently filtered one) as mined out.
        filters=frontier.filters_key(
            type=settings.included_type, rating=settings.min_rating,
            open_now=settings.open_now, name_match=settings.name_match,
            website=settings.with_website_only,
            operational=settings.operational_only))
    sweep = (sweeps.restart(sweep_key) if settings.resweep or settings.include_seen
             else sweeps.load(sweep_key))
    if sweep.exhausted:
        report.print()
        report.error("Nothing left to search here — this area was swept to the end "
                     f"on {frontier.human_day(sweep.finished)}.")
        body = Text("Already mined out\n\n", style="bad")
        body.append(f"{sweep.delivered:,} business{'' if sweep.delivered == 1 else 'es'} "
                    f"came out of it across {sweep.searched:,} "
                    f"search{'' if sweep.searched == 1 else 'es'} since "
                    f"{frontier.human_day(sweep.started)}, and no circle is left "
                    "unsearched.\nNot one call was spent finding that out.\n\n",
                    style="muted")
        body.append("Try another area or category, widen --radius,\n"
                    "or pass --resweep to search the whole area again from scratch.",
                    style="muted")
        report.print(Panel(body, box=ROUNDED, border_style="bad", expand=False,
                           padding=(0, 1), title=Text("nothing left", style="bad"),
                           title_align="left"))
        return 1

    report.detail("resolved", Text(resolved, style="value"))
    coords = Text(f"{lat:.5f}, {lng:.5f}", style="muted")
    if remembered:
        coords.append("  ·  remembered, no geocoding call", style="muted")
    report.detail("coords", coords)
    report.print()

    # ---- the plan -----------------------------------------------------------
    filters = []
    if settings.included_type:
        filters.append(f"type={settings.included_type}")
    if settings.min_rating:
        filters.append(f"rating≥{settings.min_rating}")
    if settings.open_now:
        filters.append("open now")
    if settings.name_match:
        filters.append(f"name contains {settings.name!r}")
    if settings.with_website_only:
        filters.append("has website")
    if settings.operational_only:
        filters.append("operational")

    report.step("Search plan")
    looking_for = Text()
    if settings.name:
        looking_for.append(settings.name, style="value")
        if settings.category:
            looking_for.append(" · ", style="muted")
    if settings.category:
        looking_for.append(settings.category, style="value")
    report.detail("looking for", looking_for)
    area = Text(f"{radius / 1000:.1f} km radius", style="value")
    area.append("  ·  everything in it", style="muted")
    if settings.max_results:
        area.append(f"  ·  stopping at {settings.max_results}", style="muted")
    report.detail("area", area)
    if settings.max_tiles or not metered:
        depth = Text(f"at most {budget} searches of the area", style="value")
    else:
        depth = Text(f"until today's {search_left:,} calls run out", style="value")
    depth.append("  ·  splits where it's dense", style="muted")
    report.detail("sweep", depth)
    if filters:
        report.detail("filters", Text(", ".join(filters), style="muted"))
    if not sweep.fresh:
        picking_up = Text(f"{len(sweep.queue):,} areas still queued", style="value")
        picking_up.append(f"  ·  {sweep.searched:,} searched since "
                          f"{frontier.human_day(sweep.started)}", style="muted")
        report.detail("carrying on", picking_up)
    if settings.include_seen:
        report.detail("repeats", Text("kept in", style="value")
                      + Text("  ·  --include-seen", style="muted"))
    elif already:
        report.detail("no repeats", Text(f"{len(already):,} delivered before", style="value")
                      + Text("  ·  left out of this file", style="muted"))
    report.detail("output", Text(short_path(output_path), style="path"))
    report.detail("api key", Text(f"{mask_key(settings.api_key)} · from "
                                  f"{settings.api_key_source}", style="muted"))
    if metered:
        tier = ledger.status(search_sku)
        free = Text(f"{search_left:,} calls left today", style="value")
        free.append(f"  ·  {tier.left_month:,} of "
                    f"{tier.monthly_free:,} this month  ·  {search_sku.label}",
                    style="muted")
        if settings.daily_cap is not None or settings.monthly_cap is not None:
            free.append("  ·  capped by "
                        + (settings.daily_cap_source or settings.monthly_cap_source
                           or "--daily-cap"), style="muted")
    else:
        free = Text("free, unmetered", style="value")
        free.append(f"  ·  {search_sku.label}", style="muted")
    report.detail("free tier", free)
    report.print()

    # ---- search -------------------------------------------------------------
    report.step("Searching Google Places")
    report.detail("query", Text(f"“{query}”", style="muted"))

    fetched: set[str] = set()      # every id Google has shown us this run
    records: list[dict] = []
    raw: list[dict] = []
    warnings: list[str] = []
    repeats = 0                    # matches held back because an earlier run had them
    search_started = time.monotonic()
    report.start_work("Searching…")

    def remember_sweep(handed_over: int) -> None:
        """Write down what was searched and what is left, however this run ended."""
        sweeps.record(sweep, query=query, done=walked, queue=queue,
                      delivered=handed_over)
        sweeps.save()

    resumed = sweep.tiles()
    queue: deque[Tile] = deque(resumed or tiles)
    walked: set[str] = set(sweep.done)      # circles earlier runs already searched
    failed: list[Tile] = []    # circles whose search failed: kept for next time
    done = 0
    dry = 0                # searches in a row that turned up nothing new
    unsplit = 0            # tiles that came back full but couldn't be subdivided
    failures = 0           # searches in a row that failed outright
    out_of_quota = False
    stopped_dry = False
    stopped_network = False
    broken = False
    pending: Tile | None = None    # popped but not yet searched or put back
    try:
        while queue:
            if len(records) >= limit or done >= budget:
                break
            if dry >= DRY_TILES:      # this ground is picked over: keep the calls
                stopped_dry = True
                break
            tile = queue.popleft()
            here = frontier.encode(tile)
            if here in walked:            # the same circle twice is a wasted call
                continue
            pending = tile
            verb = WORK_VERBS[done % len(WORK_VERBS)]
            total = min(budget, done + 1 + len(queue))
            queued = f" · {len(queue)} queued" if queue else ""
            report.working(verb,
                           f"{progress_bar(done, total)}  tile {done + 1}/{total}"
                           f"{queued} · {len(records)} found",
                           time.monotonic() - search_started)
            try:
                places = client.search_text(
                    query, tile, limit, included_type=settings.included_type,
                    language=settings.language, region=settings.region,
                    open_now=settings.open_now, min_rating=settings.min_rating,
                    on_warn=warnings.append)
            except quota.QuotaExceeded as exc:
                report.stop_work()
                report.note(str(exc), mark="■", style="warn")
                out_of_quota = True
                queue.appendleft(tile)    # never searched: stays on the frontier
                pending = None
                break
            except RetryableError as exc:
                report.stop_work()
                report.note(f"the network (or Google) gave out — {exc}. Stopping "
                            "here; everything found so far is kept, and the next "
                            "run carries on from this circle.", mark="■", style="warn")
                stopped_network = True
                queue.appendleft(tile)
                pending = None
                break
            except PlacesError as exc:
                report.note(f"tile {done + 1} · {exc}", mark="!", style="warn")
                failed.append(tile)       # kept for the next run, not retried now
                pending = None
                failures += 1
                if failures >= ERROR_TILES:
                    report.stop_work()
                    report.note(f"{ERROR_TILES} searches in a row failed — "
                                "stopping before more of the area is wasted on an "
                                "error that isn't going away", mark="■", style="bad")
                    broken = True
                    break
                continue

            failures = 0
            done += 1
            if client.partial_tile:
                failed.append(tile)   # quota cut it short: not searched to the end
            else:
                walked.add(here)      # only now is this circle truly done
            pending = None

            new_here = 0
            fresh = 0              # ids this tile showed us that no earlier tile did
            for place in places:
                pid = place.get("id")
                if not pid or pid in fetched:
                    continue
                fetched.add(pid)
                fresh += 1
                if pid in already and not settings.include_seen:
                    repeats += 1              # an earlier run already handed it over
                    continue
                if settings.operational_only and place.get("businessStatus") != "OPERATIONAL":
                    continue
                if settings.with_website_only and not place.get("websiteUri"):
                    continue
                if settings.name_match and settings.name and not name_matches(
                        (place.get("displayName") or {}).get("text", ""), settings.name):
                    continue
                records.append(to_row(place, settings.category, query, settings.name,
                                      extracted_on))
                if settings.json_out:     # only --json-out needs the raw payloads
                    raw.append(place)
                new_here += 1
                if len(records) >= limit:
                    break

            # A full tile means Google truncated it: search the same ground again
            # in four smaller circles, and keep going until it stops truncating.
            dry = 0 if new_here else dry + 1

            crowded = len(places) >= SATURATED and fresh   # full, and new to us
            # --max-tiles is a promise about spend, so a split has to fit inside
            # it. With only the day's calls to answer to, splitting is free: the
            # tiles that don't fit are simply never reached.
            room = (done + len(queue) + 4 <= budget) if settings.max_tiles else True
            split = crowded and tile.radius > MIN_TILE_RADIUS and room
            if split:
                queue.extend(split_tile(tile))
            elif crowded:
                unsplit += 1

            if settings.verbose:          # --verbose puts the tile-by-tile log back
                detail = Text()
                detail.append(f"tile {done}", style="muted")
                detail.append(f"  {len(places)} found", style="muted")
                detail.append(f"  +{new_here} new" if new_here else "  +0 new",
                              style="ok" if new_here else "muted")
                detail.append(f"  ·  {len(records)} total", style="muted")
                if split:
                    detail.append("  ·  full, splitting in 4", style="warn")
                report.line(Text("  ") + Text(f"{BRANCH} ", style="muted") + detail)
    except KeyboardInterrupt:
        report.stop_work()
        if pending is not None:
            queue.appendleft(pending)     # interrupted mid-search: not done yet
            pending = None
        report.note(f"stopped early · keeping the {len(records)} found so far",
                    mark="■", style="warn")
    finally:
        report.stop_work()
        if failed:
            queue.extend(failed)    # failed circles stay on the frontier
            failed = []
        ledger.save()               # even a ctrl+c leaves the ledger honest
        remember_sweep(0)           # and the frontier survives whatever comes next

    # Never let a cap look like an exhaustive sweep.
    if out_of_quota or stopped_network or broken:
        pass                        # already said so, in its own words
    elif len(records) >= limit and settings.max_results:
        report.note(f"stopped at --max-results {settings.max_results}",
                    mark="!", style="warn")
    elif stopped_dry:
        report.note(f"{DRY_TILES} searches in a row turned up nothing new — stopping "
                    f"with {ledger.left_today(search_sku):,} calls still yours",
                    mark="!", style="warn")
    elif queue:
        left = len(queue) + unsplit
        if settings.max_tiles:
            why = f"stopped at the --max-tiles {settings.max_tiles} cap"
        elif metered:
            why = "today's free calls are spent"
        else:
            why = f"stopped at {budget} searches"
        report.note(f"{left} area{'' if left == 1 else 's'} still had more to give · "
                    f"{why} — the next run carries on from there",
                    mark="!", style="warn")
    elif unsplit:
        report.note(f"{unsplit} area{'' if unsplit == 1 else 's'} came back full at the "
                    "smallest tile size — narrow the category or search a smaller area",
                    mark="!", style="warn")

    if repeats:
        report.note(f"{repeats:,} match{'' if repeats == 1 else 'es'} left out — "
                    "earlier runs already delivered them", mark="·", style="muted")

    for note in dict.fromkeys(warnings):
        report.note(note, mark="!", style="warn")

    elapsed = time.monotonic() - started

    if not records and repeats:
        # Everything this search can reach has been delivered before. That is an
        # answer, not a result: no file is written and the run fails loudly.
        report.error(f"No unique data left — all {repeats:,} match"
                     f"{'' if repeats == 1 else 'es'} here were delivered by an "
                     "earlier run.")
        body = Text("Nothing new to hand over\n\n", style="bad")
        body.append(f"{repeats:,} business{'' if repeats == 1 else 'es'} matched and "
                    f"every one is already in a file you have.\n"
                    f"{len(already):,} delivered in all, kept in "
                    f"{short_path(delivered.default_path())}.\n\n", style="muted")
        body.append("Search another area or category, widen --radius,\n"
                    "or pass --include-seen to write the repeats out again.",
                    style="muted")
        report.print(Panel(body, box=ROUNDED, border_style="bad", expand=False,
                           padding=(0, 1), title=Text("nothing new", style="bad"),
                           title_align="left"))
        remember_sweep(0)
        return 1

    if not records:
        report.note("no businesses matched", mark="!", style="warn")
        report.print()
        hints = ["Try a wider --radius,"]
        if settings.name_match:
            hints.append("relax --name-match (the name must appear in the result),")
        if settings.name and not settings.category:
            hints.append("add a --category to widen the search,")
        hints.append("or drop the other filters.")
        body = Text("No businesses found\n\n", style="warn")
        body.append("\n".join(hints), style="muted")
        report.print(Panel(body, box=ROUNDED, border_style="warn", expand=False,
                           padding=(0, 1), title=Text("empty", style="muted"),
                           title_align="left"))
        remember_sweep(0)
        return 0

    report.note(f"{len(records)} businesses, none delivered before, in "
                f"{time.monotonic() - search_started:.1f}s"
                f" · {done} tile{'' if done == 1 else 's'} · "
                f"{client.requests} API request{'' if client.requests == 1 else 's'}")
    report.print()

    # ---- write --------------------------------------------------------------
    df = pd.DataFrame(records, columns=COLUMNS)
    df = df.sort_values(["reviews_count", "name"], ascending=[False, True],
                        na_position="last").reset_index(drop=True)
    # `sheet` is what lands on disk: this run's rows under everything the same
    # search found before. `df` stays this run's alone — the table, the history
    # and the delivered ledger are all about what this run did.
    sheet, output_path, before = fold_into_existing(df, output_path)
    settings.output = str(output_path)
    if before:
        report.note(f"added to the {before:,} already in "
                    f"{short_path(output_path)} · {len(sheet):,} in the file now")
    try:
        fmt = write_dataframe(sheet, output_path, title=query, pdf_all=settings.pdf_all)
    except (OSError, ValueError) as first_error:
        # The classic case is Windows: the last run's file is open in Excel and
        # holds a lock. The results are paid for — they must land somewhere.
        fallback = output_path.with_name(
            f"{output_path.stem}-{time.strftime('%H%M%S')}{output_path.suffix}")
        try:
            fmt = write_dataframe(sheet, fallback, title=query, pdf_all=settings.pdf_all)
            report.note(f"couldn't write {short_path(output_path)} "
                        f"({first_error}) — wrote {short_path(fallback)} instead",
                        mark="!", style="warn")
            output_path = fallback
            settings.output = str(output_path)
        except (OSError, ValueError):
            rescue = (state_dir() / "rescue"
                      / f"{output_path.stem}-{time.strftime('%Y%m%d-%H%M%S')}.csv")
            try:
                rescue.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(rescue, index=False, encoding="utf-8-sig")
            except OSError:
                # Total write failure: nothing was delivered, so nothing is
                # marked delivered — the searched circles are already saved.
                raise PlacesError(
                    f"couldn't write {short_path(output_path)} ({first_error}) — "
                    "close it if it's open in Excel and run again; nothing needs "
                    "re-searching, or pass --resweep to be thorough") from first_error
            already.add(df["place_id"].tolist())
            already.save()
            remember_sweep(len(df))
            raise PlacesError(
                f"couldn't write {short_path(output_path)} ({first_error}) — the "
                f"{len(df)} results were saved to {short_path(rescue)}; convert "
                "them any time with --convert") from first_error
    already.add(df["place_id"].tolist())
    already.save()
    remember_sweep(len(df))

    remaining = ledger.status(search_sku)
    extra = [("tiles swept", str(done)), ("api requests", str(client.requests)),
             ("free tier", "free, unmetered" if remaining.unlimited else
                           f"{remaining.left_today:,} left today · "
                           f"{remaining.left_month:,} this month"),
             ("never repeated", f"{len(already):,} businesses delivered so far"
                                + (f" · {repeats:,} held back" if repeats else "")),
             ("next run", f"{len(queue):,} areas queued, it carries on there"
                          if queue else "this area is swept to the end")]
    if settings.json_out:
        try:
            Path(settings.json_out).expanduser().write_text(
                json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
            extra.append(("raw json", short_path(settings.json_out)))
        except OSError as exc:
            report.note(f"couldn't write --json-out {settings.json_out}: {exc}",
                        mark="!", style="warn")

    report.step("Top results")
    report.print(results_table(df))
    if len(df) > 5:
        report.print(Text(
            f"  … and {len(df) - 5} more new · {len(sheet)} in the file" if before
            else f"  … and {len(df) - 5} more in the file", style="muted"))
    report.print()

    report.step(f"Wrote {short_path(output_path)}")
    report.detail("rows", Text(
        f"{len(df)} new · {len(sheet)} × {len(sheet.columns)} columns" if before
        else f"{len(sheet)} × {len(sheet.columns)} columns", style="value"))
    history.record(location=resolved, category=settings.category, name=settings.name,
                   rows=len(df), file=str(output_path), format=fmt,
                   tiles=done, requests=client.requests,
                   seconds=round(elapsed, 1), query=query)

    report.print()
    report.print(summary_panel(df, output_path, fmt, elapsed, extra))
    return 0
