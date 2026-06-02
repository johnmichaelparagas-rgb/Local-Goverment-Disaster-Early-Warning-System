"""Generate the 1200x630 social-share (Open Graph) image for the landing page.

Run:  python scripts/make_og_image.py
Output: static/og-image.png

Re-run whenever the branding changes. Uses Pillow (already a dependency).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (15, 23, 42)        # --bg  #0f172a
PANEL = (30, 41, 59)     # --panel
BRAND = (14, 165, 233)   # --brand #0ea5e9
BRAND2 = (2, 132, 199)   # --brand-2
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)

OUT = Path(__file__).resolve().parent.parent / 'static' / 'og-image.png'


def load_font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # Soft top glow band (faux radial) using stacked translucent ellipses.
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, a in enumerate(range(40, 0, -4)):
        spread = 360 + i * 26
        gd.ellipse([W / 2 - spread, -220 - i * 8, W / 2 + spread, 240 + i * 8],
                   fill=(14, 165, 233, a))
    img.paste(Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB'), (0, 0))
    d = ImageDraw.Draw(img)

    # Brand crest — rounded square with a vertical brand gradient + white triangle.
    cx, cy, cs = 110, 150, 132
    crest = Image.new('RGB', (cs, cs), BRAND)
    cd = ImageDraw.Draw(crest)
    for y in range(cs):
        t = y / cs
        cd.line([(0, y), (cs, y)],
                fill=(int(BRAND[0] + (BRAND2[0] - BRAND[0]) * t),
                      int(BRAND[1] + (BRAND2[1] - BRAND[1]) * t),
                      int(BRAND[2] + (BRAND2[2] - BRAND[2]) * t)))
    mask = Image.new('L', (cs, cs), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cs, cs], radius=30, fill=255)
    img.paste(crest, (cx, cy), mask)

    # White warning triangle + exclamation inside the crest.
    tx, ty, tw = cx + cs / 2, cy + 26, 78
    d.line([(tx, ty), (tx + tw / 2, ty + tw), (tx - tw / 2, ty + tw), (tx, ty)],
           fill=(255, 255, 255), width=9, joint='curve')
    d.rounded_rectangle([tx - 5, ty + 30, tx + 5, ty + 60], radius=5, fill=(255, 255, 255))
    d.ellipse([tx - 6, ty + 66, tx + 6, ty + 78], fill=(255, 255, 255))

    # Wordmark + subtitle.
    f_kicker = load_font(['segoeui.ttf', 'arial.ttf'], 30)
    f_title = load_font(['segoeuib.ttf', 'arialbd.ttf', 'arial.ttf'], 92)
    f_sub = load_font(['segoeui.ttf', 'arial.ttf'], 38)

    d.text((cx + cs + 34, cy + 6), 'MDRRMO · LEYTE', font=f_kicker, fill=BRAND)
    d.text((cx + cs + 34, cy + 44), 'Leyte DEWS', font=f_title, fill=(255, 255, 255))

    d.text((110, 360), 'Disaster Early Warning System', font=f_sub, fill=TEXT)
    d.text((110, 414),
           'Real-time hazard monitoring · incident reporting · early-warning broadcasts',
           font=load_font(['segoeui.ttf', 'arial.ttf'], 28), fill=MUTED)

    # Accent rule + footer URL.
    d.rounded_rectangle([110, 486, 350, 492], radius=3, fill=BRAND)
    d.text((110, 540), 'leyte-dews.onrender.com',
           font=load_font(['segoeui.ttf', 'arial.ttf'], 28), fill=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, 'PNG')
    print(f'Wrote {OUT} ({OUT.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
