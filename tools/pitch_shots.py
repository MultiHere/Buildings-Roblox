"""Pitch shots: 3/4 render with the wireframe drawn over the textured model (proves clean low-poly work).

usage (local Blender): blender -b --factory-startup --python tools/pitch_shots.py
Writes out/building01/pitch_wire.png. The texture sheet is made by tools/texture_sheet.py (plain Python).
"""
import math
import os

import bmesh
import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "building01")
CENTER = Vector((26.0, 12.0, 17.0))


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, "building01_textured.glb"))
    wire = bpy.data.materials.new("wire")
    wire.use_nodes = True
    nt = wire.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.02, 0.02, 0.02, 1)
    nt.links.new(em.outputs["Emission"], nt.nodes["Material Output"].inputs["Surface"])
    for ob in [o for o in bpy.context.scene.objects if o.type == "MESH"]:
        w = ob.copy()
        w.data = ob.data.copy()
        bpy.context.scene.collection.objects.link(w)
        # draw the modelled polygons: flat neighbouring triangles merged (Roblox triangulates on import anyway;
        # the triangle count goes in the message), so the overlay shows shapes, not a fan of slivers
        bm = bmesh.new()
        bm.from_mesh(w.data)
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(2), verts=bm.verts, edges=bm.edges)
        bm.to_mesh(w.data)
        bm.free()
        m = w.modifiers.new("wire", "WIREFRAME")
        m.thickness = 0.035
        m.use_replace = True
        w.data.materials.clear()
        w.data.materials.append(wire)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.8, 0.82, 0.86, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52), 0, math.radians(-30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    a = math.radians(-35)
    cam.location = Vector((CENTER.x + 150 * math.sin(a), CENTER.y - 150 * math.cos(a), 32))
    cam.rotation_euler = (CENTER - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 36 * 150 / 95
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1066
    sc.render.filepath = os.path.join(OUT, "pitch_wire.png")
    bpy.ops.render.render(write_still=True)


main()
