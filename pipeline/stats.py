"""Measure a built creature and write out/<name>/stats.md.

usage: /opt/bpyenv/bin/python tools/stats.py <name>
Numbers come from the exported GLB and the cached low mesh / UVs, not from the build settings.
The review text and score live in the creature module (REVIEW) so they are versioned with the design.
"""
import importlib
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

STUD_M = 0.28  # Roblox avatar convention, 1 stud ~ 0.28 m


def glb_counts(path):
    with open(path, "rb") as f:
        data = f.read()
    jlen = struct.unpack("<I", data[12:16])[0]
    js = json.loads(data[20:20 + jlen])
    tris = verts = 0
    for m in js["meshes"]:
        for p in m["primitives"]:
            verts += js["accessors"][p["attributes"]["POSITION"]]["count"]
            tris += js["accessors"][p["indices"]]["count"] // 3
    imgs = len(js.get("images", []))
    try:
        import trimesh
        vol = trimesh.load(path, force="mesh").volume
    except Exception:
        vol = float("nan")
    mn = js["accessors"][js["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]["min"]
    mx = js["accessors"][js["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]["max"]
    return tris, verts, imgs, mn, mx, vol


def topo(V, F):
    nq = sum(1 for f in F if len(f) == 4)
    val = np.zeros(len(V), int)
    edges = set()
    for f in F:
        for i in range(len(f)):
            e = tuple(sorted((f[i], f[(i + 1) % len(f)])))
            edges.add(e)
    for a, b in edges:
        val[a] += 1
        val[b] += 1
    poles = int((val != 4).sum())
    # closed / manifold check: every edge used by exactly two faces
    cnt = {}
    for f in F:
        for i in range(len(f)):
            e = tuple(sorted((f[i], f[(i + 1) % len(f)])))
            cnt[e] = cnt.get(e, 0) + 1
    open_edges = sum(1 for c in cnt.values() if c != 2)
    return nq, poles, open_edges, len(edges)


def uv_metrics(V, uv, loops, ls, lt, res=1024):
    tv, tu = [], []
    for s, n in zip(ls, lt):
        for k in range(1, n - 1):
            idx = [s, s + k, s + k + 1]
            tv.append(loops[idx])
            tu.append(idx)
    tv, tu = np.array(tv), np.array(tu)
    A3all = 0.5 * np.linalg.norm(np.cross(V[tv[:, 1]] - V[tv[:, 0]], V[tv[:, 2]] - V[tv[:, 0]]), axis=1)
    degenerate = int((A3all < 1e-9).sum())
    tv, tu = tv[A3all >= 1e-9], tu[A3all >= 1e-9]
    P = V[tv]
    U = uv[tu]
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    A3 = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    f1, f2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
    Auv = 0.5 * np.abs(f1[:, 0] * f2[:, 1] - f1[:, 1] * f2[:, 0])
    # anisotropy: singular values of the 3D->UV map per triangle
    x = e1 / np.linalg.norm(e1, axis=1, keepdims=True)
    nrm = np.cross(e1, e2)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    y = np.cross(nrm, x)
    p1 = np.stack([(e1 * x).sum(1), (e1 * y).sum(1)], 1)
    p2 = np.stack([(e2 * x).sum(1), (e2 * y).sum(1)], 1)
    Pm = np.stack([p1, p2], 2)  # 2x2 local 3D edge matrix (columns)
    Um = np.stack([f1, f2], 2)
    J = Um @ np.linalg.inv(Pm)
    sv = np.linalg.svd(J, compute_uv=False)
    aniso = sv[:, 0] / np.maximum(sv[:, 1], 1e-12)
    dens = np.sqrt(Auv / np.maximum(A3, 1e-12))
    # overlap: rasterise and count texels claimed by more than one triangle
    cnt = np.zeros((res, res), np.int16)
    T = U * res - 0.5
    for t in range(len(T)):
        a, b, c = T[t]
        x0, y0 = np.floor(T[t].min(0)).astype(int)
        x1, y1 = np.ceil(T[t].max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res - 1), min(y1, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        v0, v1 = b - a, c - a
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        wx, wy = xs - a[0], ys - a[1]
        l1 = (wx * v1[1] - v1[0] * wy) / den
        l2 = (v0[0] * wy - wx * v0[1]) / den
        ins = (l1 > 1e-3) & (l2 > 1e-3) & (1 - l1 - l2 > 1e-3)
        cnt[ys[ins], xs[ins]] += 1
    overlap = int((cnt > 1).sum())
    usage = float((cnt > 0).mean())
    return aniso, dens, overlap, usage, A3, degenerate


def main(name):
    mod = importlib.import_module(f"creatures.{name}")
    nm = mod.NAME.lower()
    out = os.path.join(ROOT, "out", name)
    work = os.path.join(out, "work")
    tris, gverts, imgs, mn, mx, vol = glb_counts(os.path.join(out, f"{nm}.glb"))
    d = np.load(os.path.join(work, "final.npz"), allow_pickle=True)
    V, F = d["V"], list(d["F"])
    u = np.load(os.path.join(work, "uv.npz"))
    nq, poles, open_edges, ne = topo(V, F)
    aniso, dens, overlap, usage, A3, degenerate = uv_metrics(V, u["uv"], u["loops"], u["ls"], u["lt"])
    tex = Image.open(os.path.join(out, f"{nm}_albedo.png"))
    # texel density spread, area weighted, per island excluded: report body density spread
    lab = np.load(os.path.join(work, "labels.npy"))
    w = A3 / A3.sum()
    med = np.median(dens)
    within = float(w[(dens > med * 0.8) & (dens < med * 1.25)].sum())
    height_m = mx[1] - mn[1]  # glTF is Y up
    rv = getattr(mod, "REVIEW", {"score": "-", "notes": ["not reviewed yet"]})
    lines = [
        f"# {mod.NAME} stats",
        "",
        f"Type: {mod.TYPE}. Body plan: {mod.PLAN}.",
        "",
        "## Measured (from the exported files)",
        "",
        "| item | value |",
        "|---|---|",
        f"| triangles (GLB) | {tris:,} |",
        f"| vertices (GLB, split at UV seams) | {gverts:,} |",
        f"| vertices (mesh) | {len(V):,} |",
        f"| faces before triangulation | {len(F):,} ({100 * nq / len(F):.1f}% quads) |",
        f"| poles (valence not 4) | {poles} ({100 * poles / len(V):.1f}% of vertices) |",
        f"| open / non-manifold edges | {open_edges} |",
        f"| degenerate (zero-area) triangles | {degenerate} |",
        f"| normals | {'outward (enclosed volume ' + format(vol, '.3f') + ' m3 > 0)' if vol > 0 else 'INVERTED (volume ' + format(vol, '.3f') + ')'} |",
        f"| height | {height_m:.2f} m = {height_m / STUD_M:.1f} studs at 0.28 m/stud |",
        f"| texture | 1 x {tex.width}x{tex.height} PNG albedo, embedded in the GLB ({imgs} image) |",
        f"| UV usage | {100 * usage:.1f}% of the 0-1 square |",
        f"| UV overlap | {overlap} texels claimed twice (0 = no overlapping shells) |",
        f"| UV stretch (anisotropy, area weighted) | mean {np.average(aniso, weights=w):.2f}, 95th pct {np.percentile(aniso, 95):.2f} (1.0 = none) |",
        f"| texel density | {100 * within:.0f}% of surface within -20%/+25% of the median (face island is scaled up on purpose) |",
        "",
        "## Review",
        "",
        f"Score: **{rv['score']} / 10**",
        "",
    ] + [f"- {n}" for n in rv["notes"]] + [""]
    with open(os.path.join(out, "stats.md"), "w") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
