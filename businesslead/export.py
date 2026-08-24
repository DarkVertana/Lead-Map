"""Writing and re-writing results: csv, xlsx, pdf, json.

Converting between them never touches the API — the rows come off disk.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import pandas as pd

from .constants import APP_TITLE, FILE_FORMATS, OUTPUT_DIR_NAME
from .errors import PlacesError
from .paths import env
from .ui.report import short_path

if TYPE_CHECKING:                       # only for the annotation below
    from .config import Settings


# How much page width each column deserves, relative to the others. Anything
# not listed gets a middling share.
COLUMN_WEIGHTS = {
    "name": 3.4, "category": 1.5, "primary_type": 1.8, "all_types": 3.4,
    "phone": 1.7, "international_phone": 1.8, "website": 2.6,
    "street": 3.6, "area": 1.8, "city": 1.4, "district": 1.5, "state": 1.5,
    "state_code": 0.7, "postal_code": 1.0, "country": 1.1,
    "formatted_address": 4.2, "latitude": 1.1, "longitude": 1.1,
    "rating": 0.7, "reviews_count": 1.0, "price_level": 1.1, "price_range": 1.3,
    "business_status": 1.4, "opened": 1.0, "opening_hours": 4.6, "open_now": 0.9,
    "google_maps_url": 2.4, "reviews_url": 2.4, "directions_url": 2.4,
    "summary": 2.8, "place_id": 2.2, "search_query": 2.2, "searched_name": 1.5,
    "extracted_on": 1.2,
}
HEADINGS = {
    "primary_type": "Type", "all_types": "All types", "international_phone": "Intl phone",
    "formatted_address": "Full address", "reviews_count": "Reviews",
    "business_status": "Status", "opening_hours": "Hours", "open_now": "Open",
    "google_maps_url": "Maps URL", "reviews_url": "Reviews URL",
    "directions_url": "Directions URL", "place_id": "Place ID",
    "search_query": "Query", "searched_name": "Searched name", "state_code": "ST",
    "postal_code": "PIN", "price_level": "Price", "price_range": "Price range",
    "extracted_on": "Extracted",
}


# What a printed lead sheet is actually for: who they are, how to reach them,
# where they are, and how well regarded. The other columns are all still in the
# csv / xlsx / json — a PDF that carries 34 of them is 4pt type nobody reads.
PDF_COLUMNS = [
    "name", "primary_type", "phone", "website",
    "street", "area", "city", "state", "postal_code",
    "rating", "reviews_count", "business_status",
]


def pdf_columns(df: pd.DataFrame, everything: bool = False) -> list[str]:
    """The columns a PDF shows: the useful dozen, or all of them if asked."""
    if everything:
        return list(df.columns)
    chosen = [name for name in PDF_COLUMNS if name in df.columns]
    return chosen or list(df.columns)        # someone else's file: show it all


def _pdf_scale(columns: int) -> tuple[float, float]:
    """Font size and leading that let this many columns fit across the page."""
    if columns <= 8:
        return 7.5, 9.5
    if columns <= 14:
        return 6.0, 7.5
    if columns <= 22:
        return 5.0, 6.2
    return 4.2, 5.2


def write_pdf(df: pd.DataFrame, path: Path, title: str = "",
              columns: list[str] | None = None) -> None:
    """A landscape table of the columns that matter on paper.

    Values are wrapped, never truncated, and the type shrinks as columns are
    added — pass `columns=list(df.columns)` (or --pdf-all) for the whole
    spreadsheet, which lands at about 4pt on A3.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    columns = list(columns) if columns else pdf_columns(df)
    size, leading = _pdf_scale(len(columns))
    pagesize = landscape(A4 if len(columns) <= 12 else A3)
    margin = 8 * mm

    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=size,
                          leading=leading, alignment=TA_LEFT, spaceAfter=0,
                          wordWrap="CJK")          # break inside long URLs too
    head = ParagraphStyle("head", parent=cell, textColor=colors.white,
                          fontName="Helvetica-Bold")

    available = pagesize[0] - 2 * margin
    weights = [COLUMN_WEIGHTS.get(name, 1.6) for name in columns]
    widths = [available * weight / sum(weights) for weight in weights]

    def text(value) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "–"
        out = str(value).strip()
        return (out.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                or "–")

    rows = [[Paragraph(HEADINGS.get(name, name.replace("_", " ").title()), head)
             for name in columns]]
    for _, row in df.iterrows():
        rows.append([Paragraph(text(row.get(name)), cell) for name in columns])

    document = SimpleDocTemplate(
        str(path), pagesize=pagesize, leftMargin=margin, rightMargin=margin,
        topMargin=margin, bottomMargin=margin,
        title=title or path.stem, author=APP_TITLE)

    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e08c48")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#faf6f2")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9d2cc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))

    note = (f" · showing {len(columns)} of {len(df.columns)} columns, "
            f"all of them are in the csv / xlsx / json"
            if len(columns) < len(df.columns) else "")
    heading = Paragraph(
        f"<b>{title or path.stem}</b> — {len(df)} businesses{note}",
        ParagraphStyle("title", parent=styles["Title"], fontSize=11, spaceAfter=2))
    document.build([heading, Spacer(1, 3 * mm), table])


