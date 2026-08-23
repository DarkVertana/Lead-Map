"""
Guided terminal session, in the shape of Claude Code's interface.

Not a chat: there are no bubbles and no transcript. Output scrolls inline in the
real terminal — ⏺ steps with ⎿ detail lines — and the only interactive element is
a rounded input box that appears at the bottom, takes one answer, and disappears
again, leaving the answer behind as a line of output.

The session asks one question at a time, in this order:

    Location  →  Category  →  Name  →  Output file

then hands the finished Settings to ``leadmap.run``, which renders the
search itself. Entry point: ``run_session(settings)``.
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (BufferControl, FormattedTextControl, HSplit,
                                   Layout, VSplit, Window)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import (AfterInput, BeforeInput,
                                              ConditionalProcessor)
from prompt_toolkit.styles import Style
from rich.text import Text

from . import export, history, quota, search
from .config import Settings
from .constants import APP_TITLE, ENV_KEYS, SEARCH_SKU, VERSION
from .errors import PlacesError
from .ui.banner import banner
from .ui.report import mask_key, progress_bar, short_path
from .ui.theme import BRANCH, BULLET, console
from .validate import gazetteer, place_types
from .validate.gazetteer import Match

console = console

# A command is a word, optionally followed by arguments: /back, /category food.
# Anything whose first token holds a path — /Users/tvita/Desktop/leads.csv — is
# an answer, not a command.
COMMAND = re.compile(r"/(?P<name>[a-zA-Z?][a-zA-Z-]{0,15})(?:\s+(?P<args>.*))?")


class Cancelled(Exception):
    """The user asked to leave, or stdin is not a terminal."""


# Editors type their own commands into whatever is on screen: VS Code activates
# the project virtualenv in the terminal a moment after it opens, and the line
# lands in our box. It is not an answer, so it is ignored rather than submitted.
INJECTED = re.compile(
    r"""\s*(?:source|\.)\s+["']?.*/activate(?:\.\w+)?["']?\s*$"""
    r"""|\s*(?:conda|pyenv|nvm|rvm)\s+activate\b.*""",
    re.IGNORECASE)


# ---------------------------------------------------------------------------
# The input box
# ---------------------------------------------------------------------------

_PROMPT_STYLE = Style.from_dict({
    "frame": "#e08c48",
    "arrow": "#e08c48 bold",
    "input": "",
    "placeholder": "#6c6c6c",
    "hint": "#6c6c6c",
    "note": "#e08c48",
})

_HISTORIES: dict[str, InMemoryHistory] = {}


def _rule(left: str, right: str) -> VSplit:
    """A ─────── border row with rounded corners, sized to the terminal.

    One column is left spare on the right: a box that reaches the last cell
    makes terminals wrap, which would cost a blank line per row.
    """
    return VSplit([
        Window(FormattedTextControl(left), width=1, style="class:frame"),
        Window(char="─", style="class:frame"),
        Window(FormattedTextControl(right), width=1, style="class:frame"),
        Window(width=1),
    ], height=1)


