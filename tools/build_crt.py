"""Age the flat terminal still into a curved, glowing CRT and animate it as a GIF."""
import math
import pathlib
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

SCANLINE_PERIOD = 3        # a bright row every 3rd row, matching the reference screenshot
SCANLINE_DARKEN = 0.76
TINT_STRENGTH = 0.86       # how far every colour is pulled toward the green phosphor ramp
TINT_SHADOW, TINT_MID, TINT_HIGHLIGHT = "#050b04", "#69ad50", "#ecf4df"
WARP_MARGIN = 40           # padding added before the barrel warp so nothing is cropped away
WARP_K1 = -0.055
BEZEL = "#070c07"
SCREEN_INSET_X, SCREEN_INSET_Y = 16, 11
CORNER_RADIUS = 26
FRAMES = 18
NOISE_SIGMA = 13
NOISE_OPACITY = 0.10
FLICKER = 0.018
BAND_HEIGHT, BAND_STRENGTH = 100, 14


def apply_phosphor_tint(screen):
    """Pull every colour toward the green phosphor ramp, the way a mono tube would."""
    ramped = ImageOps.colorize(
        ImageOps.grayscale(screen), black=TINT_SHADOW, white=TINT_HIGHLIGHT, mid=TINT_MID
    )
    return Image.blend(screen, ramped, TINT_STRENGTH)


def apply_scanlines(screen):
    mask = Image.new("L", screen.size, 255)
    draw = ImageDraw.Draw(mask)
    for y in range(screen.height):
        if y % SCANLINE_PERIOD:
            draw.line((0, y, screen.width, y), int(255 * SCANLINE_DARKEN))
    return ImageChops.multiply(screen, Image.merge("RGB", [mask] * 3))


def apply_bloom(screen, sigma=5, opacity=0.30):
    glow = screen.filter(ImageFilter.GaussianBlur(sigma))
    return Image.blend(screen, ImageChops.screen(screen, glow), opacity)


def apply_barrel(screen, workdir):
    """Bulge the picture the way a real tube does, via ffmpeg's lenscorrection."""
    padded = Image.new("RGB", (screen.width + WARP_MARGIN * 2, screen.height + WARP_MARGIN * 2), "#0a1508")
    padded.paste(screen, (WARP_MARGIN, WARP_MARGIN))
    source, target = workdir / "pre-warp.png", workdir / "post-warp.png"
    padded.save(source)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-vf", f"lenscorrection=cx=0.5:cy=0.5:k1={WARP_K1}:k2=0:i=bilinear", str(target)],
        check=True,
    )
    with Image.open(target) as warped:
        return warped.convert("RGB").crop(
            (WARP_MARGIN, WARP_MARGIN, WARP_MARGIN + screen.width, WARP_MARGIN + screen.height)
        )


def apply_vignette(screen):
    width, height = screen.size
    shade = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(shade)
    steps = 18
    for step in range(steps):
        inset = step * 3
        level = int(255 * (0.58 + 0.42 * (step / steps) ** 0.7))
        draw.rounded_rectangle(
            (inset, inset, width - inset, height - inset), radius=CORNER_RADIUS + 30, fill=level
        )
    shaded = ImageChops.multiply(screen, Image.merge("RGB", [shade.filter(ImageFilter.GaussianBlur(20))] * 3))
    # The bloom lifts the blacks; pull them back down and re-saturate the phosphor.
    graded = ImageEnhance.Contrast(shaded).enhance(1.30)
    return ImageEnhance.Color(graded).enhance(1.18)


def rolling_band(size, position):
    width, height = size
    column = Image.new("L", (1, height), 0)
    pixels = column.load()
    for y in range(height):
        distance = (y - position) / BAND_HEIGHT
        pixels[0, y] = int(BAND_STRENGTH * math.exp(-distance * distance))
    return column.resize(size, Image.BILINEAR)


def compose_bezel(picture, canvas_size):
    """Seat the tube picture inside a dark plastic bezel with rounded screen corners."""
    width, height = canvas_size
    inner = picture.resize((width - SCREEN_INSET_X * 2, height - SCREEN_INSET_Y * 2), Image.LANCZOS)
    mask = Image.new("L", inner.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, inner.width - 1, inner.height - 1), CORNER_RADIUS, 255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))

    canvas = Image.new("RGB", canvas_size, BEZEL)
    halo = Image.new("RGB", canvas_size, "#000000")
    halo.paste(inner, (SCREEN_INSET_X, SCREEN_INSET_Y), mask)
    canvas = ImageChops.screen(canvas, halo.filter(ImageFilter.GaussianBlur(18)))
    canvas.paste(inner, (SCREEN_INSET_X, SCREEN_INSET_Y), mask)
    return canvas


def main(screen_path, out_gif):
    # Scratch lives beside this script, never next to the published GIF.
    workdir = pathlib.Path(__file__).parent / "build" / "crt"
    frames_dir = workdir / "frames"
    workdir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("*.png"):
        stale.unlink()

    with Image.open(screen_path) as raw:
        screen = raw.convert("RGB")
    tube = apply_vignette(
        apply_barrel(apply_bloom(apply_scanlines(apply_phosphor_tint(screen))), workdir)
    )

    span = tube.height + BAND_HEIGHT * 4
    for index in range(FRAMES):
        frame = ImageChops.screen(tube, Image.merge("RGB", [rolling_band(
            tube.size, -BAND_HEIGHT * 2 + span * index / FRAMES)] * 3))
        noise = Image.effect_noise(tube.size, NOISE_SIGMA).convert("RGB")
        frame = Image.blend(frame, ImageChops.add(frame, noise, scale=1.0, offset=-20), NOISE_OPACITY)
        frame = ImageEnhance.Brightness(frame).enhance(
            1 + FLICKER * math.sin(index / FRAMES * math.tau * 3))
        compose_bezel(frame, screen.size).save(frames_dir / f"crt_{index:03d}.png")

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "12",
         "-i", str(frames_dir / "crt_%03d.png"),
         "-filter_complex", "[0:v] split [a][b];[a] palettegen=max_colors=160 [p];[b][p] paletteuse=dither=bayer:bayer_scale=3",
         "-loop", "0", out_gif],
        check=True,
    )
    print(f"wrote {out_gif} ({pathlib.Path(out_gif).stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
