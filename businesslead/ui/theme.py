"""One console, one palette, one spinner — shared by every part of the UI."""

from __future__ import annotations

from rich import spinner as rich_spinner
from rich.console import Console
from rich.theme import Theme


THEME = Theme({
    "brand": "#e08c48",
    "shadow": "#6b3a1c",
    "muted": "grey58",
    "ok": "green",
    "warn": "yellow",
    "bad": "red",
    "value": "bold",
    "path": "cyan",
})

# A slowly pulsing asterisk, in the spirit of the Claude Code spinner.
rich_spinner.SPINNERS["pulse"] = {
    "interval": 110,
    "frames": ["✻", "✼", "✽", "✾", "✽", "✼"],
}

# Verbs the spinner rotates through while it works.
WORK_VERBS = ["Scouting", "Sweeping", "Percolating", "Collating",
              "Canvassing", "Distilling", "Rounding up"]

BULLET = "⏺"
BRANCH = "⎿"

console = Console(theme=THEME, highlight=False)


def __getattr__(name: str):
    # questionary drags in all of prompt_toolkit; only the one-shot prompts
    # need it, so the style is built the first time somebody asks for it.
    if name == "QUESTION_STYLE":
        import questionary
        style = questionary.Style([
            ("qmark", "fg:#e08c48 bold"),
            ("question", "bold"),
            ("answer", "fg:#5fd7af"),
            ("instruction", "fg:#808080"),
        ])
        globals()["QUESTION_STYLE"] = style
        return style
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
