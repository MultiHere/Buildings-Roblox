"""M3: world-scale box UVs, PBR materials from out/building01/textures, FBX + GLB export, textured preview renders.

usage (local Blender): blender -b --factory-startup --python-exit-code 1 --python tools/m3_export.py
         (cloud bpy):  /opt/bpyenv/bin/python tools/m3_export.py
Input is the M2 GLB (geometry and custom normals are final). Textures are tileable, so UVs are box-projected at a
fixed studs-per-repeat per part: texel density is the same everywhere and the client can swap any material.
Writes out/building01/building01_textured.fbx/.glb, prev_ref.png, prev_34.png, prev_close.png and m3_stats.json.
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "building01")
TEX = os.path.join(OUT, "textures")
CENTER = Vector((28.0, 14.0, 18.0))

TILE = {"frame": 10.0, "walls": 10.0, "slabs_broken": 10.0, "debris": 6.0, "rubble": 14.0, "rubble_upper": 14.0, "rebar": 2.0}
PREVIEW = "--no-render" not in sys.argv
SHADE_PARTS = ("frame", "walls", "slabs_broken")
SHADE_BELOW = 0.30  # sky openness under which a face gets the dark interior material


def scene_bvh():
    """One BVH of every mesh in world space plus a big ground quad, for openness rays."""
    bm = bmesh.new()
    for ob in bpy.context.scene.objects:
        if ob.type == "MESH":
            me = ob.data.copy()
            me.transform(ob.matrix_world)
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
    g = [bm.verts.new(v) for v in ((-500, -500, 0), (500, -500, 0), (500, 500, 0), (-500, 500, 0))]
    bm.faces.new(g)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def hemisphere(n=48):
    """Fibonacci sphere directions (unit vectors)."""
    out = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - z * z)
        out.append(Vector((r * math.cos(ga * i), r * math.sin(ga * i), z)))
    return out


def shade_faces(ob, bvh, dirs):
    """Material index 1 on faces that see little open sky (cos-weighted share of rays that escape)."""
    mw = ob.matrix_world
    nm = mw.to_3x3().inverted().transposed()
    shaded = 0
    for poly in ob.data.polygons:
        n = (nm @ poly.normal).normalized()
        c = mw @ poly.center
        pts = [c] + [c.lerp(mw @ ob.data.vertices[v].co, 0.6) for v in poly.vertices]
        tot = esc = 0.0
        for p in pts:
            o = p + n * 0.05
            for d in dirs:
                w = d.dot(n)
                if w <= 0.05:
                    continue
                tot += w
                if bvh.ray_cast(o, d, 120.0)[0] is None:
                    esc += w
        open_ = esc / tot if tot else 1.0
        if open_ < SHADE_BELOW:
            poly.material_index = 1
            shaded += 1
    return shaded / max(1, len(ob.data.polygons))


def box_uv(ob, tile):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            if ax == 0:
                u, v = (p.y if n.x > 0 else -p.y), p.z
            elif ax == 1:
                u, v = (-p.x if n.y > 0 else p.x), p.z
            else:
                u, v = p.x, (p.y if n.z > 0 else -p.y)
            lp[uv].uv = (u / tile, v / tile)
    bm.to_mesh(ob.data)
    bm.free()


def patch_backs(ob, faces):
    """Give the listed faces a back side: a reversed copy 0.01 studs behind (gap_check.py found them visible from
    behind, e.g. a rubble pile hanging over a chipped slab edge). Offset, so it never flickers with the front."""
    if not faces:
        return 0
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    n0 = len(bm.faces)
    for f in [bm.faces[i] for i in faces if i < n0]:
        vs = [bm.verts.new(v.co - f.normal * 0.01) for v in reversed(f.verts)]
        nf = bm.faces.new(vs)
        nf.material_index = f.material_index
    bm.to_mesh(ob.data)
    bm.free()
    return len(faces)


def split_inner(ob, part):
    """Faces with material 1 (dark interior) become their own object `<part>_inner`: Roblox keeps one material per
    MeshPart, so a second material on one mesh is dropped on import."""
    if not any(p.material_index == 1 for p in ob.data.polygons):
        return None
    for o in bpy.context.scene.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    ob.active_material_index = 1
    bpy.ops.object.material_slot_select()
    bpy.ops.mesh.separate(type="SELECTED")
    bpy.ops.object.mode_set(mode="OBJECT")
    inner = [o for o in bpy.context.selected_objects if o is not ob][0]
    inner.name = inner.data.name = f"{part}_inner"
    inner.data.materials.pop(index=0)  # keep only the shade material; pop does not remap the face indices
    for p in inner.data.polygons:
        p.material_index = 0
    ob.data.materials.pop(index=1)
    return inner


def check_materials():
    """Every exported object: exactly one material, every face on it, and a colour image on that material
    (an _inner part once shipped with faces pointing at a removed slot and imported untextured)."""
    bad = []
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        mats = ob.data.materials
        idx = {p.material_index for p in ob.data.polygons}
        tex = mats and any(n.type == "TEX_IMAGE" and n.image for n in mats[0].node_tree.nodes)
        if len(mats) != 1 or idx != {0} or not tex:
            bad.append((ob.name, len(mats), sorted(idx), bool(tex)))
    if bad:
        raise SystemExit(f"material check failed: {bad}")
    print("MATCHECK ok", len([o for o in bpy.context.scene.objects if o.type == "MESH"]), "objects")


def material(part, color="color", name=None):
    m = bpy.data.materials.new(name or part)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    def img(kind, data):
        path = os.path.join(TEX, f"{part}_{kind}.png")
        if not os.path.exists(path):
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path)
        if data:
            n.image.colorspace_settings.name = "Non-Color"
        return n

    c = img(color, False)
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    r = img("roughness", True)
    nt.links.new(r.outputs["Color"], bsdf.inputs["Roughness"])
    met = img("metalness", True)
    if met:
        nt.links.new(met.outputs["Color"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = 0.0
    nm = img("normal", True)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def tris(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def camera(sc, az, height, dist, res, aspect=1.5, center=CENTER, span=None):
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    a = math.radians(az)
    loc = Vector((center.x + dist * math.sin(a), center.y - dist * math.cos(a), height))
    cam.location = loc
    d = center - loc
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36
    cam.data.clip_end = 3000
    cam.data.lens = 36 * d.length / (span or 92.0)
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res / aspect)


def lights(sc):
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.78, 0.80, 0.85, 1)
    bg.inputs["Strength"].default_value = 0.55
    sc.world = w
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.2
    sun.angle = math.radians(2)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(52), 0, math.radians(-30))


def render(sc, name):
    sc.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, "building01.glb"))
    stats = {}
    bvh = scene_bvh()
    dirs = hemisphere()
    gc = os.path.join(OUT, "gap_check_building01.json")  # run gap_check.py on building01.glb first
    patch = {}
    if os.path.exists(gc):
        for part, i in json.load(open(gc))["patch_faces"]:
            patch.setdefault(part, []).append(i)
    # later rounds: hits found on the textured export, for parts that are not split (their face order is kept)
    gt = os.path.join(OUT, "patch_extra.json")
    extra = json.load(open(gt)) if os.path.exists(gt) else []
    for part, i in extra:
        if part not in SHADE_PARTS and i not in patch.get(part, []):
            patch.setdefault(part, []).append(i)
    inners = []
    for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
        part = ob.name.split(".")[0]
        if part not in TILE:
            raise SystemExit(f"unexpected object {ob.name}")
        ob.name = part
        ob.data.name = part
        patched = patch_backs(ob, patch.get(part, []))
        box_uv(ob, TILE[part])
        ob.data.materials.clear()
        ob.data.materials.append(material(part))
        shade = None
        if part in SHADE_PARTS:
            ob.data.materials.append(material(f"{part}_inner"))
            shade = round(shade_faces(ob, bvh, dirs), 3)
            inner = split_inner(ob, part)
            if inner:
                inners.append(inner)
        lo = [min((ob.matrix_world @ v.co)[i] for v in ob.data.vertices) for i in range(3)]
        hi = [max((ob.matrix_world @ v.co)[i] for v in ob.data.vertices) for i in range(3)]
        stats[part] = dict(tris=tris(ob), studs_per_repeat=TILE[part], px_per_stud=round(1024 / TILE[part], 1),
                           bounds=[round(a, 2) for a in lo + hi], shaded_share=shade, backs_patched=patched)
    for ob in inners:
        stats[ob.name] = dict(tris=tris(ob), studs_per_repeat=TILE[ob.name[:-6]], material=ob.data.materials[0].name)
    stats["total_tris"] = sum(v["tris"] for v in stats.values())
    print({k: v["tris"] for k, v in stats.items() if isinstance(v, dict)})
    print(json.dumps(stats))
    json.dump(stats, open(os.path.join(OUT, "m3_stats.json"), "w"), indent=1)

    check_materials()
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "building01_textured.glb"), export_format="GLB",
                              export_yup=True, export_normals=True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "building01_textured.fbx"), global_scale=0.01,
                             apply_unit_scale=True, axis_forward="-Z", axis_up="Y", mesh_smooth_type="OFF",
                             path_mode="COPY", embed_textures=True, object_types={"MESH"})
    if not PREVIEW:
        return
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    sc.render.film_transparent = False
    lights(sc)
    camera(sc, -16, 9, 220.0, 1200)
    render(sc, "prev_ref.png")
    sc.render.film_transparent = True  # for tools/silhouette.py against the reference
    render(sc, "prev_ref_alpha.png")
    sc.render.film_transparent = False
    camera(sc, -38, 30, 170.0, 1200)
    render(sc, "prev_34.png")
    camera(sc, -25, 6, 38.0, 1200, center=Vector((10.0, 0.0, 9.0)), span=30.0)
    render(sc, "prev_close.png")


main()
