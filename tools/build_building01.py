"""Building 01 (bombed-out concrete frame, ref/building1_ref_small.png) - M2: damage, rubble, rebar.

usage: /opt/bpyenv/bin/python tools/build_building01.py
Writes out/building01/work/building01.blend, building01.fbx/.glb, m2_stats.json, and prints per-part tris + checks.
1 Blender unit = 1 stud. x = along the facade (left column line x=0), y = depth (front column line y=0, front faces
-y), z = up, ground at z=0.

How it is modelled (M1 base, kept): every straight piece (columns, slabs, edge beams, infill walls, standing top wall,
room frame, stub) is a box on one labelled, non-uniform 3D grid; frame is added last and wins. Each part is emitted
as a closed solid (faces between its own cells and anything else).
M2 on top: damage is cut with jagged polygon prisms (exact boolean, `CUTS`): ragged openings (the grid keeps a
shrunk rectangle so the jagged outline is all that shows), chipped slab and beam edges, broken balcony ends, the
L1 hole the hanging slab fell from, column corner chips and broken column tops (convex-hull cutters). Rubble mounds
are low-poly heightfields (jittered grid + Delaunay), rubble/debris chunks are convex hulls of jittered box corners,
rebar is 4-sided tubes along bent polylines. Then a hidden-face pass deletes every face whose points all lie inside
another solid (ray parity) or under the ground; contact faces between parts (wall ends in columns, wall tops under
slabs) go with it, so no coplanar faces are left between parts. Finally planar dissolve, triangulate, weighted normals.
"""
import json
import math
import os
import sys

import numpy as np

import bpy  # noqa: I001 (bmesh is only importable after bpy in the wheel)
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from scipy.spatial import Delaunay, cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "building01")

# ---------------------------------------------------------------- config (all sizes in studs)
C = dict(
    floor_h=14.0,            # floor-to-floor (reference proportions; BRIEF default was 12)
    slab_t=1.0,
    ground_slab_t=0.5,
    col=1.9,                 # column section (M1 review fix 3; M1 was 1.6)
    bays_x=[17.0, 14.0, 14.0, 11.0],  # front bays left->right (ref: right bay narrower)
    bays_y=[14.0, 14.0],     # depth bays
    over_front=0.8,          # slab past column face, front
    over_left=4.0,           # left balcony overhang past the left column face
    over_other=0.3,          # right / back
    beam_d=2.2,              # edge band depth incl. slab (M1 review fix 1): 1.2 downstand under the 1.0 slab
    beam_w=1.4,              # left balcony edge beam width
    wall_t=0.8,
    top_wall_top=44.0,       # standing wall top above ground
    top_wall_left=4.5,       # standing wall starts this far left of column line 1 (review fix 2: ~1.4 bays wide)
    corner_col_top=39.0,     # top-left corner column stump
    room_frame_top=38.0,     # top-right room frame lintel top
    stub_top=32.5,           # far-right wall stub
    seed=11,
)
PARTS = ["frame", "walls", "slabs_broken", "rubble", "debris", "rebar"]
GREY = {"frame": 0.50, "walls": 0.58, "slabs_broken": 0.45, "rubble": 0.40, "debris": 0.47, "rebar": 0.22}
BUDGET = {"frame": 7000, "walls": 7000, "slabs_broken": 3000, "rubble": 9000, "debris": 3000, "rebar": 1000}

c = C
rng = np.random.default_rng(c["seed"])
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
YF = -h - c["over_front"]      # front slab edge
XLB = -h - c["over_left"]      # left balcony edge
BIG = 1e4

ops = []  # ("add", part, box) / ("cut", None, box); later ops win
CUTS = {"frame": [], "walls": []}  # ("prism", poly, plane, d0, d1) / ("hull", points)


def add(part, x0, x1, y0, y1, z0, z1):
    ops.append(("add", part, (x0, x1, y0, y1, z0, z1)))


def cut(x0, x1, y0, y1, z0, z1):
    ops.append(("cut", None, (x0, x1, y0, y1, z0, z1)))


def cutp(part, poly, pl, d0, d1):
    CUTS[part].append(("prism", [tuple(p) for p in poly], pl, d0, d1))


def bay_u(i):
    """clear span of front bay i (between column faces)"""
    return XL[i] + h, XL[i + 1] - h


def depth_u(j):
    return YL[j] + h, YL[j + 1] - h


# ---------------------------------------------------------------- jagged outlines (2D)
AMP, STEP = 0.45, 1.3


def jag_line(p0, p1, amp, step):
    """points strictly between p0 and p1, offset sideways by +-amp (flat broken facets, not noise)"""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    n = max(1, int(round(L / step)))
    nrm = np.array([-d[1], d[0]]) / L
    return [tuple(p0 + (k + rng.uniform(-0.25, 0.25)) / n * d + nrm * rng.uniform(-amp, amp)) for k in range(1, n)]


def jag_rect(u0, u1, v0, v1, lo_u=-BIG, hi_u=BIG, lo_v=-BIG, hi_v=BIG, amp=AMP, step=STEP, ext=0.6):
    """jagged polygon for the rect (u0..u1, v0..v1) inside a panel (lo..hi): sides on the panel border are pushed out
    by ext and stay straight (they run inside the column / slab), the others are jagged. Returns poly, keep flags
    [bottom, right, top, left]."""
    kL, kR, kB, kT = u0 <= lo_u + 0.01, u1 >= hi_u - 0.01, v0 <= lo_v + 0.01, v1 >= hi_v - 0.01
    U0, U1 = (lo_u - ext if kL else u0), (hi_u + ext if kR else u1)
    V0, V1 = (lo_v - ext if kB else v0), (hi_v + ext if kT else v1)
    cs = [(U0, V0), (U1, V0), (U1, V1), (U0, V1)]
    keep = [kB, kR, kT, kL]
    pts = []
    for i in range(4):
        a, b = cs[i], cs[(i + 1) % 4]
        if not keep[i - 1] and not keep[i]:
            pts.append((a[0] + rng.uniform(-amp, amp), a[1] + rng.uniform(-amp, amp)))
        else:
            pts.append(a)
        if not keep[i]:
            pts += jag_line(a, b, amp, step)
    return pts, keep


