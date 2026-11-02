"""Building 01 (bombed-out concrete frame, ref/building1_ref_small.png) - M1 structure blockout.

usage: /opt/bpyenv/bin/python tools/build_building01.py
Writes out/building01/work/building01.blend, building01.fbx/.glb (blockout), m1_stats.json, and prints per-part tris.
1 Blender unit = 1 stud. x = along the facade (left column line x=0), y = depth (front column line y=0, front faces
-y), z = up, ground at z=0.

How it is modelled: every straight piece (columns, slabs, infill walls, standing top wall, room frame, stub) is a box
on one labelled, non-uniform 3D grid. Openings are boxes cut out of the grid. Faces are emitted only between a filled
cell and an empty cell, so faces hidden between two parts (wall end against a column, wall top under a slab) and
ground-contact faces never exist, and two parts can never have coplanar overlapping faces. Each part is then planar
dissolved and triangulated. Tilted pieces (fallen slabs) and the blockout rubble berm are separate small meshes.
"""
import json
import math
import os
import sys

import numpy as np

import bpy  # noqa: I001 (bmesh is only importable after bpy in the wheel)
import bmesh
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "building01")

# ---------------------------------------------------------------- config (all sizes in studs)
C = dict(
    floor_h=14.0,            # floor-to-floor (reference proportions; BRIEF default was 12)
    slab_t=1.0,
    ground_slab_t=0.5,
    col=1.6,                 # column section
    bays_x=[17.0, 14.0, 14.0, 11.0],  # front bays left->right (ref: right bay narrower)
    bays_y=[14.0, 14.0],     # depth bays
    over_front=0.8,          # slab past column face, front
    over_left=4.0,           # left balcony overhang past the left column face
    over_other=0.3,          # right / back
    wall_t=0.8,
    top_wall_top=44.0,       # standing wall top above ground
    corner_col_top=39.0,     # top-left corner column stump (rebar goes here in M2)
    room_frame_top=38.0,     # top-right room frame lintel top
    stub_top=32.5,           # far-right wall stub
)
PARTS = ["frame", "walls", "slabs_broken", "rubble", "debris", "rebar"]
GREY = {"frame": 0.50, "walls": 0.58, "slabs_broken": 0.45, "rubble": 0.40}

c = C
h = c["col"] / 2
XL = [0.0]
for b in c["bays_x"]:
    XL.append(XL[-1] + b)
YL = [0.0]
for b in c["bays_y"]:
    YL.append(YL[-1] + b)
W, D = XL[-1], YL[-1]
FH, ST = c["floor_h"], c["slab_t"]
L1, L2 = FH, 2 * FH  # slab tops
G = c["ground_slab_t"]
wt = c["wall_t"] / 2

ops = []  # ("add", part, box) / ("cut", None, box); later ops win


def add(part, x0, x1, y0, y1, z0, z1):
    ops.append(("add", part, (x0, x1, y0, y1, z0, z1)))


def cut(x0, x1, y0, y1, z0, z1):
    ops.append(("cut", None, (x0, x1, y0, y1, z0, z1)))


def bay_u(i):
    """clear span of front bay i (between column faces)"""
    return XL[i] + h, XL[i + 1] - h


def depth_u(j):
    return YL[j] + h, YL[j + 1] - h


# ---------------------------------------------------------------- infill walls (storeys 0 and 1)
storeys = [(G, L1 - ST), (L1, L2 - ST)]
for (z0, z1) in storeys:
    add("walls", -h, W + h, -wt, wt, z0, z1)          # front
    add("walls", -h, W + h, D - wt, D + wt, z0, z1)   # back
    add("walls", -wt, wt, -h, D + h, z0, z1)          # left side
    add("walls", W - wt, W + wt, -h, D + h, z0, z1)   # right side

# front openings: (storey, bay, u0, u1, v0, v1) in bay-local studs from the left column face / floor top
FRONT_HOLES = [
    (0, 0, 3.0, 99, 0.0, 9.5), (0, 0, 8.0, 99, 9.5, 99),        # ground bay 0: left chunk + top-left band left
    (0, 1, 0.0, 9.5, 0.0, 99), (0, 1, 9.5, 99, 0.0, 8.5),       # ground bay 1: small top-right chunk left
    (0, 2, 2.0, 99, 0.0, 99),                                    # ground bay 2: left chunk only
    (0, 3, 2.0, 7.5, 0.0, 9.0),                                  # ground bay 3: door-like opening
    (1, 0, 4.0, 99, 0.0, 9.0),                                   # storey 1 bay 0: left chunk + top band
    (1, 1, 0.0, 99, 0.0, 11.0),                                  # storey 1 bay 1: thin top band left
    (1, 2, 1.2, 11.2, 1.5, 11.5),                                # storey 1 bay 2: sill + jambs left
    (1, 3, 2.5, 6.0, 4.0, 9.0),                                  # storey 1 bay 3: mostly intact, window hole
]
# back openings where the reference shows sky through the building
BACK_HOLES = [
    (1, 0, 3.0, 13.0, 2.5, 11.0),
    (1, 2, 2.5, 9.0, 3.0, 11.0),
    (0, 1, 5.5, 8.0, 4.0, 6.5),
]
SIDE_HOLES = [  # (storey, side 'L'/'R', depth bay, u0, u1, v0, v1)
    ("L", 0, 0, 2.0, 99, 0.0, 99), ("L", 1, 0, 0.0, 99, 0.0, 10.0), ("L", 1, 1, 3.0, 10.0, 3.0, 10.0),
    ("R", 0, 1, 4.0, 9.0, 0.0, 8.5), ("R", 1, 0, 3.0, 9.0, 3.0, 9.5),
]


