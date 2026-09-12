"""Age the flat terminal still into a curved, glowing CRT and animate it as a GIF."""
import math
import pathlib
import random
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

FRAMES = 44
FPS = 7
SCANLINE_PERIOD = 3
SCANLINE_DARKEN = 0.86
TINT_STRENGTH = 0.30
TINT_SHADOW, TINT_MID, TINT_HIGHLIGHT = "#071007", "#69ad50", "#edf3df"
BARREL_X, BARREL_Y, BARREL_RADIAL = 0.022, 0.028, 0.006
MESH_STEP = 32
SCREEN_BOX = (9, 9, 791, 532)
CORNER_RADIUS = 25
BEZEL = "#0a0a0a"
NOISE_SEED = 0x435254
NOISE_BLOCK = 2
PORTRAIT_BOX = (18, 14, 462, 506)
# The dark baseline the terminal leaves between character rows. Measured on the
# reference face strip: a crisp 3px line every 20px, about 24% down. It is laid
# in after the bloom so the glow cannot smear it, but before the warp so it
# still bends with the tube.
PORTRAIT_ART_BOX = (22, 14, 446, 494)
ROW_PITCH, ROW_LINE_PX, ROW_LINE_DARKEN = 20, 3, 0.85
# One refresh band sweeps down the tube per loop. Measured off the reference:
# it enters near y=20 at frame 8 and reaches y=499 by frame 39, ~16.5px/frame,
# peaking around +6.5 luma when read through a 13px window - never a hard bar.
SCAN_FIRST_FRAME, SCAN_LAST_FRAME = 7, 38
SCAN_Y_START, SCAN_Y_END = 20, 499
SCAN_HALF_HEIGHT, SCAN_PEAK = 26, 6
SCAN_EASE = 1.2                 # the reference sweep starts slow and accelerates
SWATCH_MOTION_BOX = (486, 188, 718, 238)
PORTRAIT_TONE_POINTS = (
    (0, 0), (80, 71), (119, 117), (141, 136), (152, 145), (158, 152), (161, 161),
    (170, 166), (172, 172), (180, 178), (185, 183), (190, 188), (203, 193),
    (207, 200), (218, 208), (221, 217), (224, 233), (242, 236), (255, 238),
)


def apply_phosphor_tint(screen):
    ramped = ImageOps.colorize(
        ImageOps.grayscale(screen), black=TINT_SHADOW, white=TINT_HIGHLIGHT, mid=TINT_MID
    )
    return Image.blend(screen, ramped, TINT_STRENGTH)


def apply_scanlines(screen):
    mask = Image.new("L", screen.size, 255)
    draw = ImageDraw.Draw(mask)
    for y in range(SCANLINE_PERIOD - 1, screen.height, SCANLINE_PERIOD):
        draw.line((0, y, screen.width, y), fill=round(255 * SCANLINE_DARKEN))
    return ImageChops.multiply(screen, Image.merge("RGB", [mask] * 3))


def apply_bloom(screen):
    gate = ImageOps.grayscale(screen).point(lambda value: max(0, min(255, (value - 38) * 3)))
    emission = ImageChops.multiply(screen, Image.merge("RGB", [gate] * 3))
    glow = emission.filter(ImageFilter.GaussianBlur(6.5))
    return Image.blend(screen, ImageChops.screen(screen, glow), 0.62)


def source_point(x, y, size):
    width, height = size
    center_x, center_y = (width - 1) / 2, (height - 1) / 2
    nx, ny = (x - center_x) / center_x, (y - center_y) / center_y
    radial = nx * nx + ny * ny
    return (
        center_x + (x - center_x) * (1 + BARREL_X * ny * ny + BARREL_RADIAL * radial),
        center_y + (y - center_y) * (1 + BARREL_Y * nx * nx + BARREL_RADIAL * radial),
    )