def wall_hole(pl, lo_u, hi_u, lo_v, hi_v, u0, u1, v0, v1, d):
    """ragged opening: the grid gets the rect shrunk on its jagged sides, the jagged prism goes to CUTS['walls']"""
    poly, keep = jag_rect(u0, u1, v0, v1, lo_u, hi_u, lo_v, hi_v)
    s = AMP + 0.15
    g0, g1 = (u0 if keep[3] else u0 + s), (u1 if keep[1] else u1 - s)
    g2, g3 = (v0 if keep[0] else v0 + s), (v1 if keep[2] else v1 - s)
    if g1 - g0 > 0.3 and g3 - g2 > 0.3:
        if pl == "y":
            cut(g0, g1, d - wt - 0.1, d + wt + 0.1, g2, g3)
        else:
            cut(d - wt - 0.1, d + wt + 0.1, g0, g1, g2, g3)
    cutp("walls", poly, pl, d - wt - 0.3, d + wt + 0.3)


# ---------------------------------------------------------------- infill walls (storeys 0 and 1)
storeys = [(G, L1 - ST), (L1, L2 - ST)]
for (z0, z1) in storeys:
    add("walls", -h, W + h, -wt, wt, z0, z1)          # front
    add("walls", -h, W + h, D - wt, D + wt, z0, z1)   # back
    add("walls", -wt, wt, -h, D + h, z0, z1)          # left side
    add("walls", W - wt, W + wt, -h, D + h, z0, z1)   # right side

# front openings: (storey, bay, u0, u1, v0, v1) in bay-local studs from the left column face / floor top
# (M2: two tops lowered 1 stud so a solid band stays under the new front edge beam)
FRONT_HOLES = [
    (0, 0, 3.0, 99, 0.0, 9.5), (0, 0, 8.0, 99, 9.5, 99),        # ground bay 0: left chunk + top-left band left
    (0, 1, 0.0, 9.5, 0.0, 99), (0, 1, 9.5, 99, 0.0, 8.5),       # ground bay 1: small top-right chunk left
    (0, 2, 2.0, 99, 0.0, 99),                                    # ground bay 2: left chunk only
    (0, 3, 2.0, 7.5, 0.0, 9.0),                                  # ground bay 3: door-like opening
    (1, 0, 4.0, 99, 0.0, 9.0),                                   # storey 1 bay 0: left chunk + top band
    (1, 1, 0.0, 99, 0.0, 10.0),                                  # storey 1 bay 1: top band left
    (1, 2, 1.2, 11.2, 1.5, 10.0),                                # storey 1 bay 2: sill + jambs left
    (1, 3, 2.5, 6.0, 4.0, 9.0),                                  # storey 1 bay 3: mostly intact, window hole
]
# back openings where the reference shows sky through the building
BACK_HOLES = [
    (1, 0, 3.0, 13.0, 2.5, 11.0),
    (1, 2, 2.5, 9.0, 3.0, 11.0),
    (0, 1, 5.5, 8.0, 4.0, 6.5),
]
SIDE_HOLES = [  # (side 'L'/'R', storey, depth bay, u0, u1, v0, v1)
    ("L", 0, 0, 2.0, 99, 0.0, 99), ("L", 1, 0, 0.0, 99, 0.0, 10.0), ("L", 1, 1, 3.0, 10.0, 3.0, 10.0),
    ("R", 0, 1, 4.0, 9.0, 0.0, 8.5), ("R", 1, 0, 3.0, 9.0, 3.0, 9.5),
]


def bay_hole(s, i, u0, u1, v0, v1, d):
    a, b = bay_u(i)
    z0, z1 = storeys[s]
    wall_hole("y", a, b, z0, z1, a + u0, min(b, a + u1), z0 + v0, min(z1, z0 + v1), d)


for (s, i, *r) in FRONT_HOLES:
    bay_hole(s, i, *r, 0.0)
for (s, i, *r) in BACK_HOLES:
    bay_hole(s, i, *r, D)
for (side, s, j, u0, u1, v0, v1) in SIDE_HOLES:
    a, b = depth_u(j)
    z0, z1 = storeys[s]
    wall_hole("x", a, b, z0, z1, a + u0, min(b, a + u1), z0 + v0, min(z1, z0 + v1), 0.0 if side == "L" else W)

# walls under the missing roof corner (back-left): broken tops, kept below the broken column top at (0, D)
cutp("walls", [(YL[1] + 0.3, L2 + 2), (YL[1] + 0.3, L2 - 2.4)] + jag_line((YL[1] + 0.3, L2 - 2.4), (D + 1.6, L2 - 5.4),
                                                                        0.5, 1.6) + [(D + 1.6, L2 - 5.4), (D + 1.6, L2 + 2)],
     "x", -wt - 0.2, wt + 0.2)
cutp("walls", [(0.3, L2 + 2), (0.3, L2 - 5.0)] + jag_line((0.3, L2 - 5.0), (XL[1] - 0.4, L2 - 2.8), 0.5, 1.6)
     + [(XL[1] - 0.4, L2 - 2.8), (XL[1] - 0.4, L2 + 2)], "y", D - wt - 0.2, D + wt + 0.2)

# ---------------------------------------------------------------- standing pieces on the destroyed 3rd level
T = c["top_wall_top"]
sw0, sw1 = XL[1] - c["top_wall_left"], XL[2] + h + 0.5   # left of centre, ~1.4 bays; 0.5 into the lintel
add("walls", sw0, sw1, -wt, wt, L2, T)
prof = [(sw0 - 0.6, T - 3.6)]
prof += [(x, T - 3.0 - rng.uniform(0, 1.0)) for x in np.linspace(sw0 + 0.7, sw0 + 3.8, 3)]
prof += [(sw0 + 4.3, T - 2.6), (sw0 + 4.6, T - rng.uniform(0.3, 0.8))]
prof += [(x, T - rng.uniform(0.15, 1.2)) for x in np.linspace(sw0 + 5.6, sw1 - 0.6, 12)]
prof += [(sw1 + 0.6, T - 0.6)]
cutp("walls", [(sw0 - 0.6, T + 3)] + prof + [(sw1 + 0.6, T + 3)], "y", -1.0, 1.0)  # jagged broken top
le = [(sw0 - 1.0, L2 + 0.8), (sw0 + 0.25, L2 + 1.2)] + jag_line((sw0 + 0.25, L2 + 1.2), (sw0 + 0.5, L2 + 8.0), 0.3, 1.4)
le += [(sw0 + 0.5, L2 + 8.0), (sw0 + 1.9, L2 + 8.6)] + jag_line((sw0 + 1.9, L2 + 8.6), (sw0 + 1.7, T - 2), 0.35, 1.3)
le += [(sw0 + 1.7, T - 2), (sw0 + 1.7, T + 3), (sw0 - 1.0, T + 3)]
cutp("walls", le, "y", -1.0, 1.0)                                                    # ragged left edge
BIG_HOLES = [(sw1 - 3.8, sw1 - 0.9, L2 + 5.0, L2 + 10.0), (sw0 + 6.5, sw0 + 9.6, L2 + 1.6, L2 + 4.4)]
for (u0, u1, v0, v1) in BIG_HOLES:
    cutp("walls", jag_rect(u0, u1, v0, v1, amp=0.5, step=1.0)[0], "y", -1.0, 1.0)
