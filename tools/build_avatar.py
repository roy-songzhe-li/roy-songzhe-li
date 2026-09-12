"""Turn a GitHub avatar into a green-phosphor, dithered pixel portrait.

The reference look (a cool-retro-term screenshot) keeps the subject at full
phosphor brightness, drops outlines to near-black and leaves the backdrop as a
mid-tone dither, so the tones are remapped explicitly rather than left to the
avatar's own luminance.
"""
import sys
from PIL import Image, ImageDraw, ImageOps

RAMP = [(24, 54, 20), (91, 156, 72), (150, 211, 120), (200, 236, 176), (238, 243, 223)]
BLOCKS = 104         # pixel-art resolution in blocks across
SCALE = 5            # nearest-neighbour upscale, final art is BLOCKS * SCALE px
BG_TOLERANCE = 32    # flood-fill tolerance for the avatar's flat backdrop

TONE_OUTLINE, TONE_MIDTONE, TONE_SUBJECT, TONE_BACKDROP = 12, 88, 246, 138
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


def build_palette_image():
    palette = Image.new("P", (1, 1))
    palette.putpalette([c for colour in RAMP for c in colour] + [0, 0, 0] * (256 - len(RAMP)))
    return palette


def main(source, target):
    avatar = Image.open(source).convert("RGB")
    tones = remap_tones(ImageOps.grayscale(avatar))
    tones.paste(Image.new("L", avatar.size, TONE_BACKDROP), (0, 0), backdrop_mask(avatar))
    tones = tones.resize((BLOCKS, BLOCKS), Image.LANCZOS).convert("RGB")
    dithered = tones.quantize(palette=build_palette_image(), dither=Image.FLOYDSTEINBERG)
    art = dithered.convert("RGB").resize((BLOCKS * SCALE, BLOCKS * SCALE), Image.NEAREST)
    art.save(target)
    print(f"wrote {target} {art.size}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