def bay_hole(s, i, u0, u1, v0, v1, y0, y1):
    a, b = bay_u(i)
    z0, z1 = storeys[s]
    cut(a + u0, min(b, a + u1), y0, y1, z0 + v0, min(z1, z0 + v1))


for (s, i, *r) in FRONT_HOLES:
    bay_hole(s, i, *r, -wt - 0.1, wt + 0.1)
for (s, i, *r) in BACK_HOLES:
    bay_hole(s, i, *r, D - wt - 0.1, D + wt + 0.1)
for (side, s, j, u0, u1, v0, v1) in SIDE_HOLES:
    a, b = depth_u(j)
    z0, z1 = storeys[s]
    x = 0.0 if side == "L" else W
    cut(x - wt - 0.1, x + wt + 0.1, a + u0, min(b, a + u1), z0 + v0, min(z1, z0 + v1))

# ---------------------------------------------------------------- standing pieces on the destroyed 3rd level
sw0, sw1 = XL[1] - 2.5, XL[2] + h      # standing wall left of centre (ref: just left of column line 1 to line 2)
add("walls", sw0, sw1, -wt, wt, L2, c["top_wall_top"])
cut(sw0, sw0 + 4.5, -1, 1, c["top_wall_top"] - 2.5, 99)  # stepped broken top
cut(sw0, sw0 + 1.5, -1, 1, L2 + 9.0, 99)                 # ragged left edge
cut(sw1 - 3.0, sw1 - 0.6, -1, 1, L2 + 5.5, L2 + 9.5)     # big hole, upper right
for (u, v, s) in [(3.5, 6.5, 1.1), (7.0, 11.0, 1.2), (10.5, 3.5, 1.0), (6.0, 2.0, 0.9)]:
    cut(sw0 + u, sw0 + u + s, -1, 1, L2 + v, L2 + v + s)  # small shell holes
# top-right room frame: mid column + column on line 3 + lintel
rf_mid = XL[3] - 7.0
add("frame", rf_mid - h, rf_mid + h, -h, h, L2, c["room_frame_top"] - 2.0)
add("frame", XL[3] - h, XL[3] + h, -h, h, L2, c["room_frame_top"] - 2.0)
add("frame", XL[2] + h, XL[3] + h, -h, h, c["room_frame_top"] - 2.0, c["room_frame_top"])
add("frame", XL[3] - h, XL[3] + h, h, 7.0, c["room_frame_top"] - 1.6, c["room_frame_top"])  # side beam stub
# far-right wall stub + short column
add("walls", XL[3] + h, W - h, -wt, wt, L2, c["stub_top"])
cut(XL[3] + h + 6.0, W - h, -1, 1, c["stub_top"] - 1.5, 99)
add("frame", W - h, W + h, -h, h, L2, c["stub_top"] + 0.5)
# top-left corner column stump
add("frame", -h, h, -h, h, L2, c["corner_col_top"])
add("walls", h, 4.0, -wt, wt, L2, c["corner_col_top"] - 2.0)  # wall chunk beside it (ref: ~4.5 wide)
cut(2.6, 4.1, -1, 1, c["corner_col_top"] - 5.0, 99)  # broken step

# ---------------------------------------------------------------- frame: columns + slabs (added last, wins)
for x in XL:
    for y in YL:
        add("frame", x - h, x + h, y - h, y + h, 0.0, L2)
add("frame", -h, W + h, -h, D + h, 0.0, G)  # ground slab (bottom face on the ground is not emitted)
for zt in (L1, L2):
    add("frame", -h - c["over_left"], W + h + c["over_other"], -h - c["over_front"], D + h + c["over_other"],
        zt - ST, zt)
# broken-off roof slab: the 3rd level slab is gone behind the standing pieces only at the back-left (blockout)
cut(-10, XL[1] - h, YL[1] + h, D + 10, L2 - ST - 0.01, L2 + 0.01)


