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
PORTRAIT_PX = 444               # on-screen size of the pixel portrait
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
    ("Editor", "Neovim"),
]
LANGUAGES = ["TypeScript, Python,", "Java, Lua, Bash"]
SKILLS = ["Full Stack, AI Agents,", "Cloud Native"]

# GitHub's own language colours; the CRT pass tints them toward phosphor green.
SWATCH_COLORS = ["#3178c6", "#3572a5", "#b07219", "#000080", "#89e051", "#f1e05a", "#ff3e00", "#dea584"]
SWATCH_BLOCK, SWATCH_HEIGHT = 26, 30


def build_swatch_bar(target):
    bar = Image.new("RGB", (SWATCH_BLOCK * len(SWATCH_COLORS), SWATCH_HEIGHT), "#13250f")
    draw = ImageDraw.Draw(bar)
    for index, colour in enumerate(SWATCH_COLORS):
        draw.rectangle((index * SWATCH_BLOCK, 0, (index + 1) * SWATCH_BLOCK - 1, SWATCH_HEIGHT), colour)
    bar.save(target)
    return target


def main(avatar_path, swatch_path, out_path):
    # contin=True everywhere: gifos otherwise auto-scrolls the frame to close the gap
    # under the pasted portrait, which wipes the portrait off the screen.
    terminal = Terminal(WIDTH, HEIGHT, XPAD, YPAD)
    terminal.toggle_show_cursor(False)

    with Image.open(avatar_path) as art:
        terminal.paste_image(avatar_path, 1, 1, size_multiplier=PORTRAIT_PX / art.width)

    row = 2
    for label, value in FIELDS:
        terminal.gen_text(f"{CREAM}{label}:{GREEN} {value}", row, PANEL_COL, contin=True)
        row += 1

    terminal.gen_text(f"{CREAM}Languages:{GREEN} {LANGUAGES[0]}", row, PANEL_COL, contin=True)
    terminal.gen_text(LANGUAGES[1], row + 1, PANEL_COL + 11, contin=True)
    row += 2
    terminal.gen_text(f"{CREAM}Skills:{GREEN} {SKILLS[0]}", row, PANEL_COL, contin=True)
    terminal.gen_text(SKILLS[1], row + 1, PANEL_COL + 8, contin=True)
    row += 3

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