FORMATS = FILE_FORMATS          # name → extension, from constants.py
READABLE = (".csv", ".xlsx", ".xls", ".json")


def output_root() -> Path:
    """Where bare filenames land. BUSINESSLEAD_OUTPUT_DIR moves it."""
    return Path(env("OUTPUT_DIR", OUTPUT_DIR_NAME)).expanduser()


def output_path_for(settings: "Settings", today: dt.date | None = None) -> Path:
    """Where a run will write.

    A bare name is filed straight into the output folder — one file per search,
    named after it, added to every time that search is run again. A name with a
    directory in it — leads.csv in a folder, ~/Desktop/leads.pdf, /tmp/x.json —
    is left exactly where you put it.

    `today` is accepted and ignored: results used to be filed under a folder per
    day, which split one search's findings across as many folders as the days
    you happened to run it on. Callers still pass it.
    """
    path = Path(settings.output).expanduser()
    if not path.name:                    # asked before the filename question
        path = Path(settings.default_filename())
    if not path.suffix:
        path = path.with_suffix(".csv")
    if path.suffix.lower() == ".xls":    # pandas dropped the ancient .xls writer
        path = path.with_suffix(".xlsx")
    if path.parent == Path("."):
        path = output_root() / path.name
    return path


def unique_path(path: Path) -> Path:
    """The same name until it would overwrite: leads.csv → leads-2.csv → …

    A results file is a delivery, so nothing may replace one. Searches that can
    be added to are added to instead — see `fold_into_existing`; this is for the
    ones that can't, a PDF or a file that won't read back.
    """
    if not path.exists():
        return path
    for counter in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}-{dt.datetime.now():%H%M%S}{path.suffix}")


def read_dataframe(path: Path) -> pd.DataFrame:
    """Read a results file back — the CSV keeps its BOM, so say so.

    The CSV is read as text and only the truly numeric columns are converted
    back: type inference would strip the leading zero off a postal code and
    turn a phone number into a float, and those corrupted values would then be
    what --convert hands to a client.
    """
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        try:
            return pd.read_excel(path)
        except ImportError as exc:
            raise PlacesError(f"reading {suffix} needs an extra package ({exc}) — "
                              "save it as .xlsx or .csv instead") from exc
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".csv":
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        for column in ("latitude", "longitude", "rating", "reviews_count"):
            if column in df.columns:
                try:
                    df[column] = pd.to_numeric(df[column].where(df[column] != ""))
                except (TypeError, ValueError):
                    pass                       # someone else's file: leave it text
        return df
    raise PlacesError(f"I can read .csv, .xlsx and .json — not {suffix or 'a file with no extension'}")


