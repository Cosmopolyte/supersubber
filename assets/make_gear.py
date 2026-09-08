"""Erzeugt assets/gear.png — klassisches Zahnrad-Icon für den Einstellungen-Button.
Aufruf: python assets/make_gear.py  (braucht Pillow, nur zur Entwicklungszeit)
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

INK = (27, 58, 54, 255)
HERE = Path(__file__).parent


def gear(size: int, teeth: int = 8) -> Image.Image:
    s = 8
    w = size * s
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = w / 2
    r_out = w * 0.48      # Zahnspitzen
    r_body = w * 0.36     # Zahnfuß / Körper
    r_hole = w * 0.16
    tooth_half = math.pi / teeth * 0.42
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        pts = []
        for da, r in ((-tooth_half, r_body), (-tooth_half * 0.7, r_out),
                      (tooth_half * 0.7, r_out), (tooth_half, r_body)):
            pts.append((cx + r * math.cos(a + da), cy + r * math.sin(a + da)))
        d.polygon(pts, fill=INK)
    d.ellipse([cx - r_body, cy - r_body, cx + r_body, cy + r_body], fill=INK)
    d.ellipse([cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole], fill=(0, 0, 0, 0))
    return img.resize((size, size), Image.LANCZOS)


gear(20).save(HERE / "gear.png")
gear(64).save(HERE / "gear_preview.png")
print("gear.png geschrieben")
