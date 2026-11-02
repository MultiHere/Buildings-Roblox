"""Write out/SHEET.md: one row per built creature, numbers read from the exported files via stats.py.

usage: /opt/bpyenv/bin/python tools/sheet.py
"""
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

ORDER = ["pebbloon", "emberlotl", "clovern", "ripplefin", "zippit", "frostmoth", "wispurr", "fungoad", "skyray",
         "brasshorn"]


def field(text, name):
    m = re.search(r"\| " + re.escape(name) + r" \| (.+?) \|", text)
    return m.group(1) if m else "-"


def main():
    rows = []
    for nm in ORDER:
        p = os.path.join(ROOT, "out", nm, "stats.md")
        mod = importlib.import_module(f"creatures.{nm}")
        if not os.path.exists(p) or not hasattr(mod, "REVIEW"):
            rows.append(f"| {mod.NAME} | {mod.TYPE} | {mod.PLAN} | - | - | - | - | not finished (see docs/NEXT.md) |")
            continue
        t = open(p).read()
        score = mod.REVIEW["score"]
        score = f"{score}" + ("" if score >= 8 else " (draft, below the bar)")
        rows.append(f"| [{mod.NAME}]({nm}/) | {mod.TYPE} | {mod.PLAN} | {field(t, 'triangles (GLB)')} | "
                    f"{field(t, 'texture').split(',')[0].replace('1 x ', '')} | {field(t, 'UV overlap').split(' ')[0]} | "
                    f"{field(t, 'height').split(' = ')[-1].split(' at')[0]} | {score} |")
    lines = [
        "# Creature pack sheet",
        "",
        "Measured from the exported GLB files (see each `stats.md`). Score is my own review against the reference,",
        "1-10; under 8 means it needs another pass (see docs/NEXT.md). Made with scripted Blender (SDF sculpt, Quadriflow retopo, scripted UVs,",
        "procedural hand-painted texture) with AI assistance.",
        "",
        "| name | type | body plan | tris | texture | UV overlap (texels) | height | score |",
        "|---|---|---|---|---|---|---|---|",
    ] + rows + [""]
    open(os.path.join(ROOT, "out", "SHEET.md"), "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
