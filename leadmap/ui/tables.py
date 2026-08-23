"""The results preview and the closing summary panel."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.box import ROUNDED, SIMPLE_HEAD
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .report import progress_bar, short_path


def filled(df: pd.DataFrame, column: str) -> int:
    """How many rows actually have this field.

    Counting `!= ""` is wrong for a file read back off disk, where blanks come
    back as NaN and every one of them counts as present.
    """
    if column not in df:
        return 0
    # fillna before astype: pandas' string dtype propagates NA through .lower()
    # and the comparison then counts the missing values as present.
    values = df[column].fillna("").astype(str).str.strip().str.lower()
    return int((~values.isin(("", "nan", "none", "<na>"))).sum())


def cell(value) -> str:
    """Blank, missing and NaN all read the same on screen: a dash."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "–"
    return str(value).strip() or "–"


def results_table(df: pd.DataFrame, limit: int = 5) -> Table:
    """Preview table. Uses literal styles rather than theme names, so it renders
    the same on any console, themed or not."""
    table = Table(box=SIMPLE_HEAD, header_style="grey58", expand=False,
                  padding=(0, 1), border_style="grey58", pad_edge=False)
    table.add_column("Business", style="bold", overflow="ellipsis", max_width=26)
    table.add_column("Phone")
    table.add_column("Street", overflow="ellipsis", max_width=28, style="grey58")
    table.add_column("Area", overflow="ellipsis", max_width=16)
    table.add_column("City", overflow="ellipsis", max_width=14)
    table.add_column("★", justify="right")
    table.add_column("Reviews", justify="right")
    for _, row in df.head(limit).iterrows():
        rating = (Text(f"{row['rating']:.1f}", style="bold")
                  if pd.notna(row.get("rating")) else Text("–", style="grey58"))
        reviews = (f"{int(row['reviews_count']):,}"
                   if pd.notna(row.get("reviews_count")) else "–")
        table.add_row(cell(row.get("name")), cell(row.get("phone")),
                      cell(row.get("street")), cell(row.get("area")),
                      cell(row.get("city")), rating, reviews)
    return table


def summary_panel(df: pd.DataFrame, path: Path, fmt: str, elapsed: float,
                  extra: list[tuple[str, str]] | None = None) -> Panel:
    stats = Table.grid(padding=(0, 2))
    stats.add_column(style="muted", min_width=12)
    stats.add_column()
    rated = pd.to_numeric(df.get("rating"), errors="coerce").dropna()
    with_phone = filled(df, "phone")
    with_site = filled(df, "website")
    stats.add_row("businesses", Text(f"{len(df)}", style="value"))
    with_address = filled(df, "street")
    stats.add_row("with phone", f"{with_phone}/{len(df)}  {progress_bar(with_phone, len(df), 10)}")
    stats.add_row("with street", f"{with_address}/{len(df)}  {progress_bar(with_address, len(df), 10)}")
    stats.add_row("with website", f"{with_site}/{len(df)}  {progress_bar(with_site, len(df), 10)}")
    stats.add_row("avg rating", f"{rated.mean():.2f} ★" if len(rated) else "n/a")
    stats.add_row("elapsed", f"{elapsed:.1f}s")
    for label, value in extra or []:
        stats.add_row(label, value)

    head = Text()
    head.append("✓ ", style="ok")
    head.append("Done", style="bold")
    head.append(f"  ·  {len(df)} businesses saved", style="muted")

    saved = Text(no_wrap=True, overflow="ellipsis")
    saved.append(f"{fmt.upper()}  ", style="ok")
    saved.append(short_path(path), style="path")
    return Panel(Group(head, "", stats, "", saved), box=ROUNDED,
                 border_style="ok", expand=False, padding=(0, 1),
                 title=Text("summary", style="muted"), title_align="left")
