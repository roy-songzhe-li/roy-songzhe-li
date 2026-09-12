"""Convert the original avatar into a 48-by-24 green terminal character grid."""
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw, ImageFont

COLUMNS, ROWS = 48, 24
PORTRAIT_SIZE = (432, 480)
SYMBOLS = ' ▀▄█▌▐░▒▓'
FONT = Path(__file__).parent / 'fonts' / 'VGA.ttf'
PALETTE = np.array([(33, 72, 29), (74, 128, 53), (126, 184, 91),
                    (176, 212, 138), (226, 233, 210)])


def prepare_tones(source):
    with Image.open(source) as image:
        image = image.convert('RGB')
        pixels = np.asarray(image, dtype=float)
        backdrop = np.max(np.abs(pixels - pixels[0, 0]), axis=2) < 35
        tones = np.clip((np.asarray(image.convert('L'), dtype=float) - 15) * 255 / 185, 0, 255)
    tones[backdrop] = 155
    return Image.fromarray(tones.astype(np.uint8))


def render_characters(output):
    font = ImageFont.truetype(str(FONT), 16)
    art = Image.new('L', (COLUMNS * 8, ROWS * 16))
    draw = ImageDraw.Draw(art)
    draw.fontmode = '1'
    row = col = 0
    foreground, background = 255, 0
    for token in re.findall(r'\x1b\[[0-?]*[ -/]*[@-~]|[^\x1b]', output):
        if token.startswith('\x1b'):
            if token.endswith('m'):
                codes = [int(value or 0) for value in token[2:-1].split(';')]
                index = 0
                while index < len(codes):
                    code = codes[index]
                    if code in (38, 48) and index + 4 < len(codes) and codes[index + 1] == 2:
                        value = round(sum(codes[index + 2:index + 5]) / 3)
                        if code == 38:
                            foreground = value
                        else:
                            background = value
                        index += 5
                    else:
                        if code == 0:
                            foreground, background = 255, 0
                        elif code == 39:
                            foreground = 255
                        elif code == 49:
                            background = 0
                        index += 1
        elif token == '\n':
            row += 1
            col = 0
        elif token == '\r':
            col = 0
        else:
            if token not in SYMBOLS or row >= ROWS or col >= COLUMNS:
                raise ValueError(f'Unexpected terminal output at row {row}, column {col}: {token!r}')
            draw.rectangle((col * 8, row * 16, col * 8 + 7, row * 16 + 15), fill=background)
            draw.text((col * 8, row * 16), token, font=font, fill=foreground)
            col += 1
    values = np.asarray(art.resize(PORTRAIT_SIZE, Image.Resampling.LANCZOS), dtype=float)
    ramp = np.arange(len(PALETTE)) * 255 / (len(PALETTE) - 1)
    colors = np.stack([np.interp(values, ramp, PALETTE[:, channel]) for channel in range(3)], axis=2)
    return Image.fromarray(colors.astype(np.uint8))


def main(source, target):
    with TemporaryDirectory(prefix='crt-avatar-') as directory:
        tones = Path(directory) / 'tones.png'
        prepare_tones(source).save(tones)
        output = subprocess.check_output([
            'chafa', '--format', 'symbols', '--colors', 'full', '--optimize', '0',
            '--symbols', f'[{SYMBOLS}]', '--fill', 'stipple', '--size', f'{COLUMNS}x{ROWS}',
            '--stretch', '--fg', '#ffffff', '--bg', '#000000', '--preprocess', 'off',
            '--work', '9', '--probe', 'off', str(tones),
        ], text=True)
    render_characters(output).save(target)
    print(f'Wrote {target}: {COLUMNS} x {ROWS} terminal cells')


if __name__ == '__main__':
    main(*sys.argv[1:])
