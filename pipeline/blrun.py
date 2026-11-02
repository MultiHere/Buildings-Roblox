"""Run a pipeline script inside an installed Blender's Python (local Windows runs, no bpy wheel).

usage: blender -b --factory-startup --python-exit-code 1 --python tools/blrun.py -- tools/build.py <name> [args]
Pillow for Blender's Python lives in .vendor311/ (pip install --target .vendor311 pillow).
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:]
script = os.path.abspath(argv[0])
sys.path[:0] = [os.path.dirname(script), HERE, os.path.join(HERE, "..", ".vendor311")]
sys.argv = [script] + argv[1:]
runpy.run_path(script, run_name="__main__")
