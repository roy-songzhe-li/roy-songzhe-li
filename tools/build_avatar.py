"""Turn a GitHub avatar into a green-phosphor, dithered pixel portrait.

The reference look (a cool-retro-term screenshot) keeps the subject at full
phosphor brightness, drops outlines to near-black and leaves the backdrop as a
mid-tone dither, so the tones are remapped explicitly rather than left to the
avatar's own luminance.
"""
import math
import sys
from PIL import Image, ImageDraw, ImageOps

RAMP = [(48, 95, 39), (91, 169, 74), (123, 189, 87), (222, 253, 192), (227, 243, 211)]
SOURCE_CELLS = 104
DITHER_WIDTH, DITHER_HEIGHT = 260, 289
SCALE = 2
CELL_BAND_PERIOD = 23
BG_TOLERANCE = 32    # flood-fill tolerance for the avatar's flat backdrop

TONE_OUTLINE, TONE_MIDTONE, TONE_SUBJECT, TONE_BACKDROP = 12, 88, 246, 160
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
    """Flatten the avatar's tones onto four deliberate phosphor levels."""
    lut = [
        TONE_OUTLINE if v < SHADOW_CUTOFF else TONE_MIDTONE if v < MIDTONE_CUTOFF else TONE_SUBJECT
        for v in range(256)
    ]
    return grey.point(lut)


def ordered_dither(tones):
    """Quantize with a stable 4x4 screen-door matrix instead of diffusion noise."""
    bayer = (
        (0, 8, 2, 10),
        (12, 4, 14, 6),
        (3, 11, 1, 9),
        (15, 7, 13, 5),
    )
    pixels = []
    for y in range(tones.height):
        for x in range(tones.width):
            scaled = tones.getpixel((x, y)) * (len(RAMP) - 1) / 255
            lower = min(math.floor(scaled), len(RAMP) - 1)
            threshold = (bayer[y % 4][x % 4] + 0.5) / 16
            pixels.append(RAMP[min(lower + (scaled - lower > threshold), len(RAMP) - 1)])
    result = Image.new("RGB", tones.size)
    result.putdata(pixels)
    return result


def apply_character_bands(art):
    """Reproduce the darker baseline at the bottom of each terminal character row."""
    pixels = art.load()
    for y in range(art.height):
        phase = y % CELL_BAND_PERIOD
        factor = 0.92 if phase == CELL_BAND_PERIOD - 1 else 0.97 if phase == 0 else 1.0
        if factor < 1:
            for x in range(art.width):
                pixels[x, y] = tuple(round(channel * factor) for channel in pixels[x, y])
    return art


def main(source, target):
    avatar = Image.open(source).convert("RGB")
    tones = remap_tones(ImageOps.grayscale(avatar))
    tones.paste(Image.new("L", avatar.size, TONE_BACKDROP), (0, 0), backdrop_mask(avatar))
    tones = tones.resize((SOURCE_CELLS, SOURCE_CELLS), Image.Resampling.LANCZOS)
    tones = tones.resize((DITHER_WIDTH, DITHER_HEIGHT), Image.Resampling.BILINEAR)
    art = ordered_dither(tones).resize(
        (DITHER_WIDTH * SCALE, DITHER_HEIGHT * SCALE), Image.Resampling.NEAREST
    )
    art = apply_character_bands(art)
    art.save(target)
    print(f"wrote {target} {art.size}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