def fold_into_existing(df: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, Path, int]:
    """Add this run's rows to the file that search already has.

    One search, one file: run the same location and category again next week and
    what it finds joins what is there, each row dated by `extracted_on`. Returns
    what to write, where to write it, and how many rows were already in the file.

    Rows already on disk keep their order and their dates — a sheet someone is
    working down must not reshuffle under them — and this run's go underneath. A
    place in both stays as the older row: that is when it was really delivered.

    No failure here may cost a file. If what's on disk can't be read back — a
    PDF, someone else's spreadsheet, one a crash left half written — it is left
    exactly as it is and this run goes to a name of its own instead.
    """
    if not path.exists():
        return df, path, 0
    if path.suffix.lower() not in READABLE:
        return df, unique_path(path), 0
    try:
        existing = read_dataframe(path)
    except (PlacesError, OSError, ValueError):
        return df, unique_path(path), 0
    if existing.empty:
        return df, path, 0

    # Column-name union, so a sheet someone added a column of their own to keeps
    # it, and an older file written before `extracted_on` existed simply leaves
    # that cell empty for its rows rather than claiming a date it never had.
    combined = pd.concat([existing, df], ignore_index=True)
    if "place_id" in combined.columns:
        ids = combined["place_id"].astype(str).str.strip()
        combined = combined[~(ids.duplicated() & (ids != ""))]
    return combined.reset_index(drop=True), path, len(existing)


def convert_file(source: Path, formats: Iterable[str], title: str = "",
                 pdf_all: bool = False) -> list[Path]:
    """Rewrite a results file in other formats. Touches no API and no quota."""
    source = Path(source).expanduser()
    if not source.exists():
        raise PlacesError(f"no such file: {short_path(source)}")
    df = read_dataframe(source)

    written: list[Path] = []
    for name in formats:
        suffix = FORMATS.get(name.strip().lower().lstrip("."))
        if not suffix:
            raise PlacesError(f"I can't write {name!r} — try csv, excel, pdf or json")
        target = source.with_suffix(suffix)
        if target == source:
            continue                       # already have this one
        try:
            write_dataframe(df, target, title or source.stem.replace("_", " "),
                            pdf_all=pdf_all)
        except OSError as exc:
            raise PlacesError(f"couldn't write {short_path(target)} — is it open "
                              f"in another program? ({exc})") from exc
        written.append(target)
    return written


def _write_one(df: pd.DataFrame, path: Path, suffix: str, title: str,
               pdf_all: bool) -> str:
    if suffix == ".xlsx":
        df.to_excel(path, index=False, sheet_name="businesses")
        return "xlsx"
    if suffix == ".pdf":
        write_pdf(df, path, title, columns=pdf_columns(df, everything=pdf_all))
        return "pdf"
    if suffix == ".json":
        df.to_json(path, orient="records", indent=2, force_ascii=False)
        return "json"
    df.to_csv(path, index=False, encoding="utf-8-sig")   # BOM so Excel opens it cleanly
    return "csv"


def write_dataframe(df: pd.DataFrame, path: Path, title: str = "",
                    pdf_all: bool = False) -> str:
    """Write CSV, Excel, PDF or JSON based on the file extension.

    csv, xlsx and json always carry every column. Only the PDF is a selection,
    and only because a page has edges — `pdf_all` overrides that.

    The file is built beside its destination and moved onto it, never written
    over in place. A results file now holds every run of that search rather than
    only the last, so a writer that dies half way — a full disk, a killed
    process — must leave the previous one whole instead of truncated.
    """
    suffix = path.suffix.lower()
    if suffix == ".xls":               # pandas has no .xls writer any more
        path, suffix = path.with_suffix(".xlsx"), ".xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Beside the target, so the move onto it is a rename within one filesystem,
    # and hidden + pid-tagged so a stray one is obvious and two runs can't pick
    # the same scratch name.
    temporary = path.with_name(f".{path.stem}.writing-{os.getpid()}{path.suffix}")
    try:
        fmt = _write_one(df, temporary, suffix, title, pdf_all)
        temporary.replace(path)        # Windows: raises if the file is open in Excel
        return fmt
    finally:
        try:
            temporary.unlink()         # only still here if something above failed
        except OSError:
            pass
