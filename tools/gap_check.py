"""Gap check: rays from outside the building and from eye height inside every floor; a ray whose FIRST hit is the
back of a face is looking into a part through a hole (a deleted contact face that is not covered, or a flipped face).

usage (local Blender): blender -b --factory-startup --python tools/gap_check.py -- [out/building01/building01.glb]
Prints the number of back-face hits and the worst spots (studs, rounded to 1), writes gap_check_<glb name>.json beside the GLB.
Rays that hit below z = 0.3 are ignored (rubble and slab bottoms under the ground are deleted on purpose).
"""
import json
import math
import os
import sys
from collections import Counter

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = os.path.abspath(args[0]) if args else os.path.join(ROOT, "out", "building01", "building01.glb")
CENTER = Vector((28.0, 14.0, 18.0))


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=GLB)
    bm = bmesh.new()
    owner = []
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        me = ob.data.copy()
        me.transform(ob.matrix_world)
        n0 = len(bm.faces)
        bm.from_mesh(me)
        owner += [(ob.name.split(".")[0], i) for i in range(len(bm.faces) - n0)]
        bpy.data.meshes.remove(me)
    bm.faces.ensure_lookup_table()
    return BVHTree.FromBMesh(bm), owner, bm


def directions(nu=72, nv=36):
    out = []
    for j in range(nv):
        el = -math.pi / 2 + math.pi * (j + 0.5) / nv
        for i in range(nu):
            az = 2 * math.pi * i / nu
            out.append(Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))))
    return out


def eyes():
    pts = []
    for k in range(48):  # rings around the building: near (players at the rubble) and far, low to high
        a = 2 * math.pi * k / 48
        for r, zs in ((1.0, (2.0, 6.0, 12.0, 22.0, 35.0, 55.0)), (0.62, (2.0, 5.0, 9.0))):
            for z in zs:
                pts.append(Vector((CENTER.x + 75 * r * math.cos(a), CENTER.y + 60 * r * math.sin(a), z)))
    for zf in (0.5, 14.0, 28.0):  # player eyes inside each floor, every bay and depth bay centre
        for x in (8.5, 24.0, 38.0, 50.5):
            for y in (5.0, 14.0, 23.0):
                pts.append(Vector((x, y, zf + 5.0)))
    return pts


def main():
    bvh, owner, bm = load()
    dirs = directions()
    bad = Counter()
    spots = Counter()
    faces = set()
    rays = 0
    for e in eyes():
        if bvh.find_nearest(e, 0.6)[0] is not None:  # eye touching geometry: skip
            continue
        up = bvh.ray_cast(e, Vector((0, 0, 1)), 400.0)
        if up[0] is not None and up[1].z > 0:  # first face above is seen from below: the eye is buried in rubble
            continue
        for d in dirs:
            loc, nrm, idx, dist = bvh.ray_cast(e, d, 400.0)
            if loc is None:
                continue
            rays += 1
            if loc.z < 0.3:
                continue
            if nrm.dot(d) > 0.02:
                part, li = owner[idx]
                bad[part] += 1
                faces.add((part, li))
                spots[(part, round(loc.x), round(loc.y), round(loc.z))] += 1
    res = dict(rays_hit=rays, backface_hits=sum(bad.values()), by_part=dict(bad),
               worst=[[*k, v] for k, v in spots.most_common(12)], patch_faces=sorted(faces))
    print("GAPCHECK", json.dumps({k: v for k, v in res.items() if k != "patch_faces"}), "faces", len(faces))
    name = os.path.splitext(os.path.basename(GLB))[0]
    json.dump(res, open(os.path.join(os.path.dirname(GLB), f"gap_check_{name}.json"), "w"), indent=1)


main()
