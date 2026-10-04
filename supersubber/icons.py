"""Runde Status-Symbole für Verlauf und Statuszeile: grüner Haken, gelbes Rufzeichen, rotes Kreuz.

Zur Laufzeit in der gewünschten Pixelgröße gezeichnet statt als Bilddateien ausgeliefert — so sind sie bei jeder
Schriftgröße und DPI scharf. Reines Python: Kreis und Striche über Abstände, Kanten durch 4×4-Abtastung geglättet,
als PNG mit Alphakanal an Tk übergeben.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib

GREEN, RED, YELLOW = (0x1F, 0x9D, 0x55), (0xE0, 0x3B, 0x2F), (0xF2, 0xB7, 0x05)
WHITE, DARK = (0xFF, 0xFF, 0xFF), (0x2B, 0x22, 0x00)

# Striche im Einheitsquadrat 0..1: (x0, y0, x1, y1); dazu Strichstärke und Farben je Symbol
_SHAPES = {
    "ok": (GREEN, WHITE, 0.13, [(0.27, 0.53, 0.44, 0.69), (0.44, 0.69, 0.74, 0.35)]),
    "fail": (RED, WHITE, 0.13, [(0.32, 0.32, 0.68, 0.68), (0.68, 0.32, 0.32, 0.68)]),
    "warn": (YELLOW, DARK, 0.14, [(0.5, 0.24, 0.5, 0.56), (0.5, 0.75, 0.5, 0.76)]),
}
MARKS = {"✔": "ok", "⚠": "warn", "✖": "fail"}       # Textzeichen → Symbol


def _dist(px: float, py: float, seg: tuple) -> float:
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def png(kind: str, size: int) -> bytes:
    """PNG-Daten des Symbols in size×size Pixeln, transparent außerhalb des Kreises."""
    bg, fg, stroke, segs = _SHAPES[kind]
    n = 4                                             # Abtastungen je Pixelkante
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            inside = marked = 0
            for sy in range(n):
                for sx in range(n):
                    px, py = (x + (sx + 0.5) / n) / size, (y + (sy + 0.5) / n) / size
                    if math.hypot(px - 0.5, py - 0.5) <= 0.5:
                        inside += 1
                        if any(_dist(px, py, s) <= stroke / 2 for s in segs):
                            marked += 1
            if not inside:
                raw += b"\x00\x00\x00\x00"
                continue
            f = marked / inside
            raw += bytes(round(bg[i] * (1 - f) + fg[i] * f) for i in range(3))
            raw.append(round(255 * inside / (n * n)))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def photo(kind: str, size: int):
    """tk.PhotoImage des Symbols. Der Aufrufer muss die Referenz halten, sonst räumt Tk das Bild ab."""
    import tkinter as tk
    return tk.PhotoImage(data=base64.b64encode(png(kind, size)))