# ---------------------------------------------------------------- grid
def grid_label():
    pid = {p: i + 1 for i, p in enumerate(PARTS)}
    coords = [set(), set(), set()]
    for (_, _, b) in ops:
        for a in range(3):
            coords[a].add(round(b[2 * a], 4))
            coords[a].add(round(b[2 * a + 1], 4))
    xs, ys, zs = [np.array(sorted(s)) for s in coords]
    lab = np.zeros((len(xs) - 1, len(ys) - 1, len(zs) - 1), np.int8)
    cx, cy, cz = [(v[:-1] + v[1:]) / 2 for v in (xs, ys, zs)]
    for (kind, part, b) in ops:
        mx = (cx > b[0]) & (cx < b[1])
        my = (cy > b[2]) & (cy < b[3])
        mz = (cz > b[4]) & (cz < b[5])
        m = mx[:, None, None] & my[None, :, None] & mz[None, None, :]
        lab[m] = 0 if kind == "cut" else pid[part]
    return lab, xs, ys, zs, pid


def emit_faces(lab, xs, ys, zs):
    """{part_id: [quad of grid-index triples]} for faces between a filled and an empty cell."""
    P = np.pad(lab, 1)
    out = {}
    for ax in range(3):
        sl_a = [slice(1, -1)] * 3
        sl_b = [slice(1, -1)] * 3
        sl_a[ax] = slice(0, -1)
        sl_b[ax] = slice(1, None)
        A, B = P[tuple(sl_a)], P[tuple(sl_b)]
        for sign, own, other in ((1, A, B), (-1, B, A)):
            idx = np.argwhere((own != 0) & (other == 0))
            for (i, j, k) in idx:
                if ax == 2 and k == 0 and sign == -1:
                    continue  # face on the ground
                part = int(own[i, j, k])
                if ax == 0:
                    q = [(i, j, k), (i, j + 1, k), (i, j + 1, k + 1), (i, j, k + 1)]
                elif ax == 1:
                    q = [(i, j, k), (i, j, k + 1), (i + 1, j, k + 1), (i + 1, j, k)]
                else:
                    q = [(i, j, k), (i + 1, j, k), (i + 1, j + 1, k), (i, j + 1, k)]
                if sign == -1:
                    q = q[::-1]
                out.setdefault(part, []).append((ax, q))
    return out


def part_mesh(name, quads, xs, ys, zs):
    bm = bmesh.new()
    vmap = {}

    def V(t):
        if t not in vmap:
            vmap[t] = bm.verts.new((float(xs[t[0]]), float(ys[t[1]]), float(zs[t[2]])))
        return vmap[t]

    for (ax, q) in quads:
        bm.faces.new([V(t) for t in q])
    return bm


