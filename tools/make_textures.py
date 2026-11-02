"""M3 textures: per-part 1024 tileable sets from the CC0 sources, tinted to the reference's dusty grey-brown.

usage: python tools/make_textures.py
Writes out/building01/textures/<part>_color.png, _normal.png (OpenGL), _roughness.png (+ _metalness for rebar).
Concrete parts get shell pitting (dark round pits with a dented normal) that tiles, since pits are a texture job.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "textures")
OUT = os.path.join(ROOT, "out", "building01", "textures")
N = 1024

# Reference, measured on the non-white pixels: lit concrete ~ (156,144,132), mid (101,92,83).
PARTS = {
    "frame": dict(src="Concrete044D", tint=(126, 119, 110), contrast=1.2, pits=70, grime=1.0, seed=1, shade=0.52),
    "walls": dict(src="Concrete036", tint=(121, 113, 103), contrast=1.3, pits=110, grime=1.2, seed=2, shade=0.5),
    "slabs_broken": dict(src="Concrete044D", tint=(118, 111, 102), contrast=1.2, pits=40, grime=1.0, seed=3, shade=0.52),
    "debris": dict(src="Concrete036", tint=(116, 109, 100), contrast=1.2, pits=15, grime=0.6, seed=4),
    "rubble": dict(src="Ground108", tint=(113, 105, 95), contrast=0.5, desat=0.85, squash=0.10, pits=0, grime=0.8, seed=5,
                   mix=("Concrete036", 0.6, 1.2)),
    # own file copies of the rubble set (one material per MeshPart, never sharing images: Import 3D rule)
    "rubble_upper": dict(src="Ground108", tint=(113, 105, 95), contrast=0.5, desat=0.85, squash=0.10, pits=0, grime=0.8,
                         seed=5, mix=("Concrete036", 0.6, 1.2)),
    "rebar": dict(src="Metal041B", tint=(92, 58, 38), contrast=1.6, desat=0.2, pits=0, seed=6, metal=0.55),
}


def load(set_name, kind):
    for f in os.listdir(os.path.join(SRC, set_name)):
        if f.endswith(f"_{kind}.jpg"):
            im = Image.open(os.path.join(SRC, set_name, f))
            return np.asarray(im.convert("RGB" if kind in ("Color", "NormalGL") else "L").resize((N, N), Image.LANCZOS),
                              np.float32) / 255.0
    return None


def tint(col, target, contrast, desat):
    lum = col @ np.array([0.299, 0.587, 0.114], np.float32)
    col = col * (1 - desat) + lum[..., None] * desat
    lum = col @ np.array([0.299, 0.587, 0.114], np.float32)
    m = lum.mean()
    detail = (col - m) * contrast
    return np.clip(np.array(target, np.float32) / 255.0 + detail, 0, 1)


def pits(count, seed):
    """Tileable shell pits: height (0 surface, -1 deepest) and a halo mask (fresh chipped concrete around each hole).
    Outlines are blobby (low harmonics, small amplitude); high harmonics made them read as stars."""
    rng = np.random.default_rng(seed)
    h = np.zeros((N, N), np.float32)
    halo = np.zeros((N, N), np.float32)
    for _ in range(count):
        r = rng.choice([7, 9, 12, 16, 22, 32], p=[0.3, 0.25, 0.2, 0.13, 0.08, 0.04]) * rng.uniform(0.8, 1.25)
        cx, cy = rng.uniform(0, N, 2)
        ax = rng.uniform(0.75, 1.3)
        x0, x1 = int(cx - 2 * r), int(cx + 2 * r) + 1
        y0, y1 = int(cy - 2 * r), int(cy + 2 * r) + 1
        ys = np.arange(y0, y1) % N
        xs = np.arange(x0, x1) % N
        dx = (np.arange(x0, x1, dtype=np.float32) - cx)[None, :] * ax
        dy = (np.arange(y0, y1, dtype=np.float32) - cy)[:, None] / ax
        th = np.arctan2(dy, dx)
        wob = 1 + sum(amp * np.sin(k * th + rng.uniform(0, 6.28)) for k, amp in ((2, 0.10), (3, 0.07), (5, 0.04)))
        d = np.sqrt(dx * dx + dy * dy) / (r * wob)
        pit = -np.clip(1 - d * d, 0, 1) ** 0.7 * min(1.0, r / 18)
        ring = np.clip(1 - np.abs(d - 1.15) / 0.35, 0, 1) * min(1.0, r / 14)
        idx = np.ix_(ys, xs)
        h[idx] = np.minimum(h[idx], pit)
        halo[idx] = np.maximum(halo[idx], ring)
    return h, halo


def fbm(seed, freqs, amps):
    """Tileable value variation: random integer-frequency cosines summed, scaled to about -1..1."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32) / N
    f = np.zeros((N, N), np.float32)
    for fr, amp in zip(freqs, amps):
        for _ in range(6):
            kx, ky = rng.integers(-fr, fr + 1, 2)
            if kx == 0 and ky == 0:
                kx = fr
            f += amp * np.cos(2 * np.pi * (kx * x + ky * y) + rng.uniform(0, 6.28))
    return f / (np.abs(f).max() + 1e-6)


