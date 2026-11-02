"""Renders of building 01: reference camera (white background), 3/4, side, back, wireframe; camera search; sheet.

usage: /opt/bpyenv/bin/python tools/render_ref_cam.py [--tune] [--res 900] [--samples 48] [--sheet m1_sheet.png]
--tune  searches azimuth / height / distance for the best silhouette IoU against the reference (1-sample
        Cycles renders) and writes the winner to out/building01/work/ref_cam.json; without it that file is reused.
Reads out/building01/work/building01.blend. Lights reuse pipeline/render.py's area() rig (Standard view transform).
"""
import argparse
import itertools
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "pipeline")]
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from render import area  # noqa: E402  (pipeline/render.py)
from silhouette import mask  # noqa: E402

OUT = os.path.join(ROOT, "out", "building01")
WORK = os.path.join(OUT, "work")
REF = os.path.join(ROOT, "ref", "building1_ref.png")
if not os.path.exists(REF):
    REF = os.path.join(ROOT, "ref", "building1_ref_small.png")
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
CENTER = Vector((28.0, 14.0, 18.0))


def bounds():
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in bpy.data.objects:
        if o.type == "MESH":
            for c in o.bound_box:
                v = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, v))
                hi = Vector(map(max, hi, v))
    return lo, hi


def camera(sc, az, height, dist, res, aspect=1.5):
    """az: degrees from straight-on front (-y), negative = camera to the left. Lens fits the bounds."""
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    a = math.radians(az)
    loc = Vector((CENTER.x + dist * math.sin(a), CENTER.y - dist * math.cos(a), height))
    cam.location = loc
    d = CENTER - loc
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36
    cam.data.clip_end = 2000
    lo, hi = bounds()
    span = max(hi.x - lo.x, hi.y - lo.y, (hi.z - lo.z) * aspect) * 1.25
    cam.data.lens = 36 * d.length / span
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res / aspect)
    return cam


def scene_setup(fast, samples):
    sc = bpy.context.scene
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    if fast:
        sc.render.engine = "CYCLES"  # Workbench/EEVEE need EGL, not on the cloud VM; 1 sample = clean alpha
        sc.cycles.device = "CPU"
        sc.cycles.samples = 1
        sc.cycles.use_denoising = False
    else:
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        w = bpy.data.worlds.new("w")
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.78, 0.85, 1)
        w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
        sc.world = w
        sun = bpy.data.lights.new("sun", "SUN")
        sun.energy = 1.6
        sun.angle = math.radians(3)
        so = bpy.data.objects.new("sun", sun)
        sc.collection.objects.link(so)
        so.rotation_euler = (math.radians(50), 0, math.radians(-35))
        area("fill", (-60, -90, 40), tuple(CENTER), 6000.0, (0.9, 0.93, 1.0), 40)
    return sc


