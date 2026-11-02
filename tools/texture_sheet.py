"""Texture sheet for the pitch: the colour maps of the main parts side by side, labelled.

usage: python tools/texture_sheet.py   (after tools/make_textures.py) -> out/building01/pitch_textures.png
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "out", "building01", "textures")
NAMES = ["frame", "walls", "frame_inner", "rubble", "debris", "rebar"]
TILE, PAD = 360, 8

sh = Image.new("RGB", (3 * TILE + 4 * PAD, 2 * (TILE + 34) + 3 * PAD), (30, 30, 30))
d = ImageDraw.Draw(sh)
for k, n in enumerate(NAMES):
    im = Image.open(os.path.join(T, f"{n}_color.png")).convert("RGB").resize((TILE, TILE))
    x, y = PAD + (k % 3) * (TILE + PAD), PAD + (k // 3) * (TILE + 34 + PAD)
    sh.paste(im, (x, y))
    d.text((x + 4, y + TILE + 8), n + ("  (1024, tiles every 10 studs)" if n in ("frame", "walls", "frame_inner") else "  (1024)"),
           fill=(230, 230, 230))
sh.save(os.path.join(ROOT, "out", "building01", "pitch_textures.png"))