def streaks(seed):
    """Vertical rain/soot streaks (v runs up the wall), tileable, 0..1."""
    rng = np.random.default_rng(seed)
    x = np.arange(N, dtype=np.float32) / N
    col = np.zeros(N, np.float32)
    for k in range(4, 40, 3):
        col += np.cos(2 * np.pi * k * x + rng.uniform(0, 6.28)) / k
    col = np.clip((col - col.mean()) / col.std(), 0, None)
    return np.clip(col[None, :] * (0.5 + 0.5 * fbm(seed + 9, (1, 2), (1.0, 0.5))), 0, 1)


def normal_from_height(h, strength):
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.stack([-gx, gy, np.ones_like(h)], -1)  # OpenGL: green up
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def blend_normals(a, b):
    # Reoriented normal mapping (both in -1..1 tangent space).
    t = a + np.array([0, 0, 1], np.float32)
    u = b * np.array([-1, -1, 1], np.float32)
    r = t * (t * u).sum(-1, keepdims=True) / t[..., 2:3] - u
    return r / np.linalg.norm(r, axis=-1, keepdims=True)


def save(arr, name, mode):
    img = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
    img.save(os.path.join(OUT, name))


def main():
    os.makedirs(OUT, exist_ok=True)
    for part, c in PARTS.items():
        col = tint(load(c["src"], "Color"), c["tint"], c["contrast"], c.get("desat", 0.35))
        if c.get("squash"):  # compress bright pebbles: they glittered in Studio's light
            m = np.array(c["tint"], np.float32) / 255.0
            col = m + np.tanh((col - m) / c["squash"]) * c["squash"]
        if c.get("mix"):  # concrete-led blend: chunks read as broken concrete, gravel stays in the gaps
            src2, w, con2 = c["mix"]
            col = col * (1 - w) + tint(load(src2, "Color"), c["tint"], con2, 0.35) * w
        nrm = load(c["src"], "NormalGL") * 2 - 1
        if c.get("mix"):
            nrm = nrm * (1 - c["mix"][1]) + (load(c["mix"][0], "NormalGL") * 2 - 1) * c["mix"][1]
            nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        rough = load(c["src"], "Roughness")
        ao = load(c["src"], "AmbientOcclusion")
        if ao is not None:
            col *= (0.55 + 0.45 * ao)[..., None]
        if c.get("grime", 0):
            col *= (1 + 0.12 * c["grime"] * fbm(c["seed"] + 20, (1, 2, 4), (1.0, 0.6, 0.3)))[..., None]
            col *= (1 - 0.16 * c["grime"] * streaks(c["seed"] + 30))[..., None]
        if c["pits"]:
            h, halo = pits(c["pits"], c["seed"])
            depth = -h
            col = np.clip(col * (1 + 0.10 * halo)[..., None], 0, 1)  # fresh chipped concrete round each hole
            col *= (1 - 0.42 * np.clip(depth * 1.3, 0, 1))[..., None]  # shadowed pit floor
            nrm = blend_normals(nrm, normal_from_height(h, 6.0))
            rough = np.clip(rough + 0.08 * depth + 0.05 * halo, 0, 1)
        save(col, f"{part}_color.png", "RGB")
        if c.get("shade"):  # interior faces (ceilings, back walls): darker, sootier, flatter
            lum = (col @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
            save((col * 0.8 + lum * 0.2) * c["shade"], f"{part}_inner_color.png", "RGB")
            # own copies: Studio's Import 3D gave no SurfaceAppearance to a material whose images another
            # material already used (2026-11-02), so every part's material has its own files
            save(nrm * 0.5 + 0.5, f"{part}_inner_normal.png", "RGB")
            save(np.clip(rough * 0.9 + 0.1, 0, 1), f"{part}_inner_roughness.png", "L")
        save(nrm * 0.5 + 0.5, f"{part}_normal.png", "RGB")
        save(np.clip(rough * 0.9 + 0.1, 0, 1), f"{part}_roughness.png", "L")
        if "metal" in c:
            save(np.full((N, N), c["metal"], np.float32), f"{part}_metalness.png", "L")
        print(part, "mean colour", (col.reshape(-1, 3).mean(0) * 255).round().astype(int))


if __name__ == "__main__":
    main()