shell = []
for _ in range(600):
    if len(shell) >= 13:
        break
    x, z, r = rng.uniform(sw0 + 2.6, sw1 - 1.3), rng.uniform(L2 + 1.3, T - 2.6), rng.uniform(0.32, 0.7)
    if any(math.hypot(x - a, z - b) < r + q + 0.8 for (a, b, q) in shell):
        continue
    if any(u0 - 0.9 < x < u1 + 0.9 and v0 - 0.9 < z < v1 + 0.9 for (u0, u1, v0, v1) in BIG_HOLES):
        continue
    shell.append((x, z, r))
for k, (x, z, r) in enumerate(shell):
    n, ph = int(rng.integers(5, 8)), rng.uniform(0, 6.3)
    poly = [(x + r * rng.uniform(0.75, 1.2) * math.cos(ph + 2 * math.pi * j / n),
             z + r * rng.uniform(0.75, 1.2) * math.sin(ph + 2 * math.pi * j / n)) for j in range(n)]
    cutp("walls", poly, "y", -1.0, 0.0 if k % 3 == 0 else 1.0)  # every 3rd one is a blind pit (half the wall)
# top-right room frame: mid column + column on line 3 + lintel
rf_mid = XL[3] - 7.0
add("frame", rf_mid - h, rf_mid + h, -h, h, L2, c["room_frame_top"] - 2.0)
add("frame", XL[3] - h, XL[3] + h, -h, h, L2, c["room_frame_top"] - 2.0)
add("frame", XL[2] + h, XL[3] + h, -h, h, c["room_frame_top"] - 2.0, c["room_frame_top"])
add("frame", XL[3] - h, XL[3] + h, h, 7.0, c["room_frame_top"] - 1.6, c["room_frame_top"])  # side beam stub
# far-right wall stub + short column
st = c["stub_top"]
add("walls", XL[3] + h, W - h, -wt, wt, L2, st)
sp = [(XL[3] + h - 0.6, st - 0.3)] + jag_line((XL[3] + h - 0.6, st - 0.3), (XL[3] + h + 5.6, st - 0.5), 0.3, 1.2)
sp += [(XL[3] + h + 5.6, st - 0.5), (XL[3] + h + 6.3, st - 1.9)] + jag_line((XL[3] + h + 6.3, st - 1.9),
                                                                             (W - h + 0.6, st - 2.4), 0.3, 1.2)
sp += [(W - h + 0.6, st - 2.4), (W - h + 0.6, st + 3), (XL[3] + h - 0.6, st + 3)]
cutp("walls", sp, "y", -1.0, 1.0)
add("frame", W - h, W + h, -h, h, L2, st + 0.5)
# top-left corner column stump + wall chunk beside it (ref: ~4.5 wide), jagged stepped top
cct = c["corner_col_top"]
add("frame", -h, h, -h, h, L2, cct)
add("walls", h, 4.0, -wt, wt, L2, cct - 2.0)
cutp("walls", [(h - 0.6, cct + 3), (h - 0.6, cct - 2.3), (1.8, cct - 2.0 - rng.uniform(0.3, 0.9)), (2.4, cct - 3.4),
               (2.9, cct - 4.9), (3.6, cct - 5.3), (4.6, cct - 5.1), (4.6, cct + 3)], "y", -1.0, 1.0)

# ---------------------------------------------------------------- frame: columns + slabs + edge beams (wins)
for x in XL:
    for y in YL:
        add("frame", x - h, x + h, y - h, y + h, 0.0, L2)
add("frame", -h, W + h, -h, D + h, 0.0, G)  # ground slab
for zt in (L1, L2):
    add("frame", XLB, W + h + c["over_other"], YF, D + h + c["over_other"], zt - ST, zt)
    # edge beams (review fix 1): thick band under the slab edge, front + left balcony; the front one reaches 0.2
    # into the infill wall so the wall top steps behind it (no coplanar contact)
    add("frame", XLB, W + h + c["over_other"], YF, -wt + 0.2, zt - c["beam_d"], zt - ST)
    add("frame", XLB, XLB + c["beam_w"], YF, D + h + c["over_other"], zt - c["beam_d"], zt - ST)

# ---------------------------------------------------------------- frame damage (jagged cutters)
# roof slab (+ its edge beam) gone at the back-left behind the standing pieces (M1 rect -> jagged)
cutp("frame", jag_rect(-12, XL[1] - h, YL[1] + h, D + 5, -12, BIG, -BIG, D + 5, amp=0.7, step=1.6)[0], "z",
     L2 - c["beam_d"] - 0.2, L2 + 0.3)
for zt in (L1, L2):
    zb = zt - c["beam_d"] - 0.2
    # broken balcony end at the front-left corner
    bx, by = rng.uniform(1.8, 3.2), rng.uniform(1.6, 2.6)
    cutp("frame", jag_rect(-10, XLB + bx, -6, YF + by, -10, BIG, -6, BIG, amp=0.5, step=1.0)[0], "z", zb, zt + 0.3)
    # chipped notches in plan along the front edge and the balcony edge
    for x in rng.uniform(XLB + 4, W - 2, 6):
        wdt, dep = rng.uniform(1.2, 3.4), rng.uniform(0.35, 1.0)
        cutp("frame", [(x, YF - 1), (x + 0.3, YF + dep * rng.uniform(0.4, 1)), (x + wdt / 2, YF + dep),
                       (x + wdt - 0.3, YF + dep * rng.uniform(0.3, 1)), (x + wdt, YF - 1)], "z", zb, zt + 0.3)
    for y in rng.uniform(YF + 4, (YL[1] if zt == L2 else D) - 2, 3):
        wdt, dep = rng.uniform(1.2, 3.0), rng.uniform(0.35, 0.9)
        cutp("frame", [(XLB - 1, y), (XLB + dep * rng.uniform(0.4, 1), y + 0.3), (XLB + dep, y + wdt / 2),
                       (XLB + dep * rng.uniform(0.3, 1), y + wdt - 0.3), (XLB - 1, y + wdt)], "z", zb, zt + 0.3)
    # broken top of the edge band (wedges along the edge)
    for x in rng.uniform(XLB + 3, W - 3, 5):
        dz, dy = rng.uniform(0.4, 1.1), rng.uniform(0.6, 1.5)
        cutp("frame", [(YF - 1, zt - dz), (YF + dy * 0.5, zt - dz * rng.uniform(0.2, 0.6)), (YF + dy, zt + 1),
                       (YF - 1, zt + 1)], "x", x, x + rng.uniform(1.5, 4.5))
