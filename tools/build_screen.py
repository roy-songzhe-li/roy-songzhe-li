"""Compose the terminal screen (pixel portrait + neofetch panel) as a still PNG."""
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent.resolve()
ARGS = [str(pathlib.Path(arg).resolve()) for arg in sys.argv[1:4]]  # resolve before the chdir below

# gifos reads its theme from $HOME/.config/gifos and writes scratch frames relative to the
# working directory, so point both at this repo rather than the real home directory.
os.environ["HOME"] = str(HERE / "gifos-home")
os.chdir(HERE)
(HERE / "build" / "frames").mkdir(parents=True, exist_ok=True)  # gifos creates this at import time

from PIL import Image, ImageDraw  # noqa: E402
from gifos import Terminal  # noqa: E402

WIDTH, HEIGHT, XPAD, YPAD = 800, 541, 22, 14
PORTRAIT_PX = 416               # matches build_avatar output exactly, so the cells are never resampled
PANEL_COL = 53                  # column where the neofetch panel starts, at the reference's x=490
# The reference draws labels and values in two greens, not white-on-green - the
# cream labels this had before were invented and washed the whole panel out.
LABEL, VALUE = "\x1b[0m", "\x1b[92m"
CREAM = "\x1b[97m"

# Pixel Operator Mono (CC0). At 18 its advance and its bounding box are both exactly
# 9px, which is the reference's advance and also means the glyphs sit on the column
# grid with no correction. 15px tall, so 5px of line spacing lands the 20px pitch.
FONT_FILE = str(HERE / "fonts" / "PixelOperatorMono.ttf")
FONT_SIZE, LINE_SPACING = 18, 5
CELL_W, CELL_H = 9, 20
PROMPT = "roy@mbp$ "
GREEN = "\x1b[0m"

FIELDS = [
    ("Name", "Roy Li"),
    ("Site", "roy-li.dev"),
    ("Work", "Aetheron"),
    ("OS", "macOS"),
]
LANGUAGES = ["TypeScript, Python,", "JavaScript, Shell"]
SKILLS = ["AI Agents, Full Stack,", "Forward Deployed Engineering"]

# Neofetch's ANSI normal/bright order, calibrated for the reference phosphor response.
SWATCH_COLORS = [
    ["#1b4514", "#bc7d1b", "#07fe42", "#e8f354", "#1be172", "#c77b74", "#00f96c", "#93f273"],
    ["#46a439", "#cac61e", "#bcf769", "#edf744", "#a1f99a", "#d8f28d", "#eef18b", "#ecf5b2"],
]
SWATCH_BLOCK, SWATCH_ROW_HEIGHT, SWATCH_TOP_PAD = 28, 21, 7


def build_swatch_bar(target):
    bar = Image.new(
        "RGB", (SWATCH_BLOCK * len(SWATCH_COLORS[0]), SWATCH_ROW_HEIGHT * 2 + SWATCH_TOP_PAD), "#13250f"
    )
    draw = ImageDraw.Draw(bar)
    for row, colours in enumerate(SWATCH_COLORS):
        for index, colour in enumerate(colours):
            draw.rectangle(
                (index * SWATCH_BLOCK, SWATCH_TOP_PAD + row * SWATCH_ROW_HEIGHT,
                 (index + 1) * SWATCH_BLOCK - 1,
                 SWATCH_TOP_PAD + (row + 1) * SWATCH_ROW_HEIGHT - 1),
                colour,
            )
    bar.save(target)
    return target


def build_terminal():
    """Build the terminal, correcting gifos' idea of a column's width.

    Pixel Operator Mono measures 9px either way at this size, so this only pins the
    value rather than correcting it - but it keeps the layout honest if the font moves.
    """
    terminal = Terminal(WIDTH, HEIGHT, XPAD, YPAD, FONT_FILE, FONT_SIZE, LINE_SPACING)
    terminal._Terminal__font_width = CELL_W
    terminal.num_cols = (WIDTH - 2 * XPAD) // CELL_W
    return terminal


ANSI = re.compile(r"(\x1b\[\d+(?:;\d+)*m)")


def write_spaced(terminal, text, row, col):
    """Write one character per column so the advance is the column pitch.

    gifos hands a whole run to PIL in one call, which spaces it at the font's own
    advance. Stepping character by character is what lets a 16px face sit on the
    reference's 9px grid.
    """
    for chunk in (c for c in ANSI.split(text) if c):
        if ANSI.fullmatch(chunk):
            terminal.gen_text(chunk, row, col, contin=True)
        else:
            for character in chunk:
                if character != " ":
                    terminal.gen_text(character, row, col, contin=True)
                col += 1
    return col


def write_field(terminal, label, lines, row):
    """Write a multi-line field, hanging the continuations under the value.

    The hanging indent shrinks when a continuation would run past the right edge,
    which the longest skill needs now that the panel is set at the reference's
    wider character advance.
    """
    indent = len(label) + 2
    if len(lines) > 1:
        room = terminal.num_cols - PANEL_COL + 1 - max(len(line) for line in lines[1:])
        indent = max(0, min(indent, room))
    write_spaced(terminal, f"{LABEL}{label}:{VALUE} {lines[0]}", row, PANEL_COL)
    for offset, line in enumerate(lines[1:], start=1):
        write_spaced(terminal, f"{VALUE}{line}", row + offset, PANEL_COL + indent)
    return row + len(lines)


def main(avatar_path, swatch_path, out_path):
    # contin=True everywhere: gifos otherwise auto-scrolls the frame to close the gap
    # under the pasted portrait, which wipes the portrait off the screen.
    terminal = build_terminal()
    terminal.toggle_show_cursor(False)

    with Image.open(avatar_path) as art:
        terminal.paste_image(avatar_path, 1, 1, size_multiplier=PORTRAIT_PX / art.width)

    row = 1
    for label, value in FIELDS:
        write_spaced(terminal, f"{LABEL}{label}:{VALUE} {value}", row, PANEL_COL)
        row += 1

    row = write_field(terminal, "Languages", LANGUAGES, row)
    row = write_field(terminal, "Skills", SKILLS, row) + 1

    terminal.paste_image(build_swatch_bar(swatch_path), row, PANEL_COL)

    write_spaced(terminal, f"{CREAM}{PROMPT}", terminal.num_rows, 1)
    terminal.save_frame(out_path)
    draw_block_cursor(out_path, terminal.num_rows)


def draw_block_cursor(frame_path, row):
    """Draw the filled block cursor by hand, since the font has no U+2588."""
    with Image.open(frame_path) as frame:
        canvas = frame.copy()
    left = XPAD + len(PROMPT) * CELL_W
    top = YPAD + (row - 1) * CELL_H
    ImageDraw.Draw(canvas).rectangle((left, top, left + CELL_W - 1, top + CELL_H - 4), "#ebf1dd")
    canvas.save(frame_path)


if __name__ == "__main__":
    main(*ARGS)
