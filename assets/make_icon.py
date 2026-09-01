"""Erzeugt assets/icon.ico (+ icon_256.png Vorschau): türkise Sprechblase mit SUB / Textzeilen.
Aufruf: python assets/make_icon.py  (braucht Pillow, nur zur Entwicklungszeit)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEAL, TEAL_DARK, WHITE = (20, 184, 166, 255), (15, 118, 110, 255), (255, 255, 255, 255)
HERE = Path(__file__).parent


def bubble(size: int) -> Image.Image:
    s = 8  # supersampling
    w = size * s
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = int(w * 0.04)
    body_h = int(w * 0.78)
    r = int(w * 0.16)
    d.rounded_rectangle([m, m, w - m, body_h], radius=r, fill=TEAL,
                        outline=TEAL_DARK, width=max(1, w // 64))
    # Sprechblasen-Zipfel unten links
    d.polygon([(int(w * 0.22), body_h - w // 40), (int(w * 0.42), body_h - w // 40),
               (int(w * 0.26), int(w * 0.97))], fill=TEAL, outline=TEAL_DARK)
    d.polygon([(int(w * 0.23), body_h - w // 20), (int(w * 0.41), body_h - w // 20),
               (int(w * 0.26), int(w * 0.94))], fill=TEAL)

    def dash_line(y, segs):
        h = int(w * 0.075)
        x = int(w * 0.16)
        for frac in segs:
            ln = int(w * frac)
            d.rounded_rectangle([x, y, x + ln, y + h], radius=h // 2, fill=WHITE)
            x += ln + int(w * 0.07)

    if size >= 32:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", int(w * 0.34))
        except OSError:
            font = ImageFont.load_default()
        bb = d.textbbox((0, 0), "SUB", font=font)
        d.text(((w - bb[2] + bb[0]) / 2 - bb[0], int(w * 0.13)), "SUB", font=font, fill=WHITE)
        dash_line(int(w * 0.56), [0.30, 0.14, 0.18])
    else:
        dash_line(int(w * 0.20), [0.36, 0.24])
        dash_line(int(w * 0.42), [0.20, 0.14, 0.22])
    return img.resize((size, size), Image.LANCZOS)


sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = {n: bubble(n) for n in sizes}
imgs[256].save(HERE / "icon_256.png")
imgs[256].save(HERE / "icon.ico", format="ICO",
               append_images=[imgs[n] for n in sizes[:-1]],
               sizes=[(n, n) for n in sizes])
print("icon.ico + icon_256.png geschrieben")