# L1 hole the hanging slab broke out of (ground-floor left bay)
HOLE = (3.2, 14.2, 5.5, 12.5)
cutp("frame", jag_rect(*HOLE, amp=0.6, step=1.5)[0], "z", L1 - ST - 0.3, L1 + 0.3)
# column corner chips on the front line
for x in XL:
    for s in range(2):
        if rng.random() < 0.35:
            continue
        sg = 1 if rng.random() < 0.5 else -1
        cx, a, b = x + sg * h, rng.uniform(0.3, 0.65), rng.uniform(0.3, 0.65)
        A, B = np.array((cx - sg * a, -h)), np.array((cx, -h + b))
        z0 = s * FH + rng.uniform(1.5, 8.0)
        cutp("frame", [tuple(A + (A - B) * 0.5), tuple(B + (B - A) * 0.5), (cx + sg * 0.8, -h - 0.8)], "z",
             z0, z0 + rng.uniform(1.2, 3.5))


def broken_top(x, y, top, depth):
    """convex-hull cutter whose underside is two random tilted facets -> jagged column end"""
    s = h + 0.6
    lo = [(x + dx * s, y + dy * s, top - rng.uniform(0.15, depth)) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    CUTS["frame"].append(("hull", lo + [(p[0], p[1], top + 3) for p in lo]))
    dx, dy = rng.choice([-1, 1]), rng.choice([-1, 1])
    k = [(x + dx * h, y + dy * h, top - depth - 0.6)]
    k += [(x + dx * (h + 0.5), y + dy * (h - 0.8), top + 1), (x + dx * (h - 0.8), y + dy * (h + 0.5), top + 1),
          (x + dx * (h + 0.5), y + dy * (h + 0.5), top + 1)]
    CUTS["frame"].append(("hull", k))  # one chipped corner


broken_top(0.0, 0.0, cct, 2.2)
broken_top(W, 0.0, st + 0.5, 1.4)
broken_top(0.0, D, L2 - c["beam_d"] - 0.2, 1.2)


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


def emit_faces(lab):
    """{part_id: [quad of grid-index triples]}: every part as a closed solid (faces against anything not itself,
    ground faces included); contact faces are removed later by the hidden-face pass"""
    P = np.pad(lab, 1)
    out = {}
    for ax in range(3):
        sl_a = [slice(1, -1)] * 3
        sl_b = [slice(1, -1)] * 3
        sl_a[ax] = slice(0, -1)
        sl_b[ax] = slice(1, None)
        A, B = P[tuple(sl_a)], P[tuple(sl_b)]
        for sign, own, other in ((1, A, B), (-1, B, A)):
            idx = np.argwhere((own != 0) & (other != own))
            for (i, j, k) in idx:
                part = int(own[i, j, k])
                if ax == 0:
                    q = [(i, j, k), (i, j + 1, k), (i, j + 1, k + 1), (i, j, k + 1)]
                elif ax == 1:
                    q = [(i, j, k), (i, j, k + 1), (i + 1, j, k + 1), (i + 1, j, k)]
                else:
                    q = [(i, j, k), (i + 1, j, k), (i + 1, j + 1, k), (i, j + 1, k)]
                if sign == -1:
                    q = q[::-1]
                out.setdefault(part, []).append(q)
    return out


def part_mesh(quads, xs, ys, zs):
    bm = bmesh.new()
    vmap = {}

    def V(t):
        if t not in vmap:
            vmap[t] = bm.verts.new((float(xs[t[0]]), float(ys[t[1]]), float(zs[t[2]])))
        return vmap[t]

    for q in quads:
        bm.faces.new([V(t) for t in q])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=list(bm.verts), edges=list(bm.edges))
    return bm


# ---------------------------------------------------------------- 3D helpers
def to3(pl, u, v, d):
    return (u, d, v) if pl == "y" else (d, u, v) if pl == "x" else (u, v, d)


def prism(poly, pl, d0, d1, bm=None):
    bm = bm or bmesh.new()
    a = [bm.verts.new(to3(pl, u, v, d0)) for (u, v) in poly]
    b = [bm.verts.new(to3(pl, u, v, d1)) for (u, v) in poly]
    fs = [bm.faces.new(a), bm.faces.new(b[::-1])]
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        fs.append(bm.faces.new([a[j], a[i], b[i], b[j]]))
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return bm


def hull(points, bm=None):
    bm = bm or bmesh.new()
    vs = [bm.verts.new(p) for p in points]
    r = bmesh.ops.convex_hull(bm, input=vs)
    bad = {g for g in r["geom_interior"] + r["geom_unused"] if isinstance(g, bmesh.types.BMVert)}
    bmesh.ops.delete(bm, geom=list(bad), context="VERTS")
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(4), verts=list(bm.verts), edges=list(bm.edges))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def rot(rx, ry, rz):
    return (Matrix.Rotation(math.radians(rz), 4, "Z") @ Matrix.Rotation(math.radians(ry), 4, "Y")
            @ Matrix.Rotation(math.radians(rx), 4, "X"))


def place(bm, M, t):
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(t)) @ M, verts=bm.verts)
    return bm


def cutter_bm(cdef):
    if cdef[0] == "prism":
        return prism(*cdef[1:])
    return hull(cdef[1])


