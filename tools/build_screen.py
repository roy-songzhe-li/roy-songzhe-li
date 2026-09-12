"""Compose the terminal screen (pixel portrait + neofetch panel) as a still PNG."""
import os
import pathlib
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
PORTRAIT_PX = 424               # matches build_avatar output exactly, so the cells are never resampled
PANEL_COL = 60                  # column where the neofetch panel starts
CREAM = "\x1b[97m"
CELL_W, CELL_H = 8, 18          # gohufont-uni-14 advance plus gifos' line spacing
PROMPT = "roy@mbp$ "
GREEN = "\x1b[0m"

FIELDS = [
    ("Name", "Roy Li"),
    ("Site", "roy-li.dev"),
    ("Work", "Aetheron"),
    ("OS", "macOS"),
]
LANGUAGES = ["TypeScript, Python,", "JavaScript, Shell"]
SKILLS = ["AI Agents, MCP,", "Forward Deployed,", "Full Stack"]

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


def write_field(terminal, label, lines, row):
    """Write a multi-line field, hanging the continuations under the value."""
    terminal.gen_text(f"{CREAM}{label}:{GREEN} {lines[0]}", row, PANEL_COL, contin=True)
    for offset, line in enumerate(lines[1:], start=1):
        terminal.gen_text(line, row + offset, PANEL_COL + len(label) + 2, contin=True)
    return row + len(lines)


def main(avatar_path, swatch_path, out_path):
    # contin=True everywhere: gifos otherwise auto-scrolls the frame to close the gap
    # under the pasted portrait, which wipes the portrait off the screen.
    terminal = Terminal(WIDTH, HEIGHT, XPAD, YPAD)
    terminal.toggle_show_cursor(False)

    with Image.open(avatar_path) as art:
        terminal.paste_image(avatar_path, 1, 1, size_multiplier=PORTRAIT_PX / art.width)

    row = 1
    for label, value in FIELDS:
        terminal.gen_text(f"{CREAM}{label}:{GREEN} {value}", row, PANEL_COL, contin=True)
        row += 1

    row = write_field(terminal, "Languages", LANGUAGES, row)
    row = write_field(terminal, "Skills", SKILLS, row) + 1

    terminal.paste_image(build_swatch_bar(swatch_path), row, PANEL_COL)

    terminal.gen_text(f"{CREAM}{PROMPT}", terminal.num_rows, 1, contin=True)
    terminal.save_frame(out_path)
    draw_block_cursor(out_path, terminal.num_rows)


def draw_block_cursor(frame_path, row):
    """Draw the filled block cursor by hand.

    gifos' bundled bitmap font is latin-1 only, so it cannot render U+2588 itself.
    """
    with Image.open(frame_path) as frame:
        canvas = frame.copy()
    left = XPAD + len(PROMPT) * CELL_W
    top = YPAD + (row - 1) * CELL_H
    ImageDraw.Draw(canvas).rectangle((left, top, left + CELL_W - 1, top + CELL_H - 4), "#ebf1dd")
    canvas.save(frame_path)


if __name__ == "__main__":
    main(*ARGS)
