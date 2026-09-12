"""Render a softly glowing CRT with fine raster lines and rolling phosphor persistence."""
from pathlib import Path
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from build_screen import BACKGROUND, WIDTH, HEIGHT

FRAMES, FPS = 88, 14
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
    # Fine shade texture is independent of the coarse grid that defines the face.
    portrait = tube[18:498, 22:454]
    luminance = source[18:498, 22:454] @ np.array([.299, .587, .114])
    midtones = np.clip((luminance - 55) / 55, 0, 1) * np.clip((225 - luminance) / 40, 0, 1)
    dot_y, dot_x = np.indices(luminance.shape)
    stipple = np.cos(math.tau * dot_x / 3) * np.cos(math.tau * dot_y / 3)
    amplitude = np.minimum(56 * midtones, 255 - portrait.max(axis=2))
    portrait += (stipple * amplitude)[:, :, None]
    # Character-row baselines belong to the portrait and curve with its glass.
    for row in range(24):
        top = 18 + row * 20 + 18
        tube[top:top + 1, 22:454] *= .80
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
    noise_strength = np.full((HEIGHT, WIDTH), 1.0, dtype=np.float32)
    noise_strength[18:498, 22:454] = 1.55
    noise_strength[18:216, 484:776] = 1.45
    noise_strength[228:279, 485:719] = 3.6
    coarse_size = ((HEIGHT + 1) // 2, (WIDTH + 1) // 2)
    for index in range(FRAMES):
        phase = index / FRAMES
        # A rolling exposure dip and soft trailing persistence modulate existing light.
        cycle = HEIGHT + 320
        distance = (yy + 160 - phase * cycle + cycle / 2) % cycle - cycle / 2
        refresh = -.12 * np.exp(-(distance / 44) ** 2)
        refresh += .035 * np.exp(-((distance + 66) / 62) ** 2)
        raster = .006 * np.cos(yy * math.tau / 3.1 - math.tau * phase * 11)
        flicker = .002 * math.sin(math.tau * phase * 3) + .001 * math.sin(math.tau * phase * 13)
        frame = base * (1 + ((refresh + raster + flicker) * mask)[:, :, None])
        if index % 2 == 0:
            grain = rng.normal(0, 1, coarse_size).repeat(2, 0).repeat(2, 1)[:HEIGHT, :WIDTH]
            chroma = rng.normal(0, .35, (*coarse_size, 3)).repeat(2, 0).repeat(2, 1)[:HEIGHT, :WIDTH]
        frame += (grain[:, :, None] + chroma) * (noise_strength * mask)[:, :, None]
        # Keep the cabinet steady; only the phosphor image has a tiny horizontal nudge.
        displacement = (.025 * math.sin(math.tau * phase * 7)
                        + .018 * np.sin(np.arange(HEIGHT) * .19 + math.tau * phase * 3))
        displacement += .22 * np.exp(-((phase - 27 / 44) / .012) ** 2)
        neighbor = np.where((displacement >= 0)[:, None, None],
                            np.roll(frame, 1, axis=1), np.roll(frame, -1, axis=1))
        weight = (np.abs(displacement)[:, None] * mask)[:, :, None]
        frame = frame * (1 - weight) + neighbor * weight
        rgb(frame).save(workdir / f'frame-{index:03d}.png')
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-framerate', str(FPS),
        '-i', str(workdir / 'frame-%03d.png'), '-frames:v', str(FRAMES), '-filter_complex',
        '[0:v]split[a][b];[a]palettegen=max_colors=128:stats_mode=full[p];'
        '[b][p]paletteuse=dither=none:diff_mode=rectangle', '-loop', '0', out_gif,
    ], check=True)
    print(f'Wrote {out_gif}: {Path(out_gif).stat().st_size / 1e6:.2f} MB')


if __name__ == '__main__':
    main(*sys.argv[1:3], still_only='--still' in sys.argv[3:])