def apply_cuts(ob, cutters):
    col = bpy.data.collections.new("cut_" + ob.name)
    bpy.context.scene.collection.children.link(col)
    for i, cdef in enumerate(cutters):
        bm = cutter_bm(cdef)
        me = bpy.data.meshes.new(f"c{i}")
        bm.to_mesh(me)
        bm.free()
        col.objects.link(bpy.data.objects.new(f"{ob.name}_c{i}", me))
    m = ob.modifiers.new("cut", "BOOLEAN")
    m.operation, m.solver, m.operand_type, m.collection = "DIFFERENCE", "EXACT", "COLLECTION", col
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.remove(m)
    for o in list(col.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(col)
    return me


class Solid:
    def __init__(self, part, V, F, occluder=True):
        self.part, self.V, self.F, self.occ = part, np.asarray(V, float).reshape(-1, 3), F, occluder
        self.lo, self.hi = self.V.min(0) - 0.05, self.V.max(0) + 0.05
        self.bvh = BVHTree.FromPolygons([tuple(v) for v in self.V], F) if occluder else None


SOLIDS = []


def add_bm(part, bm, occluder=True):
    # triangles: BVH ray parity needs them (concave ngons fan-triangulate wrongly) and partly hidden ngons split
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    V = [tuple(v.co) for v in bm.verts]
    F = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    if F:
        SOLIDS.append(Solid(part, V, F, occluder))


def add_mesh(part, me):
    bm = bmesh.new()
    bm.from_mesh(me)
    add_bm(part, bm)


# ---------------------------------------------------------------- slabs_broken
def slab_piece(poly, t, M, at):
    return place(prism(poly, "z", -t, 0.0), M, at)


def build_slabs_broken():
    # hanging slab: hinged on the left edge of the L1 hole, hanging down into the ground-floor left bay
    poly = jag_rect(0.0, 11.5, 0.0, 6.6, amp=0.5, step=1.4)[0]
    add_bm("slabs_broken", slab_piece(poly, 0.85, rot(0, 66, 0), (HOLE[0] + 0.2, HOLE[2] + 0.3, L1 - 0.15)))
    # M1 plates, now with broken outlines: leaning on L1 (bay 0, front) and collapsed on the ground (bay 0, front)
    a, b = bay_u(0)
    add_bm("slabs_broken", slab_piece(jag_rect(-5.5, 5.5, -2.2, 2.2, amp=0.45)[0], 0.8, rot(14, -16, 6),
                                      ((a + b) / 2 + 0.5, 3.2, L1 + 2.0)))
    add_bm("slabs_broken", slab_piece(jag_rect(-4.0, 4.0, -2.2, 2.2, amp=0.45)[0], 0.8, rot(-10, 20, -8),
                                      (11.5, 3.5, G + 1.9)))
    # broken balcony end hanging from the L1 front-left break, and a roof piece hanging at the L2 back-left break
    add_bm("slabs_broken", slab_piece(jag_rect(0, 2.8, -2.6, 0, amp=0.35, step=1.0)[0], 0.8, rot(55, 0, 0),
                                      (XLB + 0.15, YF + 2.0, L1 - 0.2)))
    add_bm("slabs_broken", slab_piece(jag_rect(0, 5.5, 0, 3.6, amp=0.4, step=1.2)[0], 0.8, rot(-58, 0, 4),
                                      (5.0, YL[1] + h - 0.3, L2 - 0.3)))


# ---------------------------------------------------------------- rubble + debris
def mound(part, x0, x1, y0, y1, hfun, sp, z0=0.0, cut0=0.4):
    """low-poly rubble heap: jittered grid + Delaunay, height hfun(x,y) (+-lumps), open bottom on the support"""
    gx, gy = np.arange(x0, x1 + 1e-6, sp), np.arange(y0, y1 + 1e-6, sp * 0.866)
    P = []
    for j, y in enumerate(gy):
        for x in gx + (sp / 2 if j % 2 else 0):
            P.append((x + rng.uniform(-0.25, 0.25) * sp, y + rng.uniform(-0.25, 0.25) * sp))
    P = np.array(P)
    H = np.array([hfun(x, y) for x, y in P])
    H = np.where(H > cut0, H * rng.uniform(0.82, 1.18, len(H)), 0.0)
    tri = Delaunay(P).simplices
    tri = tri[(H[tri] > 0).any(1)]
    used = np.unique(tri)
    remap = -np.ones(len(P), int)
    remap[used] = np.arange(len(used))
    V = np.c_[P[used], z0 + H[used]]
    F = []
    for t in remap[tri]:
        a, b, cc = V[t]
        F.append(list(t) if np.cross(b - a, cc - a)[2] > 0 else list(t[::-1]))
    SOLIDS.append(Solid(part, V, F))
    return hfun


def chunk(part, at, size, flat=False):
    sx, sy, sz = size
    pts = [(dx * sx / 2 * rng.uniform(0.55, 1), dy * sy / 2 * rng.uniform(0.55, 1), dz * sz / 2 * rng.uniform(0.55, 1))
           for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
    pts.append((rng.uniform(-0.3, 0.3) * sx, rng.uniform(-0.3, 0.3) * sy, sz / 2 * rng.uniform(0.9, 1.25)))
    tilt = 8 if flat else 30
    M = rot(rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt), rng.uniform(0, 360))
    add_bm(part, place(hull(pts), M, at))


def ridge(x, xp, hp):
    return float(np.interp(x, xp, hp))


def heap(d_out, d_in, hx, w_in=6.0, k=1.0):
    """cross-section: rises outside over 0.4 + k h (k=1: 45 deg, ref heaps are steep), slow fall inside"""
    if d_out >= 0:
        return hx * max(0.0, 1 - d_out / (0.4 + k * hx))
    return hx * max(0.0, 1 - 0.75 * (-d_out) / w_in) if -d_out < w_in else 0.0


def build_rubble():
    FX, FHh = [-10, -7, -2, 6, 16, 30, 44, W + 1, W + 4], [0.0, 4.6, 5.6, 5.2, 3.9, 3.4, 3.5, 3.7, 0.0]
    front = mound("rubble", -11, W + 5, -10, 6, lambda x, y: heap(-2.5 - y, 0, ridge(x, FX, FHh)), 1.5)
    LY, LH = [-8, -2, 8, 20, D + 2, D + 7], [4.6, 5.4, 4.0, 2.6, 1.6, 0.0]
    left = mound("rubble", -11, 4, -8, D + 7, lambda x, y: heap(-5.0 - x, 0, ridge(y, LY, LH), 8.0, 0.8), 1.6)
    RY, RH = [-6, 0, 14, D + 2, D + 6], [0.0, 2.8, 2.2, 1.6, 0.0]
    mound("rubble", W - 4, W + 6, -6, D + 6, lambda x, y: heap(x - (W + 1.2), 0, ridge(y, RY, RH)), 1.8)
    BX, BH = [-4, 0, 30, W, W + 4], [0.0, 1.6, 1.2, 1.4, 0.0]
    mound("rubble", -6, W + 6, D - 4, D + 7, lambda x, y: heap(y - (D + 1.5), 0, ridge(x, BX, BH)), 2.2)
    # heap under the hanging slab inside the ground-floor left bay
    inner = mound("rubble", 1.2, 16, 1.2, 13, lambda x, y: G + 2.8 * max(0, 1 - math.hypot(x - 9, y - 9.5) / 6.0)
                  - G, 1.3, z0=G)
    # piles along the slab edges (front band and left balcony) on L1 and L2
    piles = []
    for zt in (L1, L2):
        xr = (XLB + 0.6, W + h - 0.3)
        ffun = (lambda zt_: lambda x, y: (0.7 + 0.8 * abs(math.sin(x * 0.37 + zt_))) *
                max(0, 1 - abs(y - (YF + 1.6)) / 1.5))(zt)
        mound("rubble", xr[0], xr[1], YF + 0.05, YF + 3.2, ffun, 1.2, z0=zt, cut0=0.3)
        ybk = YL[1] if zt == L2 else D
        lfun = (lambda zt_: lambda x, y: (0.6 + 0.7 * abs(math.sin(y * 0.41 + zt_))) *
                max(0, 1 - abs(x - (XLB + 1.7)) / 1.6))(zt)
        mound("rubble", XLB + 0.05, -h + 0.2, YF + 2.5, ybk - 1.0, lfun, 1.2, z0=zt, cut0=0.3)
        piles.append((zt, ffun, lfun, ybk))
    # chunks on the mounds (rubble part)
    n = 0
    for _ in range(4000):
        if n >= 330:
            break
        x, y = rng.uniform(-10, W + 4), rng.uniform(-10, D + 5)
        hh = max(front(x, y), left(x, y))
        if hh < 0.9:
            continue
        s = rng.uniform(0.9, 2.2) if rng.random() < 0.8 else rng.uniform(2.2, 3.0)
        chunk("rubble", (x, y, hh - 0.12 * s), (s, s * rng.uniform(0.6, 1.1), s * rng.uniform(0.45, 0.8)))
        n += 1
    for _ in range(14):
        x, y = rng.uniform(4, 15), rng.uniform(4, 12.5)
        s = rng.uniform(0.9, 1.8)
        chunk("rubble", (x, y, G + inner(x, y) - 0.1 * s), (s, s * 0.8, s * 0.55))
    for (zt, ffun, lfun, ybk) in piles:  # chunks on the edge piles, some hanging over the edge
        for x in np.arange(XLB + 1.0, W, 1.3):
            if rng.random() < 0.25:
                continue
            y = YF + rng.uniform(-0.2, 2.4)
            s = rng.uniform(0.8, 1.6)
            chunk("rubble", (x + rng.uniform(-0.5, 0.5), y, zt + ffun(x, max(y, YF)) - 0.1 * s + 0.2),
                  (s, s * 0.8, s * 0.6))
        for y in np.arange(YF + 3, ybk - 1, 1.5):
            if rng.random() < 0.3:
                continue
            x = XLB + rng.uniform(-0.2, 2.2)
            s = rng.uniform(0.8, 1.5)
            chunk("rubble", (x, y, zt + lfun(max(x, XLB), y) - 0.1 * s + 0.2), (s, s * 0.8, s * 0.6))


def build_debris():
    def ok_floor(x, y, zt):
        if any(abs(x - cx) < h + 1.0 and abs(y - cy) < h + 1.0 for cx in XL for cy in YL):
            return False
        if zt == L1 and HOLE[0] - 1 < x < HOLE[1] + 1 and HOLE[2] - 1 < y < HOLE[3] + 1:
            return False
        if zt == L2 and x < XL[1] and y > YL[1]:
            return False
        return True

    for zt, n in ((G, 34), (L1, 34), (L2, 40)):
        k = 0
        while k < n:
            x, y = rng.uniform(1.5, W - 1.5), rng.uniform(1.5, D - 1.5)
            if zt == L2 and rng.random() < 0.5:
                y = rng.uniform(1.0, 6.0)  # roof debris crowds the front, around the standing pieces
            if not ok_floor(x, y, zt):
                continue
            s = rng.uniform(0.7, 1.6)
            if rng.random() < 0.25:  # block
                chunk("debris", (x, y, zt + 0.22 * s), (1.3 * s, 0.65 * s, 0.6 * s), flat=True)
            else:
                chunk("debris", (x, y, zt + 0.2 * s), (s, s * rng.uniform(0.6, 1.0), s * rng.uniform(0.4, 0.7)))
            k += 1
    for _ in range(18):  # loose chunks rolled off the front heap
        x = rng.uniform(-7, W + 3)
        y = rng.uniform(-10.5, -6.5)
        s = rng.uniform(0.7, 1.5)
        chunk("debris", (x, y, 0.2 * s), (s, s * 0.8, s * 0.55))
    for (x, y, zt, sx, sy, rr) in [(36, 9, L1, 3.2, 2.4, (6, -9, 30)), (24, 6, G, 2.8, 2.2, (-7, 10, 75)),
                                   (44, 18, L2, 3.4, 2.6, (8, 5, 140)), (-4, -10.5, 0, 3.0, 2.0, (5, -12, 20)),
                                   (50, 20, G, 2.6, 2.0, (9, 6, 200)), (22, 3, L2, 2.4, 1.8, (-6, 8, 60))]:
        add_bm("debris", slab_piece(jag_rect(-sx / 2, sx / 2, -sy / 2, sy / 2, amp=0.3, step=0.9)[0], 0.5,
                                    rot(*rr), (x, y, zt + 0.55)))


# ---------------------------------------------------------------- rebar
def bar(pts, r=0.1, sides=4):
    bm = bmesh.new()
    P = [Vector(p) for p in pts]
    rings, s = [], None
    for i, p in enumerate(P):
        if i == 0:
            t = P[1] - P[0]
        elif i == len(P) - 1:
            t = P[-1] - P[-2]
        else:
            t = (P[i + 1] - P[i]).normalized() + (P[i] - P[i - 1]).normalized()
        t.normalize()
        s = t.orthogonal().normalized() if s is None else (s - t * s.dot(t)).normalized()
        b2 = t.cross(s)
        rings.append([bm.verts.new(p + r * (math.cos(a) * s + math.sin(a) * b2))
                      for a in np.linspace(0, 2 * math.pi, sides, endpoint=False) + math.pi / sides])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(sides):
            bm.faces.new([a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]])
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    add_bm("rebar", bm, occluder=False)


