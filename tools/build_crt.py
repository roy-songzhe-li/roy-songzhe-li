"""Render a softly glowing CRT with deterministic grain and a seamless refresh cycle."""
from pathlib import Path
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from build_screen import BACKGROUND, WIDTH, HEIGHT

FRAMES, FPS = 48, 8
SEED = 0x435254


def rgb(values):
    return Image.fromarray(np.clip(values, 0, 255).astype(np.uint8))


def blur(values, radius):
    return np.asarray(rgb(values).filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)


def barrel(image):
    mesh = []
    def point(x, y):
        nx, ny = (x - 399.5) / 399.5, (y - 270) / 270
        radial = nx * nx + ny * ny
        return (399.5 + (x - 399.5) * (1 + .022 * ny * ny + .006 * radial),
                270 + (y - 270) * (1 + .028 * nx * nx + .006 * radial))
    for top in range(0, HEIGHT, 24):
        for left in range(0, WIDTH, 24):
            right, bottom = min(left + 24, WIDTH), min(top + 24, HEIGHT)
            mesh.append(((left, top, right, bottom),
                         (*point(left, top), *point(left, bottom),
                          *point(right, bottom), *point(right, top))))
    return image.transform(image.size, Image.Transform.MESH, mesh,
                           Image.Resampling.BICUBIC, fillcolor=BACKGROUND)


def prepare(screen_path):
    with Image.open(screen_path) as screen:
        source = np.asarray(screen.convert('RGB'), dtype=np.float32)
    with Image.open(Path(screen_path).with_name('text-mask.png')) as mask:
        text_mask = np.asarray(mask, dtype=np.float32) / 255
    source[232:272, 490:714] *= .76
    emission = np.maximum(source - BACKGROUND, 0)
    gain = np.full((HEIGHT, WIDTH), .06, dtype=np.float32)
    gain[text_mask > 0] = 1.3
    gain[232:272, 490:714] = 1.0
    emission *= gain[:, :, None]
    tube = source * .55 + blur(source, .60) * .45
    tube += blur(emission, 1.1) * .28 + blur(emission, 4) * .30 + blur(emission, 11) * .18
    swatch_emission = np.zeros_like(emission)
    swatch_emission[232:272, 490:714] = emission[232:272, 490:714]
    tube += blur(swatch_emission, 8) * .24 + blur(swatch_emission, 18) * .20
    portrait_emission = np.zeros_like(source)
    portrait_emission[18:498, 22:454] = np.maximum(source[18:498, 22:454] - BACKGROUND, 0)
    portrait_halo = blur(portrait_emission, 7) * (.12, .22, .07)
    portrait_halo[18:498, 22:454] = 0
    tube += portrait_halo
    yy, xx = np.indices((HEIGHT, WIDTH))
    tube *= (1 - .045 * (1 + np.cos(yy * math.tau / 3.1)) / 2)[:, :, None]
    # A faint horizontal phosphor structure remains visible in the dark glass.
    tube += (np.sin(yy * 1.7) * .4)[:, :, None]
    tube = np.asarray(barrel(rgb(tube)), dtype=np.float32)
    edge = np.clip(np.minimum.reduce([xx / 24, (799 - xx) / 24,
                                     yy / 24, (540 - yy) / 24]), 0, 1)
    tube *= (.50 + .50 * edge * edge * (3 - 2 * edge))[:, :, None]
    mask = Image.new('L', (WIDTH, HEIGHT))
    ImageDraw.Draw(mask).rounded_rectangle((10, 10, 790, 531), radius=26, fill=255)
    mask = np.asarray(mask.filter(ImageFilter.GaussianBlur(1.6)), dtype=np.float32) / 255
    bezel = np.zeros_like(tube) + (11, 18, 10)
    bezel += blur(tube * mask[:, :, None], 12) * .17
    base = tube * mask[:, :, None] + bezel * (1 - mask[:, :, None])
    return base, mask


def main(screen_path, out_gif, still_only=False):
    workdir = Path(screen_path).parent / 'crt'
    workdir.mkdir(parents=True, exist_ok=True)
    base, mask = prepare(screen_path)
    rng = np.random.default_rng(SEED)
    yy, xx = np.indices((HEIGHT, WIDTH))
    # Fixed fine grain avoids temporal palette shimmer across the entire portrait.
    grain = rng.normal(0, 1.6, (HEIGHT, WIDTH, 1))
    base += grain * mask[:, :, None]
    still_path = Path(out_gif).with_suffix('.png')
    rgb(base).save(still_path)
    if still_only:
        return
    for index in range(FRAMES):
        phase = index / FRAMES
        distance = ((yy - (-70 + phase * (HEIGHT + 140)) + (HEIGHT + 140) / 2)
                    % (HEIGHT + 140) - (HEIGHT + 140) / 2)
        band = 4 * np.exp(-(distance / 26) ** 2)
        flicker = .003 * math.sin(math.tau * phase) + .0015 * math.sin(math.tau * phase * 3)
        shimmer = .8 * np.sin(xx * .7 + yy * 1.3 + math.tau * phase)
        frame = base * (1 + flicker * mask[:, :, None])
        frame += ((band + shimmer) * mask)[:, :, None]
        rgb(frame).save(workdir / f'frame-{index:03d}.png')
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-framerate', str(FPS),
        '-i', str(workdir / 'frame-%03d.png'), '-frames:v', str(FRAMES), '-filter_complex',
        '[0:v]split[a][b];[a]palettegen=max_colors=255:stats_mode=full[p];'
        '[b][p]paletteuse=dither=none:diff_mode=rectangle', '-loop', '0', out_gif,
    ], check=True)
    print(f'Wrote {out_gif}: {Path(out_gif).stat().st_size / 1e6:.2f} MB')


if __name__ == '__main__':
    main(*sys.argv[1:3], still_only='--still' in sys.argv[3:])
