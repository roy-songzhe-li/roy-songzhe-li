"""Redraw a GitHub avatar the way a terminal would: as character-cell block art.

The reference screenshot is not a dithered bitmap. Zoomed in, the portrait is a
coarse grid of wide, short terminal character cells, each filled with a single
uniform shade texture - the ASCII shade characters. The mosaic quality comes
from that blockiness, so this renders cells rather than dithering pixels.

Measured from the reference: 20.4px vertical pitch (20/20/21/20/21/20...), 8px
horizontal pitch, about 53x24 cells over the portrait's ~427x477px area.
"""
import sys
from PIL import Image, ImageDraw, ImageOps

COLS, ROWS = 53, 24
CELL_W, CELL_H = 8, 20          # the terminal's font advance and line pitch
DOT = 2                         # shade-pattern dot size inside a cell

# Three phosphor anchors sampled from the reference: outline, backdrop, subject.
DARK, MID, LIGHT = (62, 116, 50), (126, 192, 96), (232, 243, 214)

BG_TOLERANCE = 32               # flood-fill tolerance for the avatar's flat backdrop
TONE_OUTLINE, TONE_MIDTONE, TONE_SUBJECT, TONE_BACKDROP = 10, 96, 250, 150
SHADOW_CUTOFF, MIDTONE_CUTOFF = 70, 150


def backdrop_mask(image):
    """Mask of the avatar's flat backdrop, flood-filled inward from the four corners.

    A plain colour-distance test would also swallow the skin tones, which sit close
    to this avatar's tan background, so the fill is seeded from the corners instead.
    """
    sentinel = (1, 2, 3)
    probe = image.copy()
    width, height = probe.size
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        ImageDraw.floodfill(probe, corner, sentinel, thresh=BG_TOLERANCE)
    return Image.eval(
        Image.merge("RGB", [
            channel.point(lambda v, base=sentinel[i]: 255 if v == base else 0)
            for i, channel in enumerate(probe.split())
        ]).convert("L"),
        lambda v: 255 if v > 250 else 0,
    )


def remap_tones(grey):
    """Flatten the avatar's tones onto deliberate phosphor levels."""
    return grey.point([
        TONE_OUTLINE if v < SHADOW_CUTOFF else TONE_MIDTONE if v < MIDTONE_CUTOFF else TONE_SUBJECT
        for v in range(256)
    ])


def shade_for(tone):
    """Pick the (background, foreground, density) a cell of this tone is drawn with.

    Two segments - dark-to-backdrop, then backdrop-to-subject - each stepped in
    quarters, which is what the four ASCII shade characters give you.
    """
    level = round(tone / 255 * 8)
    if level <= 4:
        return DARK, MID, level / 4
    else:
        return MID, LIGHT, (level - 4) / 4


def draw_block(draw, left, top, height, tone):
    """Fill one block with a single uniform shade texture.

    Every dot row carries the same number of dots and only its phase rotates, the
    way the ASCII shade characters are drawn. That matters: a 2D dither leaves
    some rows empty, which makes the block ripple vertically and drowns out the
    inter-row baseline. In the reference a backdrop block averages dead flat
    horizontally, with the row line as the only vertical structure.
    """
    background, foreground, density = shade_for(tone)
    draw.rectangle((left, top, left + CELL_W - 1, top + height - 1), background)
    columns = CELL_W // DOT
    per_row = round(density * columns)
    if per_row:
        for row in range(top // DOT, (top + height) // DOT):
            for column in range(columns):
                if (column + row * 2) % columns < per_row:
                    x, y = left + column * DOT, row * DOT
                    draw.rectangle((x, y, x + DOT - 1, y + DOT - 1), foreground)


def draw_cell(draw, left, top, upper_tone, lower_tone):
    """Draw one character cell, splitting it into half blocks when the halves differ.

    This is the half-block trick every terminal image renderer uses: it keeps the
    character-cell blockiness while recovering the vertical detail that 24 rows
    alone would throw away.
    """
    half = CELL_H // 2
    if shade_for(upper_tone) == shade_for(lower_tone):
        draw_block(draw, left, top, CELL_H, upper_tone)
    else:
        draw_block(draw, left, top, half, upper_tone)
        draw_block(draw, left, top + half, CELL_H - half, lower_tone)


def main(source, target):
    avatar = Image.open(source).convert("RGB")
    tones = remap_tones(ImageOps.grayscale(avatar))
    tones.paste(Image.new("L", avatar.size, TONE_BACKDROP), (0, 0), backdrop_mask(avatar))
    cells = tones.resize((COLS, ROWS * 2), Image.Resampling.BOX)  # two samples per cell

    art = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H))
    draw = ImageDraw.Draw(art)
    for row in range(ROWS):
        for col in range(COLS):
            draw_cell(draw, col * CELL_W, row * CELL_H,
                      cells.getpixel((col, row * 2)), cells.getpixel((col, row * 2 + 1)))

    # The inter-row baseline is drawn in build_crt after the bloom, so the
    # glow cannot smear it into a soft undulation.
    art.save(target)
    print(f"wrote {target} {art.size}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