def apply_barrel(screen):
    width, height = screen.size
    mesh = []
    for top in range(0, height, MESH_STEP):
        for left in range(0, width, MESH_STEP):
            right, bottom = min(left + MESH_STEP, width), min(top + MESH_STEP, height)
            mesh.append(((left, top, right, bottom), (
                *source_point(left, top, screen.size),
                *source_point(left, bottom, screen.size),
                *source_point(right, bottom, screen.size),
                *source_point(right, top, screen.size),
            )))
    return screen.transform(
        screen.size, Image.Transform.MESH, mesh, Image.Resampling.BICUBIC, fillcolor="#0b1909"
    )


def apply_vignette(screen):
    width, height = screen.size
    shade = Image.new("L", screen.size)
    pixels = []
    for y in range(height):
        vertical = min(y, height - 1 - y) / 24
        for x in range(width):
            edge = max(0.0, min(1.0, vertical, min(x, width - 1 - x) / 24))
            smooth = edge * edge * (3 - 2 * edge)
            pixels.append(round(255 * (0.47 + 0.53 * smooth)))
    shade.putdata(pixels)
    return ImageChops.multiply(screen, Image.merge("RGB", [shade.filter(ImageFilter.GaussianBlur(2))] * 3))


def apply_portrait_tone_curve(screen):
    """Compress the portrait shadows/highlights while preserving its phosphor hue."""
    lut = []
    for value in range(256):
        for (left_x, left_y), (right_x, right_y) in zip(PORTRAIT_TONE_POINTS, PORTRAIT_TONE_POINTS[1:]):
            if value <= right_x:
                ratio = (value - left_x) / (right_x - left_x)
                lut.append(round(left_y + ratio * (right_y - left_y)))
                break
    luma = ImageOps.grayscale(screen)
    target = luma.point(lut)
    lift = ImageChops.subtract(target, luma)
    cut = ImageChops.subtract(luma, target)
    adjusted = ImageChops.subtract(
        ImageChops.add(screen, Image.merge("RGB", (lift, lift, lift))),
        Image.merge("RGB", (cut, cut, cut)),
    )
    mask = Image.new("L", screen.size)
    ImageDraw.Draw(mask).rectangle(PORTRAIT_BOX, fill=255)
    return Image.composite(adjusted, screen, mask)


def screen_mask(size):
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rounded_rectangle(SCREEN_BOX, radius=CORNER_RADIUS, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(1.0))


def compose_bezel(picture, mask):
    canvas = Image.new("RGB", picture.size, BEZEL)
    frame = Image.new("RGB", picture.size)
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle((1, 1, picture.width - 2, picture.height - 2), radius=24, fill="#020502")
    draw.line((25, 1, picture.width - 26, 1), fill="#080c08", width=2)
    canvas = ImageChops.screen(canvas, frame.filter(ImageFilter.GaussianBlur(3)))
    glow = Image.new("RGB", picture.size)
    glow.paste(picture, mask=mask)
    canvas = ImageChops.screen(canvas, glow.filter(ImageFilter.GaussianBlur(14)))
    canvas.paste(picture, mask=mask)
    return canvas


def motion_strength(base, mask):
    luminance = ImageOps.grayscale(base).point(lambda value: round(118 + value * 137 / 255))
    strengths = []
    for edge, screen, portrait, panel, swatch in (
        (5, 19, 26, 31, 49),
        (7, 28, 30, 40, 36),
        (5, 20, 26, 32, 34),
    ):
        locations = Image.new("L", base.size, edge)
        draw = ImageDraw.Draw(locations)
        draw.bitmap((0, 0), mask, fill=screen)
        draw.rectangle((0, 0, base.width - 1, 12), fill=edge)
        draw.rectangle((0, base.height - 13, base.width - 1, base.height - 1), fill=edge)
        draw.rectangle((0, 0, 12, base.height - 1), fill=edge)
        draw.rectangle((base.width - 13, 0, base.width - 1, base.height - 1), fill=edge)
        draw.rectangle(PORTRAIT_BOX, fill=portrait)
        draw.rectangle((484, 14, 782, 218), fill=panel)
        draw.rectangle(SWATCH_MOTION_BOX, fill=swatch)
        strengths.append(ImageChops.lighter(
            Image.new("L", base.size, edge), ImageChops.multiply(locations, luminance)
        ))
    return strengths


