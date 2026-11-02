"""Floating-piece check: every loose piece (mesh island) of rubble, debris, slabs_broken and rebar must rest on, or
stick into, something else. A piece floats when no vertex is within GAP studs of another island or the ground and
no edge of it crosses another surface.

usage (local Blender): blender -b --factory-startup --python tools/float_check.py -- [out/building01/building01.glb]
Prints the count and the worst pieces (centre, lowest z, distance to the nearest support).
"""
import json
import os
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = os.path.abspath(args[0]) if args else os.path.join(ROOT, "out", "building01", "building01.glb")
LOOSE = ("rubble", "rubble_upper", "debris", "slabs_broken", "rebar")
GAP = 0.15


def islands(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(isl)
    return out


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=GLB)
    pieces = []  # (part, verts) for every island of every object
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        bm.faces.ensure_lookup_table()
        for isl in islands(bm):
            vs = {v for f in isl for v in f.verts}
            pieces.append((ob.name.split(".")[0], [v.co.copy() for v in vs], [[v.co.copy() for v in f.verts] for f in isl]))
        bm.free()
    floating = []
    for i, (part, vs, fs) in enumerate(pieces):
        if part.replace("_inner", "") not in LOOSE:
            continue
        zmin = min(v.z for v in vs)
        if zmin < GAP:  # on the ground
            continue
        # support = every other island, plus the ground plane
        bm = bmesh.new()
        for j, (_, _, fs2) in enumerate(pieces):
            if j == i:
                continue
            for f in fs2:
                try:
                    bm.faces.new([bm.verts.new(c) for c in f])
                except ValueError:
                    pass
        tree = BVHTree.FromBMesh(bm)
        bm.free()
        d = min(tree.find_nearest(v)[3] for v in vs)  # touches support anywhere (hanging rebar rests at its top)
        if d > GAP:  # or crosses a support surface (an end buried inside the concrete is far from its surface)
            for f in fs:
                for a, b in zip(f, f[1:] + f[:1]):
                    if (b - a).length > 1e-6 and tree.ray_cast(a, (b - a).normalized(), (b - a).length)[0] is not None:
                        d = 0.0
                        break
                if d == 0.0:
                    break
        if d > GAP:
            c = sum(vs, Vector()) / len(vs)
            floating.append((part, [round(x, 1) for x in c], round(zmin, 2), round(d, 2)))
    floating.sort(key=lambda r: -r[3])
    print("FLOATCHECK", json.dumps(dict(pieces_checked=sum(1 for p in pieces if p[0].replace("_inner", "") in LOOSE),
                                        floating=len(floating), worst=floating[:12])))


main()
