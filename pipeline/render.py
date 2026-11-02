"""Portfolio renders for one built creature: turntable.png (4 angles), wireframe.png (quads over shading), uv.png.

usage: /opt/bpyenv/bin/python tools/render.py <name> [--res 1000] [--samples 96] [--only turntable|wire|uv]
The creature turns, the camera, lights and backdrop stay put (a real turntable).
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

KEY, FILL, RIM, WORLD = 140.0, 40.0, 160.0, 0.35
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
if not os.path.exists(FONT):  # local Windows runs
    FONT = "C:/Windows/Fonts/segoeuib.ttf"


def backdrop(height):
    """Seamless cyclorama: floor curving up into a back wall (behind +Y)."""
    prof = []
    R = 4.0 * height
    for y in np.linspace(-12 * height, 3 * height, 16):
        prof.append((y, 0.0))
    for a in np.linspace(0, math.pi / 2, 18)[1:]:
        prof.append((3 * height + R * math.sin(a), R * (1 - math.cos(a))))
    prof.append((3 * height + R, R + 10 * height))
    xs = np.linspace(-20 * height, 20 * height, 3)
    verts, faces = [], []
    for x in xs:
        for (y, z) in prof:
            verts.append((x, y, z))
    n = len(prof)
    for i in range(len(xs) - 1):
        for j in range(n - 1):
            a = i * n + j
            faces.append((a, a + 1, a + n + 1, a + n))
    me = bpy.data.meshes.new("cyc")
    me.from_pydata(verts, [], faces)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("cyc", me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("cyc_mat")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.52, 0.52, 0.54, 1)
    b.inputs["Roughness"].default_value = 0.9
    me.materials.append(mat)
    return ob


def area(name, loc, target, energy, color, size):
    L = bpy.data.lights.new(name, "AREA")
    L.energy = energy
    L.color = color
    L.size = size
    L.shape = "DISK"
    o = bpy.data.objects.new(name, L)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o


def setup(name, res, samples):
    nm = name.lower()
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "out", name, "work", f"{nm}.blend"))
    sc = bpy.context.scene
    ob = bpy.data.objects[nm]
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    zmax = max(v.z for v in bb)
    xs = max(abs(v.x) for v in bb)
    ys = max(abs(v.y) for v in bb)
    H = zmax
    R = max(math.hypot(v.co.x, v.co.y) for v in ob.data.vertices)
    span = max(H, 1.7 * R)
    backdrop(H)
    tgt = (0, 0, H * 0.45)
    # 3-point light: warm key front-left-high, cool fill front-right, strong rim from behind
    s = span
    area("key", (-2.2 * s, -2.6 * s, 2.6 * s), tgt, KEY * s * s, (1.0, 0.94, 0.86), 2.2 * s)
    area("fill", (2.8 * s, -1.8 * s, 1.0 * s), tgt, FILL * s * s, (0.84, 0.90, 1.0), 3.0 * s)
    area("rim", (1.2 * s, 2.6 * s, 2.4 * s), tgt, RIM * s * s, (1.0, 0.97, 0.92), 1.4 * s)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.57, 0.62, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = WORLD
    sc.world = world
    cam = bpy.data.cameras.new("cam")
    cam.lens = 85
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    import importlib
    pitch = math.radians(getattr(importlib.import_module(f"creatures.{name}"), "CAMERA_PITCH", 9))
    fov = 2 * math.atan(36 / 2 / cam.lens)
    dist = (span * 0.5 * 1.32) / math.tan(fov / 2)
    co.location = (0, -dist * math.cos(pitch), tgt[2] + dist * math.sin(pitch))
    co.rotation_euler = (Vector(tgt) - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x = res
    sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    return sc, ob


def render_to(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return Image.open(path).convert("RGB")


def label(im, text):
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, max(18, im.width // 40))
    d.text((im.width // 30, im.height - im.width // 14), text, font=f, fill=(235, 235, 238))
    return im


def turntable(name, sc, ob, out, tmp):
    views = [("front 3/4", -30), ("side", -90), ("back 3/4", -150), ("front", 0)]
    ims = []
    for lab, yaw in views:
        ob.rotation_euler = (0, 0, math.radians(-yaw))
        ims.append(label(render_to(sc, os.path.join(tmp, f"tt_{yaw}.png")), lab))
    w, h = ims[0].size
    S = Image.new("RGB", (w * 2, h * 2))
    for i, im in enumerate(ims):
        S.paste(im, ((i % 2) * w, (i // 2) * h))
    S.save(os.path.join(out, "turntable.png"))
    ob.rotation_euler = (0, 0, 0)


def wireframe(name, sc, ob, out, tmp):
    me = ob.data
    if hasattr(me.edges[0], "use_freestyle_mark"):
        me.edges.foreach_set("use_freestyle_mark", [True] * len(me.edges))
    else:  # Blender 5 stores the mark as a generic edge attribute
        at = me.attributes.get("freestyle_edge") or me.attributes.new("freestyle_edge", "BOOLEAN", "EDGE")
        at.data.foreach_set("value", [True] * len(me.edges))
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.0
    vl = sc.view_layers[0]
    fs = vl.freestyle_settings
    ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("wire")
    ls.select_by_visibility = True
    ls.visibility = "VISIBLE"
    ls.select_by_edge_types = True
    for attr in ("select_silhouette", "select_border", "select_crease", "select_contour",
                 "select_external_contour", "select_material_boundary", "select_suggestive_contour",
                 "select_ridge_valley"):
        if hasattr(ls, attr):
            setattr(ls, attr, False)
    ls.select_edge_mark = True
    lst = ls.linestyle or bpy.data.linestyles.new("wire_style")
    ls.linestyle = lst
    lst.color = (0.06, 0.07, 0.10)
    lst.alpha = 0.75
    lst.thickness = 1.1
    fs.crease_angle = math.radians(179)
    # lighter clay-ish base so the lines read: keep the texture but lift it
    mat = me.materials[0]
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    img = [n for n in nt.nodes if n.type == "TEX_IMAGE"][0]
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["Factor"].default_value = 0.45
    mix.inputs["B"].default_value = (0.85, 0.85, 0.86, 1)
    nt.links.new(img.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    ims = []
    for lab, yaw in (("front 3/4", -30), ("back 3/4", -150)):
        ob.rotation_euler = (0, 0, math.radians(-yaw))
        ims.append(label(render_to(sc, os.path.join(tmp, f"wf_{yaw}.png")), lab))
    w, h = ims[0].size
    S = Image.new("RGB", (w * 2, h))
    for i, im in enumerate(ims):
        S.paste(im, (i * w, 0))
    S.save(os.path.join(out, "wireframe.png"))
    sc.render.use_freestyle = False


def uv_sheet(name, ob, out):
    me = ob.data
    nm = name.lower()
    tex = Image.open(os.path.join(out, f"{nm}_albedo.png")).convert("RGB")
    R = tex.width
    big = 2048
    base = tex.resize((big, big), Image.LANCZOS)
    cov = np.load(os.path.join(out, "work", "coverage.npy"))[::-1]
    covm = Image.fromarray((cov * 255).astype(np.uint8)).resize((big, big), Image.NEAREST)
    S = Image.composite(base, Image.new("RGB", base.size, (38, 40, 46)), covm)
    d = ImageDraw.Draw(S)
    uv = me.uv_layers.active.data
    for p in me.polygons:
        pts = [tuple(uv[li].uv) for li in range(p.loop_start, p.loop_start + p.loop_total)]
        pts = [(x * big, (1 - y) * big) for x, y in pts]
        d.line(pts + [pts[0]], fill=(245, 245, 250), width=1)
    S.save(os.path.join(out, "uv.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--res", type=int, default=1000)
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--only", default="all")
    a = ap.parse_args()
    out = os.path.join(ROOT, "out", a.name)
    tmp = os.path.join(out, "work", "renders")
    os.makedirs(tmp, exist_ok=True)
    sc, ob = setup(a.name, a.res, a.samples)
    if a.only in ("all", "uv"):
        uv_sheet(a.name, ob, out)
    if a.only in ("all", "turntable"):
        turntable(a.name, sc, ob, out, tmp)
    if a.only == "test":
        ob.rotation_euler = (0, 0, math.radians(30))
        render_to(sc, os.path.join(out, "work", "test.png"))
    if a.only in ("all", "wire"):
        wireframe(a.name, sc, ob, out, tmp)


if __name__ == "__main__":
    main()
