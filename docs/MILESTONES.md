# Milestones - building 01

One cloud chat per milestone. Each ends: commit, push, `docs/STATUS.md`, AskUserQuestion, wait for the review.
Done-checks are measured by script and written in STATUS with the numbers. A check that fails 3 times = stop and ask.

## M1 - structure matched to the reference (time box 60 min)
Build: `tools/build_building01.py` (bmesh, re-runnable, all sizes from one config dict at the top). Frame (columns,
slabs, overhangs), wall chunks with the big openings cut, the standing top wall with its holes, the top-right room
frame and wall stub. Blockout-level damage only (straight cuts are fine here). Plain grey materials.
Also: `tools/render_ref_cam.py` renders the building from a camera that matches the reference (front-left, slightly
low, same framing), white background, plus a 3/4, side and back view.
Done-checks:
- Object names and per-part triangle counts printed; total <= 18,000 at this stage.
- Floors, bays, overhangs and standing pieces match the BRIEF list (write each one in STATUS as found / missing).
- `python tools/silhouette.py ref/<ref> out/building01/ref_cam.png --out out/building01/sil_diff.png` IoU >= 0.70.
- An avatar box (2 x 5.5 x 1 studs) fits through a ground-floor bay and stands on each slab (bounds check).
- `out/building01/m1_sheet.png`: ref | ref-cam render | sil_diff | 3/4 view, one row, <= 1200 px wide.

## M2 - damage, rubble, rebar (time box 75 min)
Ragged opening edges (jagged polygon outlines, not noise displacement), chipped slab edges and broken balcony ends,
the hanging slab in the ground floor, bent rebar at breaks and the top-left corner, rubble mounds (base higher on the
left, piles on slab edges) and loose debris. Delete hidden faces. Weighted normals.
Done-checks:
- Total tris < 35,000 (aim 30,000), every part < 20,000, budgets per part from BRIEF within +20%.
- No zero-area faces, no loose verts, no duplicate verts (merge by 0.001), no faces fully inside another part.
- Silhouette IoU >= 0.78.
- Wireframe render: no triangle soup (report the share of faces with area < 0.05 sq studs; keep it under 10%).
- `out/building01/m2_sheet.png`: ref | ref-cam render | 3/4 | wireframe 3/4.

## M3 - UVs, textures, export (time box 75 min)
UV each part (smart project or cube projection at world scale for concrete; no overlaps inside a part); texel
density consistent. Bake per part at 1024: colour from the CC0 tileables + AO + soot in openings + dust on tops +
lighter fresh breaks; normal (OpenGL) with the tileable normal + shrapnel pitting; roughness. Rebar gets metalness.
Export `out/building01/building01.fbx` + `.glb`, one object per part, names kept, textures beside it.
Done-checks:
- UV overlap 0 inside each part; texel density spread (max/min px per stud) <= 1.5 on the big parts.
- Re-import the FBX in a clean scene: same object count, names, tris; bounds in studs match the BRIEF size +-5%.
  Write the export factor in STATUS.
- Textures are 1024, PNG, no seams visible at the break edges in the 3/4 render (look once).
- `out/building01/sheet.png` (final: ref | ref-cam textured | 3/4 | side | back | wireframe | UV of `frame`) and
  `stats.md` per BRIEF.