def apply_character_rows(screen):
    """Draw the dark baseline between the portrait's character rows."""
    left, top, right, bottom = PORTRAIT_ART_BOX
    pixels = screen.load()
    for line in range(top + ROW_PITCH - ROW_LINE_PX, bottom, ROW_PITCH):
        for y in range(line, min(line + ROW_LINE_PX, bottom)):
            for x in range(left, right):
                pixels[x, y] = tuple(round(c * ROW_LINE_DARKEN) for c in pixels[x, y])
    return screen


def scan_band(size, centre):
    """A soft bright band at `centre`, the tube's refresh sweeping down the screen."""
    width, height = size
    column = Image.new("L", (1, height))
    pixels = column.load()
    for y in range(height):
        offset = (y - centre) / SCAN_HALF_HEIGHT
        pixels[0, y] = round(SCAN_PEAK * math.exp(-offset * offset))
    return column.resize(size, Image.Resampling.BILINEAR)


def sweep_frame(frame, mask, index):
    """Lay the refresh band over the screen area for the frames that carry it."""
    if not SCAN_FIRST_FRAME <= index <= SCAN_LAST_FRAME:
        return frame
    span = (index - SCAN_FIRST_FRAME) / (SCAN_LAST_FRAME - SCAN_FIRST_FRAME)
    travel = span ** SCAN_EASE * (SCAN_Y_END - SCAN_Y_START)
    band = scan_band(frame.size, SCAN_Y_START + travel)
    return Image.composite(
        ImageChops.add(frame, Image.merge("RGB", [band] * 3)), frame, mask
    )


def add_noise(frame, strength, rng, envelope):
    # Grain is generated at half resolution and nearest-upscaled, so it moves in
    # 2x2 blocks. Per-pixel grain changes almost every pixel every frame, which
    # defeats the GIF's inter-frame compression and doubles the file for motion
    # nobody can see at this amplitude.
    coarse = (frame.width // NOISE_BLOCK, frame.height // NOISE_BLOCK)
    noise = Image.frombytes("L", coarse, rng.randbytes(coarse[0] * coarse[1])).resize(
        frame.size, Image.Resampling.NEAREST
    )
    channels = []
    for channel, channel_strength in zip(frame.split(), strength):
        scaled_strength = channel_strength.point(lambda value: round(value * envelope))
        channels.append(Image.composite(
            ImageChops.add(channel, noise, offset=-128), channel, scaled_strength
        ))
    return Image.merge("RGB", channels)


def main(screen_path, out_gif):
    workdir = pathlib.Path(__file__).parent / "build" / "crt"
    frames_dir = workdir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("*.png"):
        stale.unlink()

    with Image.open(screen_path) as raw:
        screen = raw.convert("RGB")
    mask = screen_mask(screen.size)
    tube = apply_portrait_tone_curve(
        apply_vignette(apply_barrel(apply_character_rows(
            apply_bloom(apply_scanlines(apply_phosphor_tint(screen))))))
    )
    base = compose_bezel(tube, mask)
    strength = motion_strength(base, mask)
    noise_rng = random.Random(NOISE_SEED)
    drift_rng = random.Random(NOISE_SEED + 1)
    drift = 0.0

    for index in range(FRAMES):
        if index:
            drift = max(-0.008, min(0.012, drift + drift_rng.uniform(-0.0017, 0.0017)))
            ramp = 0.57 if index == 1 else 0.70 + 0.24 * min((index - 2) / 16, 1)
            envelope = ramp * (2.4 if index == 27 else 1)
            shifted = ImageEnhance.Brightness(base).enhance(1 + drift)
            frame = add_noise(Image.composite(shifted, base, mask), strength, noise_rng, envelope)
        else:
            frame = base
        frame = sweep_frame(frame, mask, index)
        frame.save(frames_dir / f"crt_{index:03d}.png")

    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
         "-i", str(frames_dir / "crt_%03d.png"), "-filter_complex",
         "[0:v]split[a][b];[a]palettegen=max_colors=72:stats_mode=full[p];"
         "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", "-loop", "0", out_gif],
        check=True,
    )
    print(f"wrote {out_gif} ({pathlib.Path(out_gif).stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