def bent(p0, dirs):
    """polyline from p0 through relative steps"""
    pts = [np.array(p0, float)]
    for d in dirs:
        pts.append(pts[-1] + np.array(d, float))
    return pts


def j(a):
    return rng.uniform(-a, a)


def build_rebar():
    # top-left corner stump: tall bars, slightly bent
    for (dx, dy) in ((-0.6, -0.6), (0.6, -0.6), (0.6, 0.6), (-0.6, 0.6), (0.0, -0.6), (-0.6, 0.0)):
        bar(bent((dx, dy, cct - 3.0), [(0, 0, 3.0 + rng.uniform(0.5, 2.0)), (j(0.5), j(0.5), rng.uniform(1.5, 2.5)),
                                       (j(0.9), j(0.9), rng.uniform(0.8, 2.2))]))
    # left balcony breaks: bars out of the broken end, bent down; bars hanging off the balcony edge beam
    for zt in (L1, L2):
        for k in range(3):
            x = XLB + 0.5 + k * 0.8
            bar(bent((x, YF + 2.6, zt - 0.5), [(j(0.2), -1.4, 0), (j(0.4), -0.6, -1.2),
                                                (j(0.6), j(0.4), -rng.uniform(1.5, 5.0))]))
    for (y, ln) in ((4.0, 5.5), (7.5, 3.5), (10.5, 6.5)):
        bar(bent((XLB + 0.5, y, L1 - 1.2), [(-0.6, 0, -0.6), (j(0.3), j(0.3), -ln * 0.5), (j(0.6), j(0.5), -ln * 0.5)]))
    # roof break at the back-left: bars sticking out, drooping
    for x in (2.5, 5.5, 8.0, 11.5, 14.5):
        bar(bent((x, YL[1] + h - 1.0, L2 - 0.5), [(j(0.2), 2.2, 0), (j(0.4), rng.uniform(0.6, 1.4), -rng.uniform(0.4, 1.8))]))
    # hanging slab hinge and the far edge of its hole
    for y in (6.6, 8.6, 10.6):
        bar(bent((HOLE[0] - 1.2, y, L1 - 0.5), [(1.6, 0, -0.3), (0.5, j(0.2), -1.4)]))
    for y in (7.0, 10.0):
        bar(bent((HOLE[1] + 1.2, y, L1 - 0.5), [(-2.0, j(0.2), -0.1), (-0.6, j(0.3), -1.3)]))
    # right stub column, standing wall top, column stump at the back-left, front edge breaks
    for (dx, dy) in ((-0.55, -0.55), (0.55, -0.55), (0.55, 0.55)):
        bar(bent((W + dx, dy, st - 1.5), [(0, 0, 2.5 + rng.uniform(0.3, 1.2)), (j(0.6), j(0.6), rng.uniform(0.6, 1.5))]))
    for x in (sw0 + 6.0, sw0 + 10.5, sw1 - 4.5):
        bar(bent((x, 0.0, T - 2.5), [(0, 0, 2.5 + rng.uniform(0.4, 1.0)), (j(0.7), j(0.7), rng.uniform(0.5, 1.3))]))
    for (dx, dy) in ((-0.55, -0.55), (0.55, 0.55)):
        bar(bent((dx, D + dy, L2 - 4.5), [(0, 0, 3.4 + rng.uniform(0.2, 1.0)), (j(0.6), j(0.6), 1.0)]))
    for x in (9.0, 27.0, 41.0):
        bar(bent((x, YF + 1.2, L1 - 1.6), [(0, -2.2, 0), (j(0.4), -0.5, -rng.uniform(1.0, 2.5))]))