def render(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    Image.alpha_composite(bg, im).convert("RGB").save(path)


def iou(path, ref_mask):
    o, oa = mask(path)
    return (ref_mask & o).sum() / max(1, (ref_mask | o).sum()), oa


def tune(sc):
    r, ra = mask(REF)
    best = None
    tmp = os.path.join(WORK, "tune.png")
    grid = itertools.product([-30, -20, -12, -6, 0], [6, 12, 18, 24], [80, 130, 220])
    for az, hgt, dist in grid:
        camera(sc, az, hgt, dist, 400)
        render(sc, tmp)
        s, oa = iou(tmp, r)
        if best is None or s > best[0]:
            best = (s, az, hgt, dist, oa)
    # local refine
    s0, az, hgt, dist, _ = best
    for daz, dh, dd in itertools.product([-4, 0, 4], [-3, 0, 3], [0.8, 1.0, 1.25]):
        camera(sc, az + daz, hgt + dh, dist * dd, 400)
        render(sc, tmp)
        s, oa = iou(tmp, r)
        if s > best[0]:
            best = (s, az + daz, hgt + dh, dist * dd, oa)
    print(f"tune: IoU {best[0]:.3f} az {best[1]} height {best[2]} dist {best[3]:.0f} (aspect ref {ra:.2f} "
          f"render {best[4]:.2f})")
    cam = dict(az=best[1], height=best[2], dist=best[3], iou_fast=float(best[0]))
    json.dump(cam, open(os.path.join(WORK, "ref_cam.json"), "w"))
    return cam


def label(im, text):
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype(FONT, max(12, im.width // 28))
    except OSError:
        f = ImageFont.load_default()
    d.text((8, 6), text, fill=(20, 20, 20), font=f)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--res", type=int, default=900)
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--sheet", default="m2_sheet.png")
    a = ap.parse_args()
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, "building01.blend"))
    if a.tune:
        tune(scene_setup(True, 0))
        bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, "building01.blend"))
    cam = json.load(open(os.path.join(WORK, "ref_cam.json")))
    sc = scene_setup(False, a.samples)
    views = [("ref_cam", cam["az"], cam["height"], cam["dist"]), ("view_34", -45, 30, 140),
             ("view_side", -90, 14, 130), ("view_back", 160, 20, 140)]
    for name, az, hgt, dist in views:
        camera(sc, az, hgt, dist, a.res)
        render(sc, os.path.join(OUT, name + ".png"))
        print("rendered", name)
    # wireframe 3/4: view-layer material override with a 1-px Cycles wireframe over flat grey
    wm = bpy.data.materials.new("wire")
    wm.use_nodes = True
    nt = wm.node_tree
    nt.nodes.clear()
    wf, mix, out = nt.nodes.new("ShaderNodeWireframe"), nt.nodes.new("ShaderNodeMixShader"), \
        nt.nodes.new("ShaderNodeOutputMaterial")
    wf.use_pixel_size, wf.inputs["Size"].default_value = True, 1.0
    dif, ink = nt.nodes.new("ShaderNodeBsdfDiffuse"), nt.nodes.new("ShaderNodeEmission")
    dif.inputs["Color"].default_value = (0.75, 0.75, 0.75, 1)
    ink.inputs["Color"].default_value = (0.02, 0.02, 0.05, 1)
    nt.links.new(wf.outputs[0], mix.inputs[0])
    nt.links.new(dif.outputs[0], mix.inputs[1])
    nt.links.new(ink.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    sc.view_layers[0].material_override = wm
    camera(sc, -45, 30, 140, a.res)
    render(sc, os.path.join(OUT, "view_34_wire.png"))
    sc.view_layers[0].material_override = None
    print("rendered view_34_wire")
    # sheet: ref | ref-cam render | 3/4 | wireframe 3/4, one row, <= 1200 px wide (silhouette diff saved apart)
    os.system(f"{sys.executable} {os.path.join(HERE, 'silhouette.py')} {REF} {os.path.join(OUT, 'ref_cam.png')} "
              f"--out {os.path.join(OUT, 'sil_diff.png')}")
    tiles = [("reference", REF), ("ref camera", os.path.join(OUT, "ref_cam.png")),
             ("3/4", os.path.join(OUT, "view_34.png")), ("wireframe 3/4", os.path.join(OUT, "view_34_wire.png"))]
    th = 300
    ims = []
    for t, p in tiles:
        im = Image.open(p).convert("RGB")
        im = im.resize((int(im.width * th / im.height), th), Image.LANCZOS)
        ims.append(label(im, t))
    sheet = Image.new("RGB", (sum(i.width for i in ims) + 4 * (len(ims) - 1), th), "white")
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width + 4
    if sheet.width > 1200:
        sheet = sheet.resize((1200, int(th * 1200 / sheet.width)), Image.LANCZOS)
    sheet.save(os.path.join(OUT, a.sheet))
    print("sheet", sheet.size)


if __name__ == "__main__":
    main()
