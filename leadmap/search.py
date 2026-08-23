"""One search, start to finish: check, locate, sweep, write, report."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import pandas as pd
from rich.box import ROUNDED
from rich.panel import Panel
from rich.text import Text

from . import history, quota
from .config import Settings
from .constants import (COLUMNS, ENV_KEYS, MAX_PAGES, MAX_RADIUS_M, MIN_TILE_RADIUS,
                        PAGE_SIZE, SATURATED, mask_for, sku_for_plan)
from .errors import PlacesError
from .export import output_path_for, write_dataframe
from .geometry import Tile, build_tiles, split_tile
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
                              "Pass --no-verify to search for it anyway.")
        for note in verdict.hints:
            report.note(note, mark="!", style="warn")

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
    search_left = ledger.left_today(search_sku)
    if search_left <= 0:
        status = ledger.status(search_sku)
        if status.left_month <= 0:
            raise PlacesError(
                f"the {search_sku.free_per_month:,} free {search_sku.label} calls for "
                f"{ledger.month_name()} are gone — they come back on "
                f"{quota.human_date(ledger.next_month())}")
        raise PlacesError(
            f"today's free share is spent ({status.used_today:,} calls) — "
            f"{status.left_month:,} left this month, back tomorrow. "
            "Use --daily-cap N to borrow from the rest of the month.")

    client = PlacesClient(settings.api_key, budget=ledger,
                          field_mask=field_mask, sku=search_sku)
    output_path = output_path_for(settings)
    if output_path.suffix.lower() not in (".csv", ".xlsx", ".xls", ".pdf", ".json"):
        report.note(f"{output_path.suffix} isn't a format I write — "
                    f"putting CSV inside {output_path.name}", mark="!", style="warn")

    # ---- resolve the area ---------------------------------------------------
    report.step(f"Locating {settings.location}")
    report.start_work("Geocoding…")
    started = time.monotonic()
    try:
        lat, lng, resolved, viewport_radius = client.geocode(
            settings.location, settings.language, settings.region)
    finally:
        report.stop_work()

    radius = min(max(settings.radius or viewport_radius or 10_000.0, 100.0), MAX_RADIUS_M)
    sweeping = settings.grid <= 1                  # --grid N pins a fixed layout
    budget = max(1, settings.max_tiles)
    tiles = ([Tile(lat, lng, radius)] if sweeping
             else build_tiles(lat, lng, radius, settings.grid))
    query = f"{settings.search_terms} in {resolved}"
    limit = settings.max_results or MAX_PAGES * PAGE_SIZE * (budget if sweeping
                                                             else len(tiles))

    report.detail("resolved", Text(resolved, style="value"))
    report.detail("coords", Text(f"{lat:.5f}, {lng:.5f}", style="muted"))
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
    if sweeping:
        area.append("  ·  everything in it", style="muted")
    else:
        area.append(f"  ·  {len(tiles)} search tile{'' if len(tiles) == 1 else 's'}",
                    style="muted")
    if settings.max_results:
        area.append(f"  ·  stopping at {settings.max_results}", style="muted")
    report.detail("area", area)
    if sweeping:
        report.detail("coverage", Text("automatic", style="value")
                      + Text(f"  ·  splits where results are dense, up to "
                             f"{budget} tiles", style="muted"))
    if filters:
        report.detail("filters", Text(", ".join(filters), style="muted"))
    report.detail("output", Text(short_path(output_path), style="path"))
    report.detail("api key", Text(f"{mask_key(settings.api_key)} · from "
                                  f"{settings.api_key_source}", style="muted"))
    free = Text(f"{search_left:,} calls left today", style="value")
    free.append(f"  ·  {ledger.status(search_sku).left_month:,} of "
                f"{search_sku.free_per_month:,} this month  ·  {search_sku.label}",
                style="muted")
    report.detail("free tier", free)
    report.print()

    # ---- search -------------------------------------------------------------
    report.step("Searching Google Places")
    report.detail("query", Text(f"“{query}”", style="muted"))

    seen: set[str] = set()
    records: list[dict] = []
    raw: list[dict] = []
    warnings: list[str] = []
    search_started = time.monotonic()
    report.start_work("Searching…")

    queue: deque[Tile] = deque(tiles)
    done = 0
    unsplit = 0            # tiles that came back full but couldn't be subdivided
    out_of_quota = False
    try:
        while queue:
            if len(records) >= limit or (sweeping and done >= budget):
                break
            tile = queue.popleft()
            done += 1
            verb = WORK_VERBS[(done - 1) % len(WORK_VERBS)]
            total = min(budget, done + len(queue)) if sweeping else len(tiles)
            queued = f" · {len(queue)} queued" if sweeping and queue else ""
            report.working(verb,
                           f"{progress_bar(done - 1, total)}  tile {done}/{total}"
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
                break
            except PlacesError as exc:
                report.note(f"tile {done} · {exc}", mark="!", style="warn")
                continue

            new_here = 0
            for place in places:
                pid = place.get("id")
                if not pid or pid in seen:
                    continue
                if settings.operational_only and place.get("businessStatus") != "OPERATIONAL":
                    continue
                if settings.with_website_only and not place.get("websiteUri"):
                    continue
                if settings.name_match and settings.name and not name_matches(
                        (place.get("displayName") or {}).get("text", ""), settings.name):
                    continue
                seen.add(pid)
                records.append(to_row(place, settings.category, query, settings.name))
                raw.append(place)
                new_here += 1
                if len(records) >= limit:
                    break

            # A full tile means Google truncated it: search the same ground again
            # in four smaller circles, and keep going until it stops truncating.
            split = (sweeping and len(places) >= SATURATED
                     and tile.radius > MIN_TILE_RADIUS
                     and done + len(queue) + 4 <= budget)
            if split:
                queue.extend(split_tile(tile))
            elif (sweeping and len(places) >= SATURATED
                  and tile.radius > MIN_TILE_RADIUS):
                unsplit += 1

            if settings.verbose:          # --verbose puts the tile-by-tile log back
                detail = Text()
                detail.append(f"tile {done}", style="muted")
                if not sweeping:
                    detail.append(f"/{len(tiles)}", style="muted")
                detail.append(f"  {len(places)} found", style="muted")
                detail.append(f"  +{new_here} new" if new_here else "  +0 new",
                              style="ok" if new_here else "muted")
                detail.append(f"  ·  {len(records)} total", style="muted")
                if split:
                    detail.append("  ·  full, splitting in 4", style="warn")
                report.line(Text("  ") + Text(f"{BRANCH} ", style="muted") + detail)
    except KeyboardInterrupt:
        report.stop_work()
        report.note(f"stopped early · keeping the {len(records)} found so far",
                    mark="■", style="warn")
    finally:
        report.stop_work()
        ledger.save()               # even a ctrl+c leaves the ledger honest

    # Never let a cap look like an exhaustive sweep.
    if out_of_quota:
        pass                        # already said so, in its own words
    elif len(records) >= limit and settings.max_results:
        report.note(f"stopped at --max-results {settings.max_results}",
                    mark="!", style="warn")
    elif sweeping and (queue or unsplit):
        left = len(queue) + unsplit
        report.note(f"stopped at the {budget}-tile cap · {left} area"
                    f"{'' if left == 1 else 's'} still had more to give — "
                    "raise --max-tiles to go deeper", mark="!", style="warn")

    for note in dict.fromkeys(warnings):
        report.note(note, mark="!", style="warn")

    elapsed = time.monotonic() - started

    if not records:
        report.note("no businesses matched", mark="!", style="warn")
        report.print()
        hints = ["Try a wider --radius or --grid,"]
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
        return 0

    report.note(f"{len(records)} unique businesses in {time.monotonic() - search_started:.1f}s"
                f" · {done} tile{'' if done == 1 else 's'} · "
                f"{client.requests} API request{'' if client.requests == 1 else 's'}")
    report.print()

    # ---- write --------------------------------------------------------------
    df = pd.DataFrame(records, columns=COLUMNS)
    df = df.sort_values(["reviews_count", "name"], ascending=[False, True],
                        na_position="last").reset_index(drop=True)
    fmt = write_dataframe(df, output_path, title=query, pdf_all=settings.pdf_all)

    remaining = ledger.status(search_sku)
    extra = [("tiles swept", str(done)), ("api requests", str(client.requests)),
             ("free tier", f"{remaining.left_today:,} left today · "
                           f"{remaining.left_month:,} this month")]
    if settings.json_out:
        Path(settings.json_out).expanduser().write_text(
            json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        extra.append(("raw json", short_path(settings.json_out)))

    report.step("Top results")
    report.print(results_table(df))
    if len(df) > 5:
        report.print(Text(f"  … and {len(df) - 5} more in the file", style="muted"))
    report.print()

    report.step(f"Wrote {short_path(output_path)}")
    report.detail("rows", Text(f"{len(df)} × {len(df.columns)} columns", style="value"))
    history.record(location=resolved, category=settings.category, name=settings.name,
                   rows=len(df), file=str(output_path), format=fmt,
                   tiles=done, requests=client.requests,
                   seconds=round(elapsed, 1), query=query)

    report.print()
    report.print(summary_panel(df, output_path, fmt, elapsed, extra))
    return 0
