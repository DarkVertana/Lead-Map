"""The command line: flags in, a search (or a conversion, or a report) out."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.text import Text

from . import quota
from .config import Settings, apply_env_defaults, collect_inputs, load_environment
from .constants import APP_TITLE, DEFAULT_PLAN, VERSION, plan_name
from .errors import PlacesError, RetryableError
from .ui.banner import banner
from .ui.report import Reporter, short_path
from .ui.theme import console

app = typer.Typer(
    add_completion=False, rich_markup_mode="rich",
    help="[b]Business Lead[/b] — business leads from Google Places, to csv, excel, pdf or json.")


def convert(source: str, formats: str, quiet: bool = False,
            pdf_all: bool = False) -> int:
    """--convert: rewrite an existing results file in other formats."""
    from .export import convert_file, read_dataframe    # lazy: pulls in pandas
    report = Reporter(console, quiet)
    path = Path(source).expanduser()
    wanted = [f for f in re.split(r"[,\s]+", formats) if f]
    report.step(f"Converting {short_path(path)}")
    written = convert_file(path, wanted, pdf_all=pdf_all)
    if not written:
        report.note(f"{short_path(path)} is already that format", mark="!", style="warn")
        return 0
    df = read_dataframe(path)
    report.detail("rows", Text(f"{len(df)} × {len(df.columns)} columns", style="value"))
    for target in written:
        report.note(f"{target.suffix.lstrip('.'):<5} {short_path(target)}")
    report.print()
    report.print(Text("  no API calls — the data came off disk", style="muted"))
    return 0

@app.command()
def main(
    location: Annotated[Optional[str], typer.Option(
        "--location", "-l", help='Area to search, e.g. "Austin, TX, USA" or "560001, Bangalore, India".')] = None,
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n", help='Optional business name, e.g. "Starbucks".')] = None,
    category: Annotated[Optional[str], typer.Option(
        "--category", "-c", help='Business category, e.g. "coffee shop", "dentist".')] = None,
    output: Annotated[Optional[str], typer.Option(
        "--output", "-o", help="Output file: .csv, .xlsx or .json.")] = None,
    api_key: Annotated[Optional[str], typer.Option(
        "--api-key", help="Key override; normally comes from .env.")] = None,
    env_file: Annotated[Optional[str], typer.Option(
        "--env-file", help="Path to the .env file (default: nearest ./.env).")] = None,
    radius: Annotated[Optional[float], typer.Option(
        help="Search radius in metres (default: the geocoded area; max 50000).")] = None,
    max_results: Annotated[Optional[int], typer.Option(
        help="Stop after this many unique businesses.")] = None,
    max_tiles: Annotated[Optional[int], typer.Option(
        help="Cap the sweep at this many searches of the area "
             "(default: keep digging while today's free calls last).")] = None,
    daily_cap: Annotated[Optional[int], typer.Option(
        help="Calls allowed today (default: this month's free calls ÷ days left; "
             "BUSINESSLEAD_DAILY_CAP in .env makes it standing).")] = None,
    monthly_cap: Annotated[Optional[int], typer.Option(
        help="Free calls a month (default: Google's allowance for our field mask; "
             "BUSINESSLEAD_MONTHLY_CAP in .env makes it standing).")] = None,
    usage: Annotated[bool, typer.Option(
        "--usage", help="Show what's left of the free tier and exit.")] = False,
    sessions: Annotated[bool, typer.Option(
        "--sessions", help="List the searches already run, and exit.")] = False,
    locations: Annotated[bool, typer.Option(
        "--locations", help="Show the file of places you've added by hand "
                            "(creating it if there isn't one), and exit.")] = False,
    reset_quota: Annotated[bool, typer.Option(
        "--reset-quota", help="Forget today's recorded usage (development only).")] = False,
    convert_: Annotated[Optional[str], typer.Option(
        "--convert", help="Rewrite an existing results file in other formats "
                          "(no search, no API calls).")] = None,
    to: Annotated[str, typer.Option(
        "--to", help="Formats for --convert: csv, excel, pdf, json.")] = "pdf,excel,json",
    pdf_all: Annotated[bool, typer.Option(
        "--pdf-all", help="Put every column in the PDF, not just the useful dozen.")] = False,
    type_: Annotated[Optional[str], typer.Option(
        "--type", help="Restrict to a Places type id, e.g. restaurant, dentist.")] = None,
    language: Annotated[Optional[str], typer.Option(help="Language code, e.g. en, hi, es.")] = None,
    region: Annotated[Optional[str], typer.Option(help="Region code, e.g. us, in, gb.")] = None,
    min_rating: Annotated[Optional[float], typer.Option(help="Only places rated at least this.")] = None,
    open_now: Annotated[bool, typer.Option("--open-now", help="Only places open right now.")] = False,
    name_match: Annotated[bool, typer.Option(
        "--name-match", help="With --name: keep only results whose name contains it.")] = False,
    plan: Annotated[Optional[str], typer.Option(
        "--plan", help="Which SKU to bill at: atmosphere, enterprise, pro, essentials, "
                       "ids. Fewer fields, bigger free allowance.")] = None,
    verify: Annotated[bool, typer.Option(
        "--verify/--no-verify", "--verify-location/--no-verify-location",
        help="Check the location and category against the offline data first.")] = True,
    with_website_only: Annotated[bool, typer.Option(
        "--with-website-only", help="Drop results with no website.")] = False,
    operational_only: Annotated[bool, typer.Option(
        "--operational-only", help="Drop closed businesses.")] = False,
    include_seen: Annotated[bool, typer.Option(
        "--include-seen", help="Write businesses earlier runs already delivered "
                               "(default: every file holds only what's new).")] = False,
    forget_seen: Annotated[bool, typer.Option(
        "--forget-seen", help="Forget which businesses have been delivered, and exit.")] = False,
    resweep: Annotated[bool, typer.Option(
        "--resweep", help="Search the whole area again instead of carrying on from "
                          "where the last run stopped.")] = False,
    json_out: Annotated[Optional[str], typer.Option(
        "--json-out", help="Also dump the raw API responses to this JSON file.")] = None,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colour.")] = False,
    guided: Annotated[Optional[bool], typer.Option(
        "--guided/--no-guided", "--chat/--no-chat",
        help="Ask for the file, location, category and name one question at a time. "
             "Default: on when you run with no search options.")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress all output.")] = False,
    verbose: Annotated[bool, typer.Option(
        "--verbose", "-v", help="Log every tile of the sweep instead of one progress bar.")] = False,
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
):
    """[b]Business Lead[/b] — business leads from Google Places.

    Run it bare for the guided session, or pass search options for a one-shot run.
    Every result carries phone, website and a split address, and lands in
    [path]Business Lead/[/path] as csv, excel, pdf or json.
    """
    if no_color:
        console.no_color = True
    if version:
        from . import __url__
        from .constants import APP_TAGLINE
        console.print(f"{APP_TITLE} {VERSION}")
        console.print(f"  {APP_TAGLINE}", style="muted")
        console.print(f"  {__url__}", style="muted")
        raise typer.Exit()
    # .env is loaded before any branch that reads quota state: the caps, and
    # overrides like BUSINESSLEAD_USAGE_FILE, live there too.
    try:
        if daily_cap is not None:
            quota.parse_cap("--daily-cap", daily_cap)
        if monthly_cap is not None:
            quota.parse_cap("--monthly-cap", monthly_cap)
        if plan is not None:
            try:
                plan = plan_name(plan)          # a typo here would misbill
            except ValueError as exc:
                raise PlacesError(str(exc)) from None
        env_path, from_file = load_environment(env_file)
    except PlacesError as exc:
        console.print(f"✗ {exc}", style="bad")
        raise typer.Exit(1)
    if usage:
        raise typer.Exit(quota.main(["--month"] if verbose else [],
                                    daily_cap=daily_cap, monthly_cap=monthly_cap))
    if sessions:
        from . import history
        entries = history.recent(20)
        console.print(f"  {len(entries)} recent searches · "
                      f"{short_path(history.history_path())}\n")
        for entry in entries:
            console.print(f"  {history.when(entry)}   {history.describe(entry)}"
                          f"   {entry.get('rows', 0)} rows"
                          f"   {entry.get('requests', 0)} calls"
                          f"   {short_path(entry.get('file', '—'))}")
        raise typer.Exit(0)
    if locations:
        from .validate import gazetteer
        had_one = gazetteer.locations_path().exists()
        path = gazetteer.write_template()
        mine = gazetteer.custom()
        console.print(f"  {short_path(path)}", style="path")
        if not had_one:
            console.print("  created — add your places under the headings in it",
                          style="muted")
            raise typer.Exit(0)
        # markup=False throughout: the headings are literally [countries] and
        # [cities], which rich would otherwise read as style tags and swallow.
        for kind in gazetteer.KINDS:
            entries = getattr(mine, kind)
            if entries:
                console.print(f"\n  [{kind}]", style="muted", markup=False)
                for name_, hint in entries.values():
                    console.print(f"    · {name_}" + (f"  ({hint})" if hint else ""),
                                  markup=False)
        if not len(mine):
            console.print("  no places added yet", style="muted")
        for problem in mine.problems:
            console.print(f"  ! {problem}", style="warn", markup=False)
        raise typer.Exit(1 if mine.problems else 0)
    if forget_seen:
        from . import delivered, frontier
        store = delivered.Delivered()
        sweeps = frontier.Frontier()
        console.print(f"  forgot {store.forget():,} delivered businesses and "
                      f"{sweeps.forget():,} part-searched areas — the next search "
                      "starts from nothing", style="warn")
        raise typer.Exit(0)
    if reset_quota:
        cleared = quota.Quota().reset_today()
        console.print(f"  cleared today: {cleared or 'nothing recorded'}", style="warn")
        console.print("  Business Lead's bookkeeping only — Google still counts those calls.",
                      style="muted")
        raise typer.Exit(0)
    if convert_:
        try:
            raise typer.Exit(convert(convert_, to, quiet, pdf_all))
        except PlacesError as exc:
            console.print(f"✗ {exc}", style="bad")
            raise typer.Exit(1)
    wants_session = guided if guided is not None else (
        sys.stdin.isatty() and not quiet and not any([location, name, category, output]))

    if not quiet and not wants_session:
        console.print(banner())
        console.print()

    settings = Settings(
        location=location or "", name=name or "", category=category or "",
        output=output or "", output_source="--output" if output else "",
        api_key=api_key or "", radius=radius,
        plan=plan or DEFAULT_PLAN, plan_source="--plan" if plan else "",
        max_results=max_results, max_tiles=max_tiles, daily_cap=daily_cap,
        daily_cap_source="--daily-cap" if daily_cap is not None else "",
        monthly_cap=monthly_cap,
        monthly_cap_source="--monthly-cap" if monthly_cap is not None else "",
        included_type=type_, env_path=env_path,
        language=language, region=region,
        min_rating=min_rating, open_now=open_now, name_match=name_match,
        verify_location=verify, verify_category=verify,
        with_website_only=with_website_only, operational_only=operational_only,
        include_seen=include_seen, resweep=resweep, json_out=json_out, quiet=quiet, verbose=verbose, pdf_all=pdf_all,
    )

    try:
        if max_tiles is not None and max_tiles < 1:
            raise PlacesError("--max-tiles must be >= 1.")
        apply_env_defaults(settings, from_file)
        if wants_session:
            if not sys.stdin.isatty():
                raise PlacesError("--guided needs an interactive terminal.")
            from .session import run_session      # lazy: pulls in prompt_toolkit
            raise typer.Exit(run_session(settings))
        collect_inputs(settings)
        from .search import run                   # lazy: pulls in pandas
        code = run(settings)
    except PlacesError as exc:
        console.print(f"✗ {exc}", style="bad")
        raise typer.Exit(1)
    except RetryableError as exc:
        console.print(f"✗ the network (or Google) kept failing: {exc} — "
                      "nothing was lost, run it again", style="bad")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("■ Interrupted.", style="bad")
        raise typer.Exit(130)
    raise typer.Exit(code)