# ---------------------------------------------------------------- hidden faces
RAYS = [Vector(d).normalized() for d in ((0.0123, 0.0071, 1.0), (-0.21, 0.13, 1.0), (0.17, -0.24, 1.0))]


def parity(s, p, ray):
    o, n = Vector(p), 0
    while n < 60:
        hit = s.bvh.ray_cast(o, ray)
        if hit[0] is None:
            break
        n += 1
        o = hit[0] + ray * 1e-4
    return n % 2


def inside(s, p):
    """ray parity, majority of 3 upward rays (one ray can graze an edge); upward rays also work for the open-bottom
    rubble heaps"""
    return sum(parity(s, p, r) for r in RAYS) >= 2


def hidden_pass():
    occ = [s for s in SOLIDS if s.occ]
    LO = np.array([s.lo for s in occ])
    HI = np.array([s.hi for s in occ])
    kept = {p: [] for p in PARTS}
    dropped = {p: 0 for p in PARTS}
    for si, s in enumerate(SOLIDS):
        keepF = []
        for f in s.F:
            P = s.V[f]
            cen = P.mean(0)
            nn = np.zeros(3)
            for a, b in zip(P, np.roll(P, -1, 0)):
                nn += np.cross(a, b)
            ln = np.linalg.norm(nn)
            nn = nn / ln if ln > 1e-12 else nn
            dv = cen - P
            dl = np.linalg.norm(dv, axis=1, keepdims=True)
            tp = np.vstack([cen, P + dv * np.minimum(1, 0.04 / np.maximum(dl, 1e-9))]) + nn * 0.02
            if (tp[:, 2] < 0).all():
                dropped[s.part] += 1
                continue
            hid = True
            for p in tp:
                if p[2] < 0:
                    continue
                cand = np.nonzero((p >= LO).all(1) & (p <= HI).all(1))[0]
                if not any(occ[k] is not s and inside(occ[k], p) for k in cand):
                    hid = False
                    break
            if hid:
                dropped[s.part] += 1
            else:
                keepF.append(f)
        if keepF:
            kept[s.part].append((s.V, keepF))
    return kept, dropped


# ---------------------------------------------------------------- final meshes
def finish(name, pieces):
    bm = bmesh.new()
    for V, F in pieces:
        vs = [bm.verts.new(tuple(v)) for v in V]
        for f in F:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-3)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-3, edges=list(bm.edges))
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), verts=list(bm.verts), edges=list(bm.edges))
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-6], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(f"{name}_mat")
    mat.use_nodes = True
    grey = GREY[name]
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = ((grey * 1.6, grey * 0.9, grey * 0.6, 1) if name == "rebar"
                                               else (grey, grey * 0.98, grey * 0.94, 1))
    bsdf.inputs["Roughness"].default_value = 0.95
    me.materials.append(mat)
    # weighted normals: smooth shading, sharp edges above 30 deg, face-area weighting keeps flat faces flat
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(30))
    m = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    m.mode, m.keep_sharp = "FACE_AREA", True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="wn")
    return ob


def mesh_checks(ob):
    me = ob.data
    V = np.array([v.co[:] for v in me.vertices])
    pairs = cKDTree(V).query_pairs(1e-3) if len(V) else set()
    areas = np.array([p.area for p in me.polygons])
    bm = bmesh.new()
    bm.from_mesh(me)
    open_e = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    loose = sum(1 for v in bm.verts if not v.link_faces)
    bm.free()
    return dict(tris=len(me.polygons), dup_verts=len(pairs), zero_area=int((areas < 1e-6).sum()),
                small_faces=int((areas < 0.05).sum()), loose_verts=loose, open_edges=open_e, nonmanifold_edges=nonman)


