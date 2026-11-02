"""Detail bake: procedural scales / plates / creases on a dense copy, baked to the game mesh.

usage (through blrun.py): tools/bake.py <name> [--size 2048] [--strength 1.0]
Writes out/<name>/<name>_normal.png (OpenGL tangent space, as Roblox wants) and <name>_albedo_detail.png (albedo
darkened in the baked creases), both 1024. The game mesh and its UVs are untouched.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402


def log(*a):
    print("[bake]", *a, flush=True)


def tex(name, kind, **props):
    t = bpy.data.textures.new(name, kind)
    for k, v in props.items():
        setattr(t, k, v)
    return t


def displace(ob, t, strength, mid=0.5, scale=1.0):
    m = ob.modifiers.new(t.name, "DISPLACE")
    m.texture, m.strength, m.mid_level, m.texture_coords = t, strength, mid, "OBJECT"
    return m


def bake_image(name, size):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--strength", type=float, default=1.0)
    a = ap.parse_args(sys.argv[1:])
    nm = a.name
    out_dir = os.path.join(HERE, "..", "out", nm)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out_dir, "work", f"{nm}.blend"))
    low = bpy.data.objects[nm]
    span = max(low.dimensions)
    s = a.strength * span / 1.6  # strengths tuned on a 1.6 m creature

    # dense copy with layered surface detail
    high = low.copy()
    high.data = low.data.copy()
    high.name = f"{nm}_high"
    bpy.context.collection.objects.link(high)
    sub = high.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 3
    # big rock plates / scales: voronoi cells, raised centres and sunken edges
    displace(high, tex("plates", "VORONOI", distance_metric="DISTANCE", noise_scale=0.045 * span / 1.6,
                       weight_1=1.0, weight_2=-1.0, weight_3=0.0, noise_intensity=1.6), 0.010 * s, mid=0.25)
    # creases and folds
    displace(high, tex("folds", "CLOUDS", noise_basis="BLENDER_ORIGINAL", noise_scale=0.12 * span / 1.6,
                       noise_depth=3, noise_type="HARD_NOISE"), 0.008 * s)
    # fine pebbled skin
    displace(high, tex("pebble", "STUCCI", noise_scale=0.012 * span / 1.6, turbulence=6.0, stucci_type="WALL_OUT"),
             0.0025 * s)
    for m in high.modifiers:
        log("modifier", m.name)
    dg = bpy.context.evaluated_depsgraph_get()
    log("high poly faces:", len(high.evaluated_get(dg).data.polygons))

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 16
    bk = sc.render.bake
    bk.use_selected_to_active, bk.cage_extrusion, bk.max_ray_distance = True, 0.03 * span / 1.6, 0.06 * span / 1.6
    bk.margin = 8

    mat = low.data.materials[0]
    nt = mat.node_tree
    results = {}
    for kind, cs in (("NORMAL", "Non-Color"), ("AO", "Non-Color")):
        img = bake_image(f"{nm}_{kind.lower()}", a.size)
        img.colorspace_settings.name = cs
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        nt.nodes.active = node
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        if kind == "NORMAL":
            bk.normal_space = "TANGENT"
            bk.normal_r, bk.normal_g, bk.normal_b = "POS_X", "POS_Y", "POS_Z"  # OpenGL (+Y), what Roblox reads
        sc.cycles.samples = 1 if kind == "NORMAL" else 32
        bpy.ops.object.bake(type=kind)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(a.size, a.size, 4)[..., :3]
        results[kind] = px
        nt.nodes.remove(node)
        log("baked", kind)

    from PIL import Image
    def save(arr, path):
        im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8)[::-1])  # Blender rows are bottom-up
        im.resize((1024, 1024), Image.LANCZOS).save(path)
        log("wrote", os.path.basename(path))

    save(results["NORMAL"], os.path.join(out_dir, f"{nm}_normal.png"))
    alb = np.asarray(Image.open(os.path.join(out_dir, f"{nm}_albedo.png")).convert("RGB").resize(
        (a.size, a.size), Image.LANCZOS), np.float32)[::-1] / 255.0
    ao = results["AO"].mean(-1, keepdims=True)
    detail = alb * (0.35 + 0.65 * ao ** 1.3)  # deep creases go dark, raised plates keep the paint
    save(detail, os.path.join(out_dir, f"{nm}_albedo_detail.png"))


main()
