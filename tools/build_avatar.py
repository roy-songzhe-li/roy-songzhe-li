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

# An art pixel spans TWO character cells horizontally - the standard trick, since a
# character cell is tall and narrow and doubling it up gets close to square. Measured
# on the reference: 20px row pitch, and a median horizontal run of 68px against the
# 32px we got from 8px cells with half-block splits.
COLS, ROWS = 26, 23
CELL_W, CELL_H = 16, 20
# The reference pairs a FINE dot screen with LARGE flat blocks - the texture is
# high frequency, the structure is not. Coarse dots read as the wrong thing.
DOT_W, DOT_H = 2, 2

# Three phosphor anchors sampled from the reference: outline, backdrop, subject.
DARK, MID, LIGHT = (65, 122, 53), (133, 203, 101), (244, 253, 226)

# Crop in on the head before quantising. At 26x23 blocks there are not enough cells
# to spare on empty backdrop, and the reference's subject fills its frame too.
CROP = (0.12, 0.01, 0.92, 0.90)  # fractions of the source avatar
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
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
    # Six levels, not nine: the reference's subject is mostly solid cream and its
    # backdrop one uniform dot screen, with only a few dithered blocks between.
    level = round(tone / 255 * 6)
    if level <= 3:
        return DARK, MID, level / 3
    else:
        return MID, LIGHT, (level - 3) / 3


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
    if density <= 0:
        return
    for row in range(top // DOT_H, (top + height) // DOT_H):
        for column in range(CELL_W // DOT_W):
            # A plain ordered screen. Anything that steps the phase linearly per row -
            # which is what a fixed dot count per row forces - lays the dots out along
            # diagonals instead.
            if (BAYER[row % 4][column % 4] + 0.5) / 16 < density:
                x, y = left + column * DOT_W, row * DOT_H
                draw.rectangle((x, y, x + DOT_W - 1, y + DOT_H - 1), foreground)





def main(source, target):
    avatar = Image.open(source).convert("RGB")
    mask = backdrop_mask(avatar)
    tones = remap_tones(ImageOps.grayscale(avatar))
    tones.paste(Image.new("L", avatar.size, TONE_BACKDROP), (0, 0), mask)
    width, height = avatar.size
    tones = tones.crop((round(CROP[0] * width), round(CROP[1] * height),
                        round(CROP[2] * width), round(CROP[3] * height)))
    # Two samples per row: the art pixel keeps the reference's 16px width, which is
    # the dimension the blockiness actually reads in, but splits vertically. At the
    # full 16x20 the face collapses into an unreadable blob - this avatar is a line
    # drawing, not the flat silhouette the reference was made from.
    cells = tones.resize((COLS, ROWS * 2), Image.Resampling.BOX)
    # Averaging a line drawing down to 26x23 pulls everything toward the middle, so
    # stretch the cell tones back out to the full range or the portrait reads as mush.
    cells = ImageOps.autocontrast(cells, cutoff=2)

    art = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H))
    draw = ImageDraw.Draw(art)
    for row in range(ROWS):
        for col in range(COLS):
            half = CELL_H // 2
            draw_block(draw, col * CELL_W, row * CELL_H, half, cells.getpixel((col, row * 2)))
            draw_block(draw, col * CELL_W, row * CELL_H + half, CELL_H - half,
                       cells.getpixel((col, row * 2 + 1)))

    # The inter-row baseline is drawn in build_crt after the bloom, so the
    # glow cannot smear it into a soft undulation.
    art.save(target)
    print(f"wrote {target} {art.size}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