def read_line(*, key: str = "", placeholder: str = "", hint: str = "") -> str:
    """Show the box, return one line. Raises Cancelled on ctrl+c / ctrl+d.

    Nothing is ever typed into the box for you — a default is shown greyed out
    as the placeholder and applied by the caller when the answer comes back
    empty, so you never have to delete someone else's text to write your own.

    The box grows as the answer wraps and is erased once the answer is in, so
    the terminal keeps a clean record of the session rather than a redrawn UI.
    """
    if not sys.stdin.isatty():
        raise Cancelled("not a terminal")

    history = _HISTORIES.setdefault(key or "_", InMemoryHistory())
    buffer = Buffer(multiline=False, history=history)

    def height() -> Dimension:
        """One row, plus one more for every line the answer wraps onto."""
        try:
            columns = get_app().output.get_size().columns
        except Exception:                                       # noqa: BLE001
            columns = 80
        inner = max(8, columns - 5)      # two borders, two paddings, one spare
        needed = len(buffer.text) + 3               # the '› ' prefix and cursor
        return Dimension.exact(max(1, -(-needed // inner)))

    body = VSplit([
        Window(char="│", width=1, style="class:frame"),
        Window(width=1),
        Window(
            BufferControl(
                buffer=buffer,
                input_processors=[
                    BeforeInput("› ", style="class:arrow"),
                    ConditionalProcessor(
                        AfterInput(placeholder or "", style="class:placeholder"),
                        Condition(lambda: not buffer.text and bool(placeholder)),
                    ),
                ],
            ),
            wrap_lines=True,
            style="class:input",
        ),
        Window(width=1),
        Window(char="│", width=1, style="class:frame"),
        Window(width=1),
    ], height=height)

    note = {"text": ""}          # replaces the hint line when there's something to say
    leaving = {"armed": False}   # ctrl+c only leaves on the second press

    def hint_line():
        if note["text"]:
            return [("class:note", f"  {note['text']}")]
        return [("class:hint", f"  {hint}")] if hint else []

    def clear_note(_=None) -> None:
        """Typing anything takes back a half-pressed ctrl+c."""
        note["text"] = ""
        leaving["armed"] = False

    buffer.on_text_changed += clear_note

    rows = [_rule("╭", "╮"), body, _rule("╰", "╯"),
            Window(FormattedTextControl(hint_line), height=1)]

    keys = KeyBindings()

    @keys.add("enter")
    def _accept(event) -> None:
        text = buffer.text.strip()
        if INJECTED.fullmatch(text):
            buffer.reset()
            note["text"] = "ignored a command your terminal typed in here"
            return
        if text:
            buffer.append_to_history()
        event.app.exit(result=text)

    def _ask_to_leave(event) -> None:
        """First press clears the line; a second one in a row leaves."""
        if buffer.text:
            buffer.reset()
            note["text"] = "cleared — ctrl+c again to leave"
        elif leaving["armed"]:
            event.app.exit(exception=Cancelled())
            return
        else:
            note["text"] = "press ctrl+c again to leave"
        leaving["armed"] = True

    keys.add("c-c")(_ask_to_leave)
    keys.add("c-d", filter=Condition(lambda: not buffer.text))(_ask_to_leave)

    app: Application = Application(
        layout=Layout(HSplit(rows)),
        key_bindings=keys,
        style=_PROMPT_STYLE,
        full_screen=False,
        erase_when_done=True,
        mouse_support=False,
    )
    try:
        return app.run()
    except EOFError:                    # the terminal went away under us
        raise Cancelled("input closed") from None


# ---------------------------------------------------------------------------
# Output helpers — the same vocabulary leadmap.run uses
# ---------------------------------------------------------------------------

def step(title: str, mark: str = BULLET, style: str = "brand") -> None:
    line = Text()
    line.append(f"{mark} ", style=style)
    line.append(title, style="bold")
    console.print(line)


def detail(text: str, style: str = "muted") -> None:
    line = Text("  ")
    line.append(f"{BRANCH} ", style="muted")
    line.append(text, style=style)
    console.print(line)


def field(label: str, value: str, style: str = "value", width: int = 10) -> None:
    line = Text("  ")
    line.append(f"{BRANCH} ", style="muted")
    line.append(f"{label:<{width}} ", style="muted")
    line.append(value, style=style)
    console.print(line, no_wrap=True, overflow="ellipsis", crop=True)


def answered(value: str, *, empty: str = "skipped", blank: bool = True) -> None:
    line = Text("  ")
    line.append("› ", style="ok")
    line.append(value or empty, style="ok" if value else "muted")
    console.print(line)
    if blank:
        console.print()


# ---------------------------------------------------------------------------
# The questions
# ---------------------------------------------------------------------------

@dataclass
class Question:
    key: str                                        # attribute on Settings
    title: str
    hint: str
    placeholder: str = ""
    required: Callable[[Settings], bool] = lambda s: False
    default: Callable[[Settings], str] = lambda s: ""
    parse: Optional[Callable[[str, "Settings"], object]] = None
    show: Optional[Callable[[object], str]] = None
    empty: str = "skipped"
    check: Optional[Callable[[str, "Settings"], gazetteer.Verdict]] = None
    insist_flag: str = ""        # Settings flag to clear when you answer twice


QUESTIONS: list[Question] = [
    Question(
        key="location",
        title="Location",
        hint="Where should I search? City, area, postcode or full address.",
        placeholder="Austin, TX   ·   560001, Bangalore",
        required=lambda s: True,
        default=lambda s: s.location,
        check=lambda answer, s: gazetteer.verify(answer, region=s.region),
        insist_flag="verify_location",
    ),
    Question(
        key="category",
        title="Category",
        hint="What kind of business? Leave empty if you want one named place.",
        placeholder="coffee shop   ·   dentist   ·   plumber",
        default=lambda s: s.category,
        empty="any category",
        check=lambda answer, s: place_types.verify(answer),
        insist_flag="verify_category",
    ),
    Question(
        key="name",
        title="Name",
        hint="A particular business — or skip it and take the whole category.",
        placeholder="Starbucks   ·   enter to skip",
        # one of category / name has to be there — name carries it if category was skipped
        required=lambda s: not s.category,
        default=lambda s: s.name,
        empty="any name",
    ),
    Question(
        key="output",
        title="Output",
        hint="csv, excel or pdf — or a filename if you want to choose it.",
        placeholder="csv   ·   excel   ·   pdf   ·   leads.xlsx",
        required=lambda s: True,
        default=lambda s: s.output or "csv",
        parse=lambda answer, s: output_file(answer, s),
        check=lambda answer, s: check_output(answer),
    ),
]


# What you can type at the Output question, and what it writes.
FORMATS = {
    "csv": ".csv", "excel": ".xlsx", "xlsx": ".xlsx", "xls": ".xlsx",
    "spreadsheet": ".xlsx", "sheet": ".xlsx", "workbook": ".xlsx",
    "pdf": ".pdf", "print": ".pdf", "json": ".json",
}
SUFFIXES = {".csv", ".xlsx", ".xls", ".pdf", ".json"}


def output_file(answer: str, settings: "Settings") -> str:
    """'excel' → coffee_shop_pune.xlsx; 'leads.pdf' → leads.pdf."""
    word = answer.strip().lower()
    if word in FORMATS:
        return str(Path(settings.default_filename()).with_suffix(FORMATS[word]))
    path = Path(answer.strip())
    return str(path if path.suffix else path.with_suffix(".csv"))


def check_output(answer: str) -> gazetteer.Verdict:
    verdict = gazetteer.Verdict(location=answer)
    word = answer.strip().lower()
    suffix = Path(answer.strip()).suffix.lower()
    if word in FORMATS or not suffix or suffix in SUFFIXES:
        verdict.matches.append(Match("output", answer.strip()))
        return verdict
    verdict.problems.append(f"I can't write {suffix} — csv, excel, pdf or json")
    verdict.suggestions = ["csv", "excel", "pdf"]
    return verdict


@dataclass
class Command:
    """One slash command.

    `run` prints whatever it wants to show and returns an action for the
    question loop: None to ask the same question again, "back" to step back a
    question, "quit" to leave the session.
    """
    names: tuple[str, ...]
    args: str
    summary: str
    run: Callable[[str, Settings], Optional[str]]


def _cmd_help(args: str, settings: Settings) -> None:
    step("Commands")
    for command in COMMANDS:
        name = "/" + command.names[0] + (f" {command.args}" if command.args else "")
        alias = (f"   ({', '.join('/' + n for n in command.names[1:])})"
                 if len(command.names) > 1 else "")
        field(name, command.summary + alias, style="muted", width=16)
    console.print()


def _cmd_version(args: str, settings: Settings) -> None:
    import platform
    step(f"{APP_TITLE} {VERSION}")
    field("python", platform.python_version(), style="muted")
    field("installed", short_path(Path(__file__).resolve().parent), style="muted")
    field("billed as", f"{SEARCH_SKU.label}  ·  {SEARCH_SKU.free_per_month:,} free/month",
          style="muted")
    field("place types", f"{len(place_types.ALL)} categories · "
                         f"{len(place_types.TABLE_B)} not filterable",
          style="muted", width=12)
    console.print()


def _cmd_quota(args: str, settings: Settings) -> None:
    ledger = quota.Quota(daily_cap=settings.daily_cap, monthly_cap=settings.monthly_cap)
    free_tier_panel(ledger)
    geo = ledger.status(quota.GEOCODING)
    field("geocoding", f"{geo.used_month:,} of {geo.sku.free_per_month:,} used "
                       f"this month", style="muted")
    console.print()


def _cmd_daily_cap(args: str, settings: Settings) -> None:
    """Borrow from the rest of the month instead of pretending today was free."""
    ledger = quota.Quota(daily_cap=settings.daily_cap, monthly_cap=settings.monthly_cap)
    status = ledger.status(SEARCH_SKU)
    if not args.strip():
        step("Today's cap")
        field("allowance", f"{status.allowance_today:,} calls"
                           + (" (set by --daily-cap)" if settings.daily_cap else
                              " — this month's remainder ÷ days left"))
        field("used", f"{status.used_today:,}  ·  {status.left_today:,} left")
        field("month", f"{status.left_month:,} of {status.sku.free_per_month:,} left")
        detail("/daily-cap N sets the whole allowance · /borrow N just adds to it")
        console.print()
        return

    try:
        wanted = int(args.split()[0])
    except ValueError:
        detail(f"“{args.strip()}” isn't a number — try /daily-cap 60", style="warn")
        console.print()
        return
    if wanted < 1:
        detail("that would leave you nothing to search with", style="warn")
        console.print()
        return

    settings.daily_cap = wanted
    fresh = quota.Quota(daily_cap=wanted, monthly_cap=settings.monthly_cap)
    now = fresh.status(SEARCH_SKU)
    step(f"Today's cap is now {wanted:,}", mark="✓", style="ok")
    field("left today", f"{now.left_today:,} calls"
                        + ("" if now.left_today else " — the month is what's short here"))
    field("left this month", f"{now.left_month:,}")
    detail("borrowed from the rest of the month; the monthly free tier still holds")
    console.print()


def _cmd_borrow(args: str, settings: Settings) -> None:
    """`/borrow 40` — forty more calls today, out of the month's remainder."""
    ledger = quota.Quota(daily_cap=settings.daily_cap, monthly_cap=settings.monthly_cap)
    status = ledger.status(SEARCH_SKU)
    try:
        extra = int(args.split()[0])
    except (IndexError, ValueError):
        detail("how many? /borrow 40 gives today forty more calls "
               f"({status.left_month:,} left this month)", style="warn")
        console.print()
        return
    if extra < 1:
        detail("borrow a positive number of calls", style="warn")
        console.print()
        return
    if extra > status.left_month:
        detail(f"only {status.left_month:,} left this month — that's the ceiling, "
               "and it isn't one LeadMap can lift", style="warn")
        extra = status.left_month
        if not extra:
            console.print()
            return

    settings.daily_cap = status.used_today + extra
    now = quota.Quota(daily_cap=settings.daily_cap,
                      monthly_cap=settings.monthly_cap).status(SEARCH_SKU)
    step(f"Borrowed {extra:,} calls for today", mark="✓", style="ok")
    field("left today", f"{now.left_today:,}")
    field("left this month", f"{now.left_month:,} of {now.sku.free_per_month:,}")
    detail("taken from the rest of the month — the monthly free tier still holds")
    console.print()


def _cmd_reset_quota(args: str, settings: Settings) -> None:
    cleared = quota.Quota().reset_today()
    step("Today's counters cleared", mark="⚠", style="warn")
    for key, count in (cleared or {}).items():
        field(key, f"{count:,} calls forgotten", style="warn")
    if not cleared:
        field("today", "nothing had been recorded", style="muted")
    detail("this clears LeadMap's bookkeeping only — Google has still been called, "
           "and still counts every one of them", style="warn")
    detail("for development. The real limit lives in the Cloud console.")
    console.print()


def _cmd_category(args: str, settings: Settings) -> None:
    query = args.strip().lower()
    if not query:
        step(f"Categories · {len(place_types.ALL)} place types Google accepts")
        for heading, types in place_types.TABLE_A.items():
            field(heading, f"{len(types):>3}   {', '.join(types[:3])} …", style="muted")
        detail("/category <word> searches them · /category food lists that group")
        console.print()
        return

    for heading, types in place_types.TABLE_A.items():
        if query in heading.lower():
            step(f"{heading} · {len(types)} types")
            for start in range(0, len(types), 3):
                detail("   ".join(f"{t:<26}" for t in types[start:start + 3]).rstrip())
            console.print()
            return

    hits = sorted(t for t in place_types.ALL if query in t)
    aliases = sorted(a for a in place_types.ALIASES if query in a)
    step(f"Categories matching “{args.strip()}”")
    for start in range(0, len(hits[:30]), 3):
        detail("   ".join(f"{t:<26}" for t in hits[start:start + 3]).rstrip())
    if len(hits) > 30:
        detail(f"… and {len(hits) - 30} more", style="muted")
    if aliases:
        field("also understood", ", ".join(f"{a} → {place_types.ALIASES[a]}"
                                           for a in aliases[:5]), style="muted")
    if not hits and not aliases:
        detail(f"nothing matches “{args.strip()}” — /category lists every group",
               style="warn")
    console.print()


def _cmd_sessions(args: str, settings: Settings) -> None:
    entries = history.recent(12)
    step(f"Recent searches · {len(entries)} shown")
    if not entries:
        detail("nothing recorded yet — a search is logged once it writes a file")
        console.print()
        return
    for entry in entries:
        field(history.when(entry),
              f"{history.describe(entry)}  ·  {entry.get('rows', 0)} rows  ·  "
              f"{entry.get('requests', 0)} calls  ·  "
              f"{short_path(entry.get('file', '—'))}", style="muted")
    detail(f"kept in {short_path(history.history_path())}")
    console.print()


def _cmd_settings(args: str, settings: Settings) -> None:
    step("This search, so far")
    for label, value in (("location", settings.location), ("category", settings.category),
                         ("name", settings.name), ("output", settings.output)):
        field(label, value or "—", style="value" if value else "muted")
    field("coverage", f"{settings.grid}×{settings.grid} tiles" if settings.grid > 1
          else f"automatic, up to {settings.max_tiles} tiles", style="muted")
    field("api key", f"{mask_key(settings.api_key)} · from "
                     f"{settings.api_key_source or 'environment'}", style="muted")
    field("checks", ("location " + ("on" if settings.verify_location else "off")
                     + " · category " + ("on" if settings.verify_category else "off")),
          style="muted")
    console.print()


def _cmd_formats(args: str, settings: Settings) -> None:
    step("Output formats")
    field("csv", "every column · UTF-8 BOM, opens straight in Excel", style="muted")
    field("excel", "every column · .xlsx workbook", style="muted")
    field("json", "every column · one object per business", style="muted")
    field("pdf", "the essential twelve, landscape — --pdf-all for the rest",
          style="muted")
    field("folder", short_path(export.output_root()) + "/<date>/", style="muted")
    detail("a finished file can be re-written any time: "
           "leadmap --convert FILE --to pdf")
    console.print()


def _cmd_where(args: str, settings: Settings) -> None:
    step("Where things live")
    field("output", short_path(export.output_path_for(settings)), style="path")
    field("usage ledger", short_path(quota.default_ledger_path()),
          style="muted", width=12)
    field("history", short_path(history.history_path()), style="muted")
    field("env file", short_path(settings.env_path) if settings.env_path else "—",
          style="muted")
    console.print()


def _cmd_open(args: str, settings: Settings) -> None:
    import subprocess
    target = export.output_path_for(settings).parent
    target.mkdir(parents=True, exist_ok=True)
    opener = {"darwin": "open", "win32": "explorer"}.get(sys.platform, "xdg-open")
    step(f"Opening {short_path(target)}")
    try:
        subprocess.run([opener, str(target)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:                                      # noqa: BLE001
        detail(f"couldn't open it: {exc}", style="bad")
    console.print()


def _cmd_clear(args: str, settings: Settings) -> None:
    console.clear()


def _cmd_back(args: str, settings: Settings) -> str:
    return "back"


def _cmd_quit(args: str, settings: Settings) -> str:
    return "quit"


COMMANDS: list[Command] = [
    Command(("help", "?"), "", "these commands", _cmd_help),
    Command(("back", "b"), "", "change the previous answer", _cmd_back),
    Command(("category", "categories", "cat"), "[word]",
            "the place types Google accepts", _cmd_category),
    Command(("quota", "usage"), "", "what's left of the free tier today", _cmd_quota),
    Command(("borrow",), "N", "N more calls today, taken from the month",
            _cmd_borrow),
    Command(("daily-cap", "limit"), "[N]", "set today's whole allowance",
            _cmd_daily_cap),
    Command(("sessions", "history"), "", "searches you've already run", _cmd_sessions),
    Command(("settings", "config"), "", "the answers and options in play", _cmd_settings),
    Command(("formats", "output"), "", "what each file format carries", _cmd_formats),
    Command(("where", "paths"), "", "where files and records are kept", _cmd_where),
    Command(("open", "reveal"), "", "open the output folder", _cmd_open),
    Command(("clear", "cls"), "", "clear the screen", _cmd_clear),
    Command(("version", "v"), "", "what's running, and what it bills as", _cmd_version),
    Command(("reset-quota",), "", "forget today's usage (development only)",
            _cmd_reset_quota),
    Command(("quit", "exit", "q"), "", "leave the session", _cmd_quit),
]
BY_NAME = {name: command for command in COMMANDS for name in command.names}


def handle_command(text: str, settings: Settings) -> Optional[str]:
    """Run a slash command; returns 'back', 'quit', or None to ask again."""
    match = COMMAND.fullmatch(text.strip())
    if not match:
        return None
    command = BY_NAME.get(match.group("name").lower())
    if not command:
        detail(f"unknown command /{match.group('name')} — /help lists them all",
               style="warn")
        console.print()
        return None
    return command.run((match.group("args") or "").strip(), settings)


def collect(settings: Settings) -> bool:
    """Ask every question in order. False if the user backed all the way out."""
    index = 0
    insisted: dict[str, str] = {}      # answers the check rejected once already
    while index < len(QUESTIONS):
        question = QUESTIONS[index]
        step(question.title)
        detail(f"{question.hint}")
        console.print()

        while True:
            default = question.default(settings)
            hint = f"{index + 1}/{len(QUESTIONS)}   "
            hint += "enter to accept" if default else "enter to submit"
            if index:
                hint += "   /back to change the last answer"
            hint += "   ctrl+c twice to quit"
            answer = read_line(key=question.key, hint=hint,
                               placeholder=default or question.placeholder)
            if not answer:
                answer = default

            if COMMAND.fullmatch(answer.strip()):
                action = handle_command(answer, settings)
                if action == "quit":
                    raise Cancelled()
                if action == "back":
                    detail("going back" if index else "already at the first question")
                    console.print()
                    index = max(0, index - 1)
                    break
                continue

            if not answer and question.required(settings):
                detail("I need that one to carry on.", style="warn")
                console.print()
                continue

            remarks: list[tuple[str, str]] = []
            if question.check and answer:
                verdict = question.check(answer, settings)
                if not verdict.ok and answer != insisted.get(question.key):
                    answered(answer, blank=False)
                    detail(f"✗ {verdict.reason()}", style="bad")
                    if verdict.suggestions:
                        detail("did you mean " + " · ".join(verdict.suggestions) + "?")
                    detail("send it again to use it anyway")
                    console.print()
                    insisted[question.key] = answer
                    continue
                if not verdict.ok:
                    if question.insist_flag:               # you asked for it twice
                        setattr(settings, question.insist_flag, False)
                    remarks.append(("taking it as given, unrecognised", "warn"))
                else:
                    remarks += [(f"! {hint}", "warn") for hint in verdict.hints]
                    remarks += [(f"· {note}", "muted") for note in verdict.notes]

            value = question.parse(answer, settings) if question.parse else answer
            setattr(settings, question.key, value)
            answered(question.show(value) if question.show and value else str(value or ""),
                     empty=question.empty, blank=not remarks)
            for text, style in remarks:
                detail(text, style=style)
            if remarks:
                console.print()
            index += 1
            break
    return True


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------

def day_strip(ledger: quota.Quota, sku: quota.Sku, days: int = 7) -> str:
    """'Mon 0   Tue 24   Wed 8 … today 17' — the week's spending at a glance."""
    parts = []
    for day, used in ledger.recent(sku, days):
        label = "today" if day == ledger.today else day.strftime("%a")
        parts.append(f"{label} {used:,}")
    return "   ".join(parts)


def free_tier_panel(ledger: quota.Quota) -> None:
    """The three-line free-tier readout, at startup and on /quota."""
    free = ledger.status(SEARCH_SKU)
    step(f"Free tier · {free.sku.label}")
    field("this month", f"{free.used_month:,} of {free.sku.free_per_month:,} used  ·  "
                        f"{free.left_month:,} left  ·  resets "
                        f"{quota.human_date(ledger.next_month())}")
    field("today", f"{free.used_today:,} of {free.allowance_today:,} used  ·  "
                   f"{free.left_today:,} left  "
                   f"{progress_bar(free.used_today, free.allowance_today, 10)}")
    field("by day", day_strip(ledger, free.sku), style="muted")


def plan(settings: Settings) -> None:
    step("Ready when you are")
    field("location", settings.location)
    field("category", settings.category or "—",
          style="value" if settings.category else "muted")
    field("name", settings.name or "—",
          style="value" if settings.name else "muted")
    if settings.grid > 1:                      # only set by --grid or PLACES_GRID
        field("coverage", f"{settings.grid}×{settings.grid} tiles")
    else:
        field("coverage", "everything in the area", style="value")
    field("output", short_path(export.output_path_for(settings)), style="path")
    left = quota.Quota(daily_cap=settings.daily_cap,
                       monthly_cap=settings.monthly_cap).status(SEARCH_SKU)
    field("free tier", f"{left.left_today:,} calls left today", style="muted")
    console.print()


def confirm(settings: Settings) -> bool:
    answer = read_line(key="__confirm__", placeholder="yes",
                       hint="enter to run   ·   n to change an answer   ·   ctrl+c twice to quit")
    if answer.lower() in ("n", "no", "back", "/back", "change"):
        answered("let's change something", empty="")
        return False
    answered("running the search", empty="")
    return True


def another_format(settings: Settings) -> None:
    """Offer the same results in another format. No search, no API calls."""
    path = export.output_path_for(settings)
    if not path.exists() or path.suffix.lower() not in export.READABLE:
        return
    step("Another copy?")
    detail("pdf, excel, json or csv — costs nothing, it just re-writes what you have.")
    console.print()

    while True:
        answer = read_line(key="__format__",
                           placeholder="pdf   ·   excel   ·   json   ·   enter to skip",
                           hint="enter to skip   ·   several at once is fine   ·   "
                                "ctrl+c twice to quit")
        if not answer.strip():
            answered("", empty="no thanks")
            return
        try:
            written = export.convert_file(path, re.split(r"[,\s]+", answer.strip()),
                                          pdf_all=settings.pdf_all)
        except PlacesError as exc:
            answered(answer.strip(), blank=False)
            detail(f"✗ {exc}", style="bad")
            console.print()
            continue
        answered(answer.strip(), blank=False)
        for target in written or [path]:
            detail(f"✓ {short_path(target)}"
                   + ("" if written else " — already that format"),
                   style="ok" if written else "muted")
        console.print()
        return


def again() -> bool:
    step("Another search?")
    detail("y to set up a new one, or enter to finish.")
    console.print()
    answer = read_line(key="__again__", placeholder="y / n",
                       hint="enter to finish   ·   ctrl+c twice to quit")
    yes = answer.lower() in ("y", "yes", "again", "more")
    answered("starting fresh" if yes else "done", empty="")
    return yes


def _reset(settings: Settings) -> Settings:
    """A new search that keeps the credentials and the global options."""
    return Settings(
        api_key=settings.api_key, api_key_source=settings.api_key_source,
        env_path=settings.env_path, radius=settings.radius, grid=settings.grid,
        max_results=settings.max_results, included_type=settings.included_type,
        language=settings.language, region=settings.region,
        min_rating=settings.min_rating, open_now=settings.open_now,
        name_match=settings.name_match, with_website_only=settings.with_website_only,
        operational_only=settings.operational_only,
    )


def blocked(settings: Settings) -> bool:
    """Out of quota: keep taking commands until there is some, or they leave.

    Searching is what the free tier limits — talking to the tool isn't, and
    /reset-quota is no use to anyone if running out is what locks you out of it.
    """
    while True:
        answer = read_line(
            key="__blocked__",
            placeholder="/borrow 40   ·   /reset-quota   ·   /quota   ·   /help",
            hint="commands only — searching resumes the moment there's quota   ·   "
                 "ctrl+c twice to quit")
        answer = answer.strip()
        if not answer:
            answered("", empty="checking again")
        elif COMMAND.fullmatch(answer):
            answered(answer, blank=False)
            console.print()
            if handle_command(answer, settings) == "quit":
                raise Cancelled()
        else:
            answered(answer, blank=False)
            detail("no calls left today, so there's nothing to search with yet — "
                   "/borrow N or /reset-quota, /help for the rest", style="warn")
            console.print()
            continue

        left = quota.Quota(daily_cap=settings.daily_cap,
                           monthly_cap=settings.monthly_cap).left_today(SEARCH_SKU)
        if left > 0:
            step(f"{left:,} calls available — carrying on", mark="✓", style="ok")
            console.print()
            return True


def ensure_quota(settings: Settings) -> bool:
    """True when a search can run — after talking it over, if need be."""
    ledger = quota.Quota(daily_cap=settings.daily_cap, monthly_cap=settings.monthly_cap)
    free = ledger.status(SEARCH_SKU)
    if free.left_today > 0:
        return True

    step("Out of free calls for today", mark="✗", style="bad")
    if free.left_month <= 0:
        detail(f"the {free.sku.free_per_month:,} free calls for {ledger.month_name()} "
               f"are gone — they come back on "
               f"{quota.human_date(ledger.next_month())}")
    else:
        detail(f"today's share is spent · {free.left_month:,} left this month, "
               "back tomorrow")
        detail("/borrow N takes N more calls from the rest of the month")
    detail("commands still work — /borrow, /reset-quota, /quota, /sessions, /help")
    console.print()
    return blocked(settings)


def run_session(settings: Settings) -> int:
    """Guided run: ask, confirm, search, offer another. Returns an exit code."""
    console.print(banner())
    console.print()

    if not settings.api_key:
        step("No API key", mark="✗", style="bad")
        detail(f"add {ENV_KEYS[0]}=AIza… to "
               f"{short_path(settings.env_path) if settings.env_path else '.env'}")
        detail("then enable 'Places API (New)' + 'Geocoding API' in Google Cloud")
        console.print()
        return 1

    threading.Thread(target=gazetteer.warm, daemon=True).start()

    ledger = quota.Quota(daily_cap=settings.daily_cap,
                         monthly_cap=settings.monthly_cap)
    free_tier_panel(ledger)
    console.print()

    step("Ready")
    field("api key", f"{mask_key(settings.api_key)} · from "
                     f"{settings.api_key_source or 'environment'}", style="muted")
    field("asking", "location, category, name — then a filename", style="muted")
    field("commands", "/help lists them · /category /quota /sessions /version",
          style="muted")
    console.print()

    code = 0
    try:
        while True:
            if not ensure_quota(settings):        # talk first, search when able
                return 1
            while True:
                collect(settings)
                plan(settings)
                if confirm(settings):
                    break
            code = search.run(settings)
            console.print()
            if code == 0:
                another_format(settings)
            if not again():
                break
            settings = _reset(settings)
    except Cancelled:
        console.print()
        console.print(Text("■ Left the session.", style="bad"))
        return 130
    except KeyboardInterrupt:
        console.print(Text("■ Interrupted.", style="bad"))
        return 130
    except PlacesError as exc:
        console.print(Text(f"✗ {exc}", style="bad"))
        return 1
    return code