def layer_gaps(obs):
    """axis-aligned faces of different parts facing each other or stacked: count coplanar overlaps (< 0.01) and
    the smallest non-zero gap between parallel overlapping faces"""
    recs = {}
    for name, ob in obs.items():
        for p in ob.data.polygons:
            n = p.normal
            ax = int(np.argmax(np.abs(n)))
            if abs(n[ax]) < 0.999 or p.area < 0.01:
                continue
            P = np.array([ob.data.vertices[i].co[:] for i in p.vertices])
            o = [k for k in range(3) if k != ax]
            recs.setdefault(ax, []).append((name, P[0, ax], P[:, o[0]].min(), P[:, o[0]].max(), P[:, o[1]].min(),
                                           P[:, o[1]].max()))
    coplanar, gap = 0, 99.0
    for ax, R in recs.items():
        names = np.array([r[0] for r in R])
        A = np.array([r[1:] for r in R], float)
        for i in range(len(R)):
            m = names != names[i]
            ov = (np.minimum(A[m, 2], A[i, 2]) - np.maximum(A[m, 1], A[i, 1]) > 0.05) & \
                 (np.minimum(A[m, 4], A[i, 4]) - np.maximum(A[m, 3], A[i, 3]) > 0.05)
            d = np.abs(A[m, 0] - A[i, 0])[ov]
            coplanar += int((d < 0.01).sum())
            if (d >= 0.01).any():
                gap = min(gap, float(d[d >= 0.01].min()))
    return coplanar // 2, gap


def main():
    os.makedirs(os.path.join(OUT, "work"), exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    lab, xs, ys, zs, pid = grid_label()
    faces = emit_faces(lab)
    for part in ("frame", "walls"):
        bm = part_mesh(faces[pid[part]], xs, ys, zs)
        me = bpy.data.meshes.new(part + "_raw")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(part + "_raw", me)
        bpy.context.scene.collection.objects.link(ob)
        add_mesh(part, apply_cuts(ob, CUTS[part]))
        print(f"  {part}: {len(CUTS[part])} jagged cutters applied", flush=True)
        bpy.data.objects.remove(ob)
    build_slabs_broken()
    build_rubble()
    build_debris()
    build_rebar()
    print(f"  solids {len(SOLIDS)}; hidden-face pass ...", flush=True)
    kept, dropped = hidden_pass()
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    obs = {p: finish(p, kept[p]) for p in PARTS if kept[p]}

    # ---------------------------------------------------------- checks
    chk = {k: mesh_checks(o) for k, o in obs.items()}
    tris = {k: v["tris"] for k, v in chk.items()}
    total = sum(tris.values())
    allA = np.concatenate([[p.area for p in o.data.polygons] for o in obs.values()])
    small_share = float((allA < 0.05).mean())
    coplanar, gap = layer_gaps(obs)
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in obs.values():
        for v in o.data.vertices:
            lo = Vector(map(min, lo, v.co))
            hi = Vector(map(max, hi, v.co))

    def free(b):
        ix = (xs[1:] > b[0]) & (xs[:-1] < b[1])
        iy = (ys[1:] > b[2]) & (ys[:-1] < b[3])
        iz = (zs[1:] > b[4]) & (zs[:-1] < b[5])
        return not lab[np.ix_(ix, iy, iz)].any()

    def solid_under(x, y, z):
        i = np.searchsorted(xs, x) - 1
        j_ = np.searchsorted(ys, y) - 1
        k = np.searchsorted(zs, z - 0.05) - 1
        return lab[i, j_, k] == pid["frame"]

    av = []
    for i in range(4):
        a, b = bay_u(i)
        ok = any(free((x - 1, x + 1, -3, 3, G + 0.01, G + 5.5)) for x in np.arange(a + 1, b - 1, 0.5))
        av.append(("walk through ground bay %d" % i, bool(ok)))
    for name, z in (("stand on ground slab", G), ("stand on level-1 slab", L1), ("stand on level-2 slab", L2)):
        a, b = bay_u(1)
        x, y = (a + b) / 2, YL[1] / 2
        ok = free((x - 1, x + 1, y - 0.5, y + 0.5, z + 0.01, z + 5.5)) and solid_under(x, y, z)
        av.append((name + " (bay 1, x=%.1f y=%.1f z=%.1f)" % (x, y, z), bool(ok)))

    fails = []
    if total >= 35000:
        fails.append("total >= 35000")
    for k, v in tris.items():
        if v >= 20000 or v > BUDGET[k] * 1.2:
            fails.append(f"{k} {v} over budget")
        if chk[k]["dup_verts"] or chk[k]["zero_area"] or chk[k]["loose_verts"]:
            fails.append(f"{k} dup/zero/loose")
    if small_share >= 0.10:
        fails.append("small-face share >= 10%")
    if coplanar:
        fails.append(f"{coplanar} coplanar face pairs between parts")
    stats = dict(tris=tris, total=total, checks=chk, hidden_faces_deleted=dropped, small_face_share=small_share,
                 coplanar_pairs_between_parts=coplanar, smallest_parallel_gap=gap, bounds_min=list(lo),
                 bounds_max=list(hi), avatar=av, fails=fails, config=C)
    with open(os.path.join(OUT, "m2_stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    for k, v in chk.items():
        print(f"  {k:13s} {v['tris']:6d} tris (budget {BUDGET[k]}) dup {v['dup_verts']} zero {v['zero_area']} "
              f"loose {v['loose_verts']} small {v['small_faces']} open {v['open_edges']} nonman "
              f"{v['nonmanifold_edges']} | hidden deleted {dropped[k]}")
    print(f"  TOTAL {total} tris; small-face share {small_share:.3f}; coplanar pairs {coplanar}; smallest gap "
          f"{gap:.3f}; bounds {tuple(round(v, 2) for v in lo)} .. {tuple(round(v, 2) for v in hi)}")
    for n, ok in av:
        print(f"  avatar: {n}: {'OK' if ok else 'FAIL'}")
    print("  FAILS:", fails or "none")

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "work", "building01.blend"))
    # raw FBX numbers = studs (global_scale 0.01 x apply_unit_scale 100), GLB in BU; custom (weighted) normals kept
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "building01.fbx"), global_scale=0.01, apply_unit_scale=True,
                             object_types={"MESH"}, mesh_smooth_type="OFF", axis_forward="-Z", axis_up="Y")
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "building01.glb"), export_format="GLB")
    if fails:
        sys.exit("FAIL: " + "; ".join(fails))


if __name__ == "__main__":
    main()