def finish(bm, name, grey):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=list(bm.verts), edges=list(bm.edges))
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(f"{name}_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (grey, grey * 0.98, grey * 0.94, 1)
    bsdf.inputs["Roughness"].default_value = 0.95
    me.materials.append(mat)
    return ob


def box_into(bm, size, center, rot_deg):
    sx, sy, sz = size
    R = (Matrix.Rotation(math.radians(rot_deg[2]), 4, "Z") @ Matrix.Rotation(math.radians(rot_deg[1]), 4, "Y")
         @ Matrix.Rotation(math.radians(rot_deg[0]), 4, "X"))
    vs = []
    for z in (-sz / 2, sz / 2):
        for (x, y) in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
            vs.append(bm.verts.new(Vector(center) + (R @ Vector((x, y, z)))))
    f = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    for t in f:
        bm.faces.new([vs[i] for i in t])


def loft(bm, xs_, prof_fn, axis="x"):
    """Rubble berm: cross-section prof_fn(s) -> [(d, z), ...] (open bottom), lofted along s; ends capped."""
    rings = []
    for s in xs_:
        ring = []
        for (d, z) in prof_fn(s):
            p = (s, d, z) if axis == "x" else (d, s, z)
            ring.append(bm.verts.new(p))
        rings.append(ring)
    flip = axis != "x"
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(len(a) - 1):
            q = [a[i], b[i], b[i + 1], a[i + 1]]
            bm.faces.new(q[::-1] if flip else q)
    bm.faces.new(rings[0][::-1] if not flip else rings[0])
    bm.faces.new(rings[-1] if not flip else rings[-1][::-1])


def berm_height(s, pts):
    return float(np.interp(s, [p[0] for p in pts], [p[1] for p in pts]))


def main():
    os.makedirs(os.path.join(OUT, "work"), exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    lab, xs, ys, zs, pid = grid_label()
    faces = emit_faces(lab, xs, ys, zs)
    obs = {}
    for part, n in pid.items():
        if n in faces:
            obs[part] = finish(part_mesh(part, faces[n], xs, ys, zs), part, GREY.get(part, 0.5))

    # fallen slab pieces (tilted, so never coplanar with the frame)
    bm = bmesh.new()
    a, b = bay_u(0)
    box_into(bm, (11.0, 6.5, 0.8), ((a + b) / 2 + 0.5, 4.5, L1 + 2.2), (14.0, -16.0, 6.0))  # storey 1 bay 0, leaning
    box_into(bm, (10.0, 6.0, 0.8), ((a + b) / 2, 5.5, G + 2.2), (-10.0, 20.0, -8.0))       # ground bay 0, collapsed
    obs["slabs_broken"] = finish(bm, "slabs_broken", GREY["slabs_broken"])

    # blockout rubble berm (front, higher at the left; low side berms). Replaced by real rubble in M2.
    bm = bmesh.new()
    front = [(-c["over_left"] - 6, 0.4), (-4, 4.5), (6, 5.0), (16, 3.2), (30, 2.4), (44, 2.8), (W + 1, 3.0),
             (W + 4, 0.4)]
    sx = np.linspace(front[0][0], front[-1][0], 14)
    loft(bm, sx, lambda s: [(-2.0 - 2.4 * berm_height(s, front), 0.0),
                           (-2.0 - 0.5 * berm_height(s, front), berm_height(s, front)),
                           (-0.9, 0.8 * berm_height(s, front)), (3.0, 0.0)], "x")
    obs["rubble"] = finish(bm, "rubble", GREY["rubble"])

    # ---------------------------------------------------------- checks
    tris = {k: len(o.data.polygons) for k, o in obs.items()}
    total = sum(tris.values())
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in obs.values():
        for v in o.data.vertices:
            lo = Vector(map(min, lo, v.co))
            hi = Vector(map(max, hi, v.co))

    def free(b):
        cx, cy, cz = [(v[:-1] + v[1:]) / 2 for v in (xs, ys, zs)]
        ix = (xs[1:] > b[0]) & (xs[:-1] < b[1])
        iy = (ys[1:] > b[2]) & (ys[:-1] < b[3])
        iz = (zs[1:] > b[4]) & (zs[:-1] < b[5])
        return not lab[np.ix_(ix, iy, iz)].any()

    def solid_under(x, y, z):
        i = np.searchsorted(xs, x) - 1
        j = np.searchsorted(ys, y) - 1
        k = np.searchsorted(zs, z - 0.05) - 1
        return lab[i, j, k] == pid["frame"]

    av = []
    # walk through each ground-floor front bay that is open at walking height (avatar 2 wide, 5.5 tall, 1 deep)
    for i in range(4):
        a, b = bay_u(i)
        ok = any(free((x - 1, x + 1, -3, 3, G + 0.01, G + 5.5)) for x in np.arange(a + 1, b - 1, 0.5))
        av.append(("walk through ground bay %d" % i, bool(ok)))
    for name, z in (("stand on ground slab", G), ("stand on level-1 slab", L1), ("stand on level-2 slab", L2)):
        a, b = bay_u(1)
        x, y = (a + b) / 2, YL[1] / 2
        ok = free((x - 1, x + 1, y - 0.5, y + 0.5, z + 0.01, z + 5.5)) and solid_under(x, y, z)
        av.append((name + " (bay 1, x=%.1f y=%.1f z=%.1f)" % (x, y, z), bool(ok)))

    nonman = 0
    for o in obs.values():
        bm = bmesh.new()
        bm.from_mesh(o.data)
        nonman += sum(1 for e in bm.edges if len(e.link_faces) > 2)
        bm.free()
    stats = dict(tris=tris, total=total, bounds_min=list(lo), bounds_max=list(hi), avatar=av,
                 nonmanifold_edges=nonman, config=C)
    with open(os.path.join(OUT, "m1_stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    for k, v in tris.items():
        print(f"  {k:14s} {v:6d} tris")
    print(f"  TOTAL {total} tris; bounds {tuple(round(v, 2) for v in lo)} .. {tuple(round(v, 2) for v in hi)}")
    for n, ok in av:
        print(f"  avatar: {n}: {'OK' if ok else 'FAIL'}")

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "work", "building01.blend"))
    # blockout export: raw FBX numbers = studs (global_scale 0.01 x apply_unit_scale 100), GLB in BU
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "building01.fbx"), global_scale=0.01, apply_unit_scale=True,
                             object_types={"MESH"}, mesh_smooth_type="FACE", axis_forward="-Z", axis_up="Y")
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "building01.glb"), export_format="GLB")
    if total > 18000:
        sys.exit("FAIL: total tris > 18000")


if __name__ == "__main__":
    main()
