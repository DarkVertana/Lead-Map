"""
The opening screen: a boxed welcome line over the tool's name in block letters.

Everything here is drawn from a 5×5 pixel font defined below — one dict of
glyphs, scaled to two terminal cells per pixel and given a one-cell drop shadow,
so the name reads as chunky 3D type. It wraps by word to the terminal width
(BUSINESS / LEAD stacks on a narrow terminal, BUSINESS LEAD sits on one line on
a wide one), halves the pixel width when even one word won't fit, and falls back
to plain text on anything too narrow to draw at all.
"""

from __future__ import annotations

from pathlib import Path

from rich.box import ROUNDED
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from ..constants import APP_TAGLINE, APP_TITLE, VERSION
from .report import elide, short_path
from .theme import console

BLOCK = "█"
PIXEL_WIDTH = 2         # terminal cells per pixel — keeps the letters square-ish
LETTER_GAP = 1          # blank pixel columns between letters
WORD_GAP = 3            # blank pixel columns between words on the same line
MARGIN = 1              # left indent, in cells

MAIN, SHADOW = 1, 2

# A 5×5 font. '#' is an inked pixel; anything else is blank.
GLYPHS: dict[str, list[str]] = {
    "A": [".###.", "#...#", "#####", "#...#", "#...#"],
    "B": ["####.", "#...#", "####.", "#...#", "####."],
    "C": [".####", "#....", "#....", "#....", ".####"],
    "D": ["####.", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "####.", "#....", "#####"],
    "F": ["#####", "#....", "####.", "#....", "#...."],
    "G": [".####", "#....", "#..##", "#...#", ".###."],
    "H": ["#...#", "#...#", "#####", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "#####"],
    "J": ["....#", "....#", "....#", "#...#", ".###."],
    "K": ["#...#", "#..#.", "###..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "####.", "#....", "#...."],
    "Q": [".###.", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "####.", "#..#.", "#...#"],
    "S": [".####", "#....", ".###.", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
    "Y": ["#...#", ".#.#.", "..#..", "..#..", "..#.."],
    "Z": ["#####", "...#.", "..#..", ".#...", "#####"],
    "0": [".###.", "#..##", "#.#.#", "##..#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "..##.", ".#...", "#####"],
    "3": ["####.", "....#", ".###.", "....#", "####."],
    "4": ["#..#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "####."],
    "6": [".###.", "#....", "####.", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", "..#.."],
    "8": [".###.", "#...#", ".###.", "#...#", ".###."],
    "9": [".###.", "#...#", ".####", "....#", ".###."],
    "-": [".....", ".....", ".###.", ".....", "....."],
    "+": [".....", "..#..", ".###.", "..#..", "....."],
    ".": [".....", ".....", ".....", ".....", "..#.."],
    "!": ["..#..", "..#..", "..#..", ".....", "..#.."],
    "?": [".###.", "#...#", "..##.", ".....", "..#.."],
    "&": [".##..", "#..#.", ".##..", "#..#.", ".##.#"],
}
GLYPH_HEIGHT = 5


# ---------------------------------------------------------------------------
# Text → pixels
# ---------------------------------------------------------------------------

def split_words(title: str) -> list[str]:
    """'BusinessLead v2' → ['BUSINESS', 'LEAD', 'V2'] — camel case counts as a break."""
    words: list[str] = []
    for chunk in title.replace("-", " ").replace("_", " ").split():
        current = ""
        for index, char in enumerate(chunk):
            starts_word = (index and char.isupper()
                           and (chunk[index - 1].islower() or chunk[index - 1].isdigit()))
            if starts_word and current:
                words.append(current.upper())
                current = ""
            current += char
        if current:
            words.append(current.upper())
    return [w for w in words if any(c.upper() in GLYPHS for c in w)]


def _bitmap(word: str) -> list[list[bool]]:
    """One word as rows of on/off pixels."""
    rows: list[list[bool]] = [[] for _ in range(GLYPH_HEIGHT)]
    for index, char in enumerate(word):
        glyph = GLYPHS.get(char.upper())
        if glyph is None:
            continue
        if index:
            for row in rows:
                row.extend([False] * LETTER_GAP)
        for row, line in zip(rows, glyph):
            row.extend(pixel == "#" for pixel in line)
    return rows


def _join(bitmaps: list[list[list[bool]]]) -> list[list[bool]]:
    """Lay several words side by side on one line."""
    rows: list[list[bool]] = [[] for _ in range(GLYPH_HEIGHT)]
    for index, bitmap in enumerate(bitmaps):
        for row, part in zip(rows, bitmap):
            if index:
                row.extend([False] * WORD_GAP)
            row.extend(part)
    return rows


def cell_width(bitmap: list[list[bool]], pixel: int = PIXEL_WIDTH) -> int:
    """How many terminal columns the drawn bitmap needs, shadow included."""
    return len(bitmap[0]) * pixel + 1 if bitmap and bitmap[0] else 0


# ---------------------------------------------------------------------------
# Pixels → terminal cells
# ---------------------------------------------------------------------------

def _grid(bitmap: list[list[bool]], pixel: int = PIXEL_WIDTH) -> list[list[int]]:
    """Cells of MAIN, over a dark ground shadow nudged down and right.

    The shadow is cast only by the baseline row. Casting it from every pixel
    (a true 3D offset) fills the one-pixel counters and notches inside the
    letters at this size, and the name stops being readable.
    """
    height, width = len(bitmap) + 1, cell_width(bitmap, pixel)
    grid = [[0] * width for _ in range(height)]
    for x, inked in enumerate(bitmap[-1]):
        if inked:
            for cell in range(pixel):
                grid[-1][x * pixel + 1 + cell] = SHADOW
    for y, row in enumerate(bitmap):
        for x, inked in enumerate(row):
            if inked:
                for cell in range(pixel):
                    grid[y][x * pixel + cell] = MAIN
    return grid


def _lines(bitmap: list[list[bool]], main: str, shadow: str,
           pixel: int = PIXEL_WIDTH) -> list[Text]:
    out: list[Text] = []
    for row in _grid(bitmap, pixel):
        line = Text(" " * MARGIN)
        run, style = 0, 0
        for cell in row + [0]:                             # sentinel flushes the tail
            if cell == style:
                run += 1
                continue
            if run:
                line.append((BLOCK if style else " ") * run,
                            style=main if style == MAIN else shadow if style else None)
            run, style = 1, cell
        out.append(line)
    return out


def big_text(title: str, width: int, *, main: str = "brand",
             shadow: str = "shadow") -> list[Text]:
    """The title in block letters, wrapped by word to `width` columns."""
    words = split_words(title)
    if not words:
        return []
    bitmaps = [_bitmap(word) for word in words]
    # The longest word decides the scale. Two cells per pixel is the design, but
    # a word as long as BUSINESS needs 96 columns at that size — wider than the
    # 80 a terminal is assumed to have. Half-width pixels still read as block
    # letters, and reading narrow beats not drawing the name at all.
    pixel = next((p for p in range(PIXEL_WIDTH, 0, -1)
                  if max(cell_width(b, p) for b in bitmaps) + MARGIN <= width), 0)
    if not pixel:
        return []                                          # too narrow to draw

    lines: list[Text] = []
    row: list[list[list[bool]]] = []
    for bitmap in bitmaps:
        candidate = row + [bitmap]
        if row and cell_width(_join(candidate), pixel) + MARGIN > width:
            lines.extend(_lines(_join(row), main, shadow, pixel))
            row = [bitmap]
        else:
            row = candidate
    if row:
        lines.extend(_lines(_join(row), main, shadow, pixel))
    return lines


# ---------------------------------------------------------------------------
# The opening
# ---------------------------------------------------------------------------

def welcome_panel(title: str, version: str) -> Panel:
    body = Text()
    body.append("✻ ", style="brand")
    body.append(f"Welcome to {title}", style="bold")
    if version:
        body.append(f"  v{version}", style="muted")
    return Panel(body, box=ROUNDED, border_style="brand", expand=False, padding=(0, 1))


def opening(title: str, version: str, lines: list[str], width: int) -> RenderableType:
    """Boxed welcome, the name in block letters, then the muted detail lines."""
    parts: list[RenderableType] = [welcome_panel(title, version)]
    art = big_text(title, width, main="brand", shadow="shadow")
    if art:
        parts.append("")
        parts.extend(art)
    parts.append("")
    for line in lines:
        parts.append(Text(f"  {line}", style="muted"))
    return Group(*parts)


def banner() -> RenderableType:
    """The opening screen: boxed welcome, the name in block letters, the cwd."""
    return opening(
        APP_TITLE, VERSION,
        [APP_TAGLINE, f"cwd: {elide(short_path(Path.cwd()))}"],
        console.width)
