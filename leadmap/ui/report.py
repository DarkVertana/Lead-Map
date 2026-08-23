"""The ⏺ / ⎿ voice of the tool, and the paths and bars it prints."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.text import Text

from .theme import BRANCH, BULLET


def short_path(path: str | Path) -> str:
    """Relative to cwd when it lives there, else with $HOME collapsed to ~."""
    full = Path(path).expanduser().resolve()
    try:
        relative = full.relative_to(Path.cwd())
        if str(relative) != ".":            # the cwd itself reads better as a full path
            return str(relative)
    except ValueError:
        pass
    try:
        return "~/" + str(full.relative_to(Path.home()))
    except ValueError:
        return str(full)


def elide(text: str, limit: int = 52) -> str:
    """Shorten a long path to its last components rather than wrapping it."""
    if len(text) <= limit:
        return text
    parts = Path(text).parts
    for keep in range(2, len(parts)):
        candidate = "…/" + str(Path(*parts[-keep:]))
        if len(candidate) > limit:
            return "…/" + str(Path(*parts[-(keep - 1):])) if keep > 2 else candidate
    return text[-limit:]


def mask_key(key: str) -> str:
    if not key:
        return ""
    return f"{key[:6]}…{key[-4:]}" if len(key) > 14 else f"…{key[-4:]}"

class Reporter:
    """Claude-Code-flavoured output: ⏺ steps with ⎿ detail lines, and a live
    spinner that reports what it is doing while it does it."""

    def __init__(self, console: Console, quiet: bool = False):
        self.console = console
        self.quiet = quiet
        self._status = None

    # -- plain output --------------------------------------------------------
    def print(self, renderable="", **kwargs):
        if not self.quiet:
            self.console.print(renderable, **kwargs)

    def line(self, text: Text):
        """One-line output: long values are elided rather than wrapped."""
        self.print(text, no_wrap=True, overflow="ellipsis", crop=True)

    def step(self, text: str, mark: str = BULLET, style: str = "brand"):
        line = Text()
        line.append(f"{mark} ", style=style)
        line.append(text, style="bold")
        self.line(line)

    def detail(self, label: str, value=None, style: str = "muted"):
        line = Text("  ")
        line.append(f"{BRANCH} ", style="muted")
        if value is None:
            line.append(label, style=style)
        else:
            line.append(f"{label:<10} ", style="muted")
            line.append_text(value if isinstance(value, Text) else Text(str(value)))
        self.line(line)

    def note(self, text: str, mark: str = "✓", style: str = "ok"):
        line = Text("  ")
        line.append(f"{BRANCH} ", style="muted")
        line.append(f"{mark} ", style=style)
        line.append(text, style="muted")
        self.line(line)

    def error(self, text: str):
        self.console.print(Text(f"✗ {text}", style="bad"))

    # -- live spinner --------------------------------------------------------
    def start_work(self, text: str):
        if self.quiet:
            return
        self._status = self.console.status(Text(text, style="muted"),
                                           spinner="pulse", spinner_style="brand")
        self._status.start()

    def working(self, verb: str, detail: str, elapsed: float, hint="ctrl+c to stop"):
        if self.quiet or not self._status:
            return
        line = Text()
        line.append(f"{verb}… ", style="brand")
        line.append(detail, style="muted")
        line.append(f"  ({elapsed:.0f}s · {hint})", style="muted")
        self._status.update(line)

    def stop_work(self):
        if self._status:
            self._status.stop()
            self._status = None


def progress_bar(done: int, total: int, width: int = 12) -> str:
    filled = 0 if not total else round(width * done / total)
    return "▰" * filled + "▱" * (width - filled)
