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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "building01")
TEX = os.path.join(OUT, "textures")
CENTER = Vector((28.0, 14.0, 18.0))

TILE = {"frame": 10.0, "walls": 10.0, "slabs_broken": 10.0, "debris": 6.0, "rubble": 14.0, "rebar": 2.0}
PREVIEW = "--no-render" not in sys.argv


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


def material(part):
    m = bpy.data.materials.new(part)
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

    c = img("color", False)
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
    for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
        part = ob.name.split(".")[0]
        if part not in TILE:
            raise SystemExit(f"unexpected object {ob.name}")
        ob.name = part
        ob.data.name = part
        box_uv(ob, TILE[part])
        ob.data.materials.clear()
        ob.data.materials.append(material(part))
        lo = [min((ob.matrix_world @ v.co)[i] for v in ob.data.vertices) for i in range(3)]
        hi = [max((ob.matrix_world @ v.co)[i] for v in ob.data.vertices) for i in range(3)]
        stats[part] = dict(tris=tris(ob), studs_per_repeat=TILE[part], px_per_stud=round(1024 / TILE[part], 1),
                           bounds=[round(a, 2) for a in lo + hi])
    stats["total_tris"] = sum(v["tris"] for v in stats.values())
    print(json.dumps(stats))
    json.dump(stats, open(os.path.join(OUT, "m3_stats.json"), "w"), indent=1)

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
    camera(sc, -38, 30, 170.0, 1200)
    render(sc, "prev_34.png")
    camera(sc, -25, 6, 38.0, 1200, center=Vector((10.0, 0.0, 9.0)), span=30.0)
    render(sc, "prev_close.png")


main()
