"""Settings, and the three places they come from: flags, environment, .env."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import questionary
import typer
from dotenv import dotenv_values, find_dotenv, load_dotenv

from .constants import DEFAULT_TILE_BUDGET, ENV_KEYS
from .errors import PlacesError
from .ui.report import short_path
from .ui.theme import QUESTION_STYLE, console


def ask(label: str, default: str = "", required: bool = False) -> str:
    """questionary prompt; Ctrl-C / Ctrl-D exits cleanly."""
    answer = questionary.text(
        label, default=default, qmark="›", style=QUESTION_STYLE,
        instruction="(Enter to skip) " if not required and not default else None,
        validate=(lambda text: True if text.strip() else "required") if required else None,
    ).ask()
    if answer is None:
        console.print("■ Interrupted.", style="bad")
        raise typer.Exit(130)
    return answer.strip()

@dataclass
class Settings:
    location: str = ""
    name: str = ""
    category: str = ""
    output: str = ""
    api_key: str = ""
    api_key_source: str = ""
    env_path: Optional[str] = None
    radius: Optional[float] = None
    grid: int = 1
    max_results: Optional[int] = None
    max_tiles: int = DEFAULT_TILE_BUDGET
    daily_cap: Optional[int] = None
    monthly_cap: Optional[int] = None
    included_type: Optional[str] = None
    language: Optional[str] = None
    region: Optional[str] = None
    min_rating: Optional[float] = None
    open_now: bool = False
    name_match: bool = False
    verify_location: bool = True
    verify_category: bool = True
    with_website_only: bool = False
    operational_only: bool = False
    json_out: Optional[str] = None
    quiet: bool = False
    verbose: bool = False
    pdf_all: bool = False

    @property
    def search_terms(self) -> str:
        return " ".join(part for part in [self.name, self.category] if part)

    def default_filename(self) -> str:
        seed = "_".join(p for p in [self.name, self.category, self.location] if p)
        slug = "_".join("".join(c if c.isalnum() else " " for c in seed.lower()).split())
        return f"{slug[:60] or 'places'}.csv"


def load_environment(env_file: str | None) -> tuple[Optional[str], set[str]]:
    """Load .env without overriding real environment variables.

    Returns (path, keys_that_came_from_the_file).
    """
    path = env_file or find_dotenv(usecwd=True) or None
    if path and not Path(path).exists():
        raise PlacesError(f"No .env file at {path}")
    if not path:
        return None, set()
    from_file = {k for k, v in dotenv_values(path).items() if v and not os.environ.get(k)}
    load_dotenv(path, override=False)
    return path, from_file


def env_default(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def apply_env_defaults(settings: Settings, from_file: set[str]) -> Settings:
    """Fill anything not passed on the command line from the environment/.env."""
    if settings.api_key:
        settings.api_key_source = "--api-key"
    else:
        settings.api_key = env_default(*ENV_KEYS) or ""
        if not settings.api_key:
            settings.api_key_source = ""
        elif from_file & set(ENV_KEYS):
            settings.api_key_source = short_path(settings.env_path) if settings.env_path else ".env"
        else:
            settings.api_key_source = "environment"

    settings.location = settings.location or env_default("PLACES_LOCATION") or ""
    settings.category = settings.category or env_default("PLACES_CATEGORY") or ""
    settings.name = settings.name or env_default("PLACES_NAME") or ""
    settings.included_type = settings.included_type or env_default("PLACES_TYPE")
    settings.language = settings.language or env_default("PLACES_LANGUAGE")
    settings.region = settings.region or env_default("PLACES_REGION")
    if settings.radius is None and (raw := env_default("PLACES_RADIUS")):
        try:
            settings.radius = float(raw)
        except ValueError:
            pass
    if settings.grid == 1 and (raw := env_default("PLACES_GRID")):
        try:
            settings.grid = int(raw)
        except ValueError:
            pass
    return settings


def collect_inputs(settings: Settings) -> Settings:
    """Prompt for whatever is still missing (name stays optional)."""
    missing = [f for f in ("location", "output") if not getattr(settings, f)]
    if not settings.name and not settings.category:
        missing.append("name or category")
    if not missing:
        return settings

    if not sys.stdin.isatty() or settings.quiet:
        raise PlacesError(
            f"missing required input(s): {', '.join(missing)}. Use --location, --output "
            "and at least one of --name / --category (see --help)."
        )

    console.print("  Tell me what to look up — press Enter to skip or accept a default.\n",
                  style="muted")
    if not settings.location:
        settings.location = ask("Location", required=True)
    if not settings.name and not settings.category:
        settings.name = ask("Business name")
    if not settings.category:
        settings.category = ask("Category", required=not settings.name)
    if not settings.output:
        settings.output = ask("Output CSV", default=settings.default_filename())
    console.print()
    return settings
