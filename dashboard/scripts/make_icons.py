"""Regenerate the dashboard icons from the Orion Router logo (developer tool; needs Pillow, the build does not).

    python dashboard/scripts/make_icons.py

brand/orion-router-logo.png is a large raster of thin lines. Shrunk in one step, as a browser shrinks a big
favicon, the lines break apart. Each size here is drawn from a copy eight times larger, its lines widened to at
least LINE px of the result, on the white rounded tile, then shrunk once. Up to SIMPLE px the small dots and
crosses around the constellation are left out (at 16 px they only blot it) and the rest fills the tile.
The outputs are committed:
  public/favicon.ico        16..256 px: the browser tab, the app window's title bar, and the taskbar icon
                            (the Orion host sets it on the Router window from the installed copy of this file)
  public/logo-{36,72,108}.png  the sidebar logo at 1x, 2x and 3x
More: orion-ai-assistant/docs/ikonlar.md.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

DASHBOARD = Path(__file__).resolve().parents[1]
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)  # Windows asks for 16/32 at 100 %, 20/40 at 125 %, 24/48 at 150 %.
LOGO_SIZES = (36, 72, 108)                      # The sidebar shows it at 36 CSS px.
CONTENT = (122, 104, 1113, 1112)                # The drawing inside the logo's white margin.
SIMPLE = 24                                     # The largest size drawn without the ornaments.
ORNAMENTS = ((538, 200, 40), (143, 570, 40), (347, 1087, 40), (877, 1085, 40), (843, 255, 60), (285, 745, 60))
SIMPLE_CONTENT = (152, 94, 1113, 1055)          # The constellation alone, square.
STROKE = 35                                     # Its line width in source px.
LINE = 0.85                                     # Thinnest line in a result, px (thicker blots 16 px).
PADDING = 0.06                                  # Of the tile, each side.
RADIUS = 0.2                                    # Of the tile.

logo = Image.open(DASHBOARD / 'brand/orion-router-logo.png').convert('RGB')
full = logo.crop(CONTENT)
plain = logo.copy()
for x, y, r in ORNAMENTS:  # (centre x, centre y, half width) of each dot and cross
    ImageDraw.Draw(plain).rectangle((x - r, y - r, x + r, y + r), fill='white')
simple = plain.crop(SIMPLE_CONTENT)


def tile(size):
    drawing = simple if size <= SIMPLE else full
    large = size * 8
    inner = round(large * (1 - 2 * PADDING))
    picture = drawing.resize((inner, inner), Image.LANCZOS)
    widen = round(LINE * 8 - STROKE * inner / drawing.width)
    if widen > 1:
        picture = picture.filter(ImageFilter.MinFilter(widen | 1))  # Dark lines grow over the white.
    canvas = Image.new('RGB', (large, large), 'white')
    canvas.paste(picture, ((large - inner) // 2,) * 2)
    shape = Image.new('L', (large, large), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, large - 1, large - 1), radius=large * RADIUS, fill=255)
    canvas.putalpha(shape)
    return canvas.resize((size, size), Image.LANCZOS)


icons = [tile(size) for size in ICON_SIZES]
icons[-1].save(DASHBOARD / 'public/favicon.ico', format='ICO', sizes=[(s, s) for s in ICON_SIZES], append_images=icons[:-1])
for size in LOGO_SIZES:
    tile(size).save(DASHBOARD / f'public/logo-{size}.png', optimize=True)
