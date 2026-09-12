"""Compose a terminal still with a native bitmap grid and separate emission masks."""
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 800, 541
BACKGROUND = (18, 37, 15)
PORTRAIT_POSITION = (22, 18)
PANEL_X, PANEL_Y, CELL_W, CELL_H = 490, 18, 9, 20
LABEL, VALUE = '#7db343', '#79b95f'
FONT = Path(__file__).parent / 'fonts' / 'Terminus.ttf'
FIELDS = [('Name', ['Roy Li']), ('Site', ['roy-li.dev']), ('Work', ['Aetheron']),
          ('OS', ['macOS']), ('Languages', ['TypeScript, Python,', 'JavaScript, Shell']),
          ('Skills', ['AI Agents, Full Stack,', 'Forward Deployed', 'Engineering'])]
SWATCH_COLORS = [
    ['#1b4514', '#ad7925', '#10dc42', '#d2db57', '#35c974', '#ad7e77', '#19d76a', '#8dcc72'],
    ['#4f9f40', '#b7bd4d', '#b5da7a', '#dae576', '#a5da92', '#c9dda1', '#dce4ac', '#e1e7bb'],
]


def text_mask(text):
    font = ImageFont.truetype(str(FONT), 12)
    mask = Image.new('L', (len(text) * 6, 13))
    ImageDraw.Draw(mask).text((0, 0), text, font=font, fill=255, anchor='lt')
    mask = mask.resize((len(text) * CELL_W, 18), Image.Resampling.NEAREST)
    return ImageChops.lighter(mask, mask.filter(ImageFilter.MaxFilter(3)).point(lambda v: round(v * .24)))


def main(avatar_path, swatch_path, out_path):
    canvas = Image.new('RGB', (WIDTH, HEIGHT), BACKGROUND)
    text_emission = Image.new('L', canvas.size)
    draw_mask = ImageDraw.Draw(text_emission)

    def write(text, x, y, color):
        mask = text_mask(text)
        if x + mask.width > WIDTH - 24:
            raise ValueError(f'Text exceeds the screen: {text}')
        canvas.paste(color, (x, y), mask)
        text_emission.paste(mask, (x, y))

    with Image.open(avatar_path) as avatar:
        canvas.paste(avatar, PORTRAIT_POSITION)
    row = 0
    for label, lines in FIELDS:
        write(label + ':', PANEL_X, PANEL_Y + row * CELL_H, LABEL)
        value_x = PANEL_X + (len(label) + 2) * CELL_W
        for line in lines:
            write(line, value_x, PANEL_Y + row * CELL_H, VALUE)
            row += 1

    swatch = Image.new('RGB', (224, 40), BACKGROUND)
    draw = ImageDraw.Draw(swatch)
    for row, colors in enumerate(SWATCH_COLORS):
        for col, color in enumerate(colors):
            draw.rectangle((col * 28, row * 20, col * 28 + 27, row * 20 + 19), fill=color)
    swatch.save(swatch_path)
    canvas.paste(swatch, (490, 232))
    write('roy@mbp$ ', 22, 499, VALUE)
    cursor = (103, 499, 111, 516)
    ImageDraw.Draw(canvas).rectangle(cursor, fill='#c3e694')
    draw_mask.rectangle(cursor, fill=255)
    canvas.save(out_path)
    text_emission.save(Path(out_path).with_name('text-mask.png'))


if __name__ == '__main__':
    main(*sys.argv[1:])
