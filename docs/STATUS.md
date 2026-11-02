# Status

Now: **M2 pushed, waiting for review.** Pushed to `main` and to the session branch `claude/ecstatic-gates-7zy3q8`
(same commit). Do not start M3 before the review.

## M2 - damage, rubble, rebar (done-checks all pass)
Built on the approved M1 grid (`tools/build_building01.py`, extended, not rebuilt). Method (D6): damage is cut with
jagged polygon prisms (exact boolean): 39 cutters on `walls`, 46 on `frame`. Rubble heaps are low-poly heightfields
(jittered grid + Delaunay), chunks are convex hulls of jittered box corners, rebar is 4-sided tubes on bent polylines.
A hidden-face pass then deletes every face that sits fully inside another solid or under the ground (ray parity, 3
rays): 2,988 triangles deleted, incl. all contact faces between parts. Weighted normals (face area, sharp > 30 deg)
are applied and exported as custom normals.

M1 review fixes:
1. Edge beams: front + left balcony edge band now 2.2 deep (1.2 downstand under the 1.0 slab) on L1 and L2, in
   `frame`. The top is broken by 10 edge wedges and 18 plan notches. Rubble piles sit on the band; the front beam
   reaches 0.2 into the infill wall so the wall top steps behind it (no coplanar contact).
2. Standing top wall: 19.9 studs wide (~1.4 bays, M1 17.4), x 12.5 .. 32.45. Jagged broken top, stepped lower on
   the left, ragged left edge, 2 big ragged holes, 13 small shell holes (8 through, 5 blind pits half the wall deep).
   3 bars stick out of the top.
3. Columns 1.9 x 1.9 (M1 1.6). 8 front-line corner chips. Broken jagged tops (two tilted facets + a chipped
   corner) on the top-left stump, the right stub column and the back-left column under the missing roof corner.

M2 scope:
- Ragged openings: every front/back/side opening is a jagged polygon (facets about 1.3 long, +-0.45 off the line,
  broken corners). Sides that run into a column or slab stay straight inside it. The wall chunk tops (corner chunk,
  right stub) are jagged too, and so are the walls under the missing roof corner.
- Slabs: chipped notches and broken edge tops along the front and the left balcony, broken balcony ends at the
  front-left on L1 and L2, roof corner removal now jagged (M1 rectangle).
- `slabs_broken` (5 pieces, all with broken outlines): the hanging slab, hinged on the left edge of a jagged hole in
  the L1 slab and hanging 66 deg down into the ground-floor left bay onto a rubble heap. The M1 leaning plate (L1)
  and the collapsed plate (ground) are kept. Also a balcony end hanging from the L1 front-left break and a roof piece
  hanging at the L2 back-left break.
- `rebar` (36 bars, 4-sided, r 0.1): 6 tall bent bars on the top-left stump, 6 out of the balcony breaks bent down,
  3 hanging off the left balcony beam, 5 drooping out of the roof break, 5 at the hanging slab hinge and hole edge,
  plus a few on the stub column, the standing wall top, the back-left column and the front edge. Bar segments
  inside concrete are deleted.
- `rubble`: base heaps on all 4 sides, highest at the front-left (5.6-6.1), about 3.5 mid-front, lower right
  (2.8) and back (1.6). Sides are steep (about 45 deg) to stay inside the reference outline. One heap under the
  hanging slab and piles along the slab edges on L1 and L2 (front + balcony). 330 chunks on the heaps (some 2.2-3.0
  big) and chunks along the slab edges, some hanging over the edge.
- `debris`: 108 loose chunks and blocks on the ground floor, L1 and the roof (crowded at the front), 18 on the heap
  foot, and 6 broken slab plates.

## Numbers (M2)
| part | tris | BRIEF budget | small faces (< 0.05 sq) | hidden faces deleted |
|---|---|---|---|---|
| frame | 1,595 | 7,000 | 49 | 208 |
| walls | 1,844 | 7,000 | 23 | 337 |
| slabs_broken | 306 | 3,000 | 0 | 38 |
| rubble | 6,430 | 9,000 | 29 | 2,123 |
| debris | 1,844 | 3,000 | 43 | 156 |
| rebar | 714 | 1,000 | 66 | 126 |
| **total** | **12,733** | 35,000 (aim 30,000) | share **1.6 %** (limit 10 %) | 2,988 |

- Every part is under its budget. Total is 12.7k: there is room for M3 or the client (decision D7).
- Mesh: 0 duplicate verts (merge 0.001), 0 zero-area faces, 0 loose verts, 0 non-manifold edges in every part.
  Open edges (frame 253, walls 256, rubble 2,608, ...) are only where hidden faces were deleted: contacts with other
  parts, the ground, and rubble buried in rubble.
- Faces fully inside another part: 0 (deleted by the hidden-face pass).
- Z-fighting: 0 coplanar overlapping face pairs between parts (axis-aligned check, tolerance 0.01). Smallest gap
  between parallel overlapping faces of different parts: **0.059 studs** (>= 0.01).
- Silhouette IoU **0.856** (target 0.78); bbox aspect ref 1.50, render 1.53. `out/building01/sil_diff.png`.
- Bounds (studs): x -11.3 .. 61.4, y -11.6 .. 35.1, z -0.8 .. 45.7 (rubble chunks sink up to 0.8 below the ground;
  their faces under the ground are deleted).
- Avatar 2 x 5.5 x 1 (grid check, rubble not counted): walks through all 4 ground-floor front bays; stands on the
  ground slab, L1 and L2 (bay 1).
- Export: FBX `global_scale=0.01, apply_unit_scale=True` (unchanged), `mesh_smooth_type=OFF` (custom normals).
  Re-import: 6 objects `frame walls slabs_broken rubble debris rebar`, custom normals present, 0.727 x 0.468 x 0.465
  in the file's cm units = 72.7 x 46.8 x 46.5 studs. That is the same convention as M1; Studio scale is checked at
  M3.
- Files: `out/building01/` building01.fbx/.glb (plain greys, no UVs yet), **m2_sheet.png** (ref | ref-cam | 3/4 |
  wireframe 3/4), ref_cam.png, view_34.png, view_34_wire.png, view_side.png, view_back.png, sil_diff.png,
  m2_stats.json, work/building01.blend. Run: `/opt/bpyenv/bin/python tools/build_building01.py` (about 6 s) then
  `/opt/bpyenv/bin/python tools/render_ref_cam.py` (about 50 s).

## Decisions M2 (defaults picked)
- D6 Damage as exact-boolean jagged prisms on the M1 grid solids. The grid keeps a hole shrunk by 0.6 on the jagged
  sides, so the avatar check still works on the grid and the jagged outline is all that shows.
- D7 Kept the triangle count low (12.7k vs aim 30k) and did not add detail for its own sake. Pitting, cracks and
  soot go in the M3 textures as the rules say. If the reviewer wants denser rubble or more broken edges, the counts
  are single numbers in `build_rubble` / `build_debris`.
- D8 The rubble footprint is kept tight: about 4-6 studs past the building sides. The first wider version gave
  IoU 0.695 with aspect 1.87.
- D9 Slab tops under rubble piles are not cut out: they are part of large merged faces, and cutting them would add
  triangles instead of saving them.

## M1 (approved base, kept)
M1: blockout 1,768 tris, IoU 0.859, decisions D1-D5 below, review fixes in `docs/REVIEW_M1.md` (done in M2).

## Reference read (ref/building1_ref_small.png, 399x266; no full-size ref yet) -> M1 found / missing
| # | feature in the reference | M1 |
|---|---|---|
| 1 | RC column-and-slab frame, 5 column lines across, 3 deep | found (columns 1.6 x 1.6) |
| 2 | 2 complete storeys (ground + 1st), 3rd-level slab present, 3rd storey destroyed | found (see decision D1) |
| 3 | 4 front bays, right bay visibly narrower | found, bays 17 / 14 / 14 / 11 (56 total) |
| 4 | slabs stick out past the columns at the front | found, 0.8 past column face |
| 5 | left: both slabs overhang like thin balconies | found, 4.0 studs (broken ends -> M2) |
| 6 | infill walls mostly blown out, chunks left at bay edges | found, straight cuts (ragged -> M2) |
| 7 | 1st storey, right bay: wall mostly intact with one window hole | found |
| 8 | sky visible through 1st storey bays 1 and 3 (back wall holed) | found (back-wall holes) |
| 9 | dark interior behind the other openings | found (back + side walls present) |
| 10 | tall standing wall left of centre, ~1 storey+, 3-5 holes, broken top | found, top z = 44, 1 big + 4 small holes, stepped top |
| 11 | top-right room frame: column + lintel | found (mid column, column on line 3, lintel, side beam stub) |
| 12 | short wall stub far right | found (+ short column) |
| 13 | top-left corner pier (column stump + wall chunk) | found, z = 39 |
| 14 | rebar sticking up top-left, bars hanging from left balcony | M2: found |
| 15 | collapsed slab leaning in the left bay (1st storey), slab piece in the ground-floor left rubble | found; M2 adds the hanging slab |
| 16 | rubble mounds at base, higher at left; rubble on slab edges; chunks on floors | M2: found |
| 17 | shell pitting, soot in openings, light fresh breaks, dusty grey-brown | textures -> M3 |

## Decisions (defaults picked, all in the config dict at the top of tools/build_building01.py)
- D1 Reference proportions over BRIEF numbers: floor-to-floor **14** (BRIEF 12), standing wall top **44** (BRIEF ~34),
  left overhang **4.0** (BRIEF 2.5; ref measures ~5), bays 17/14/14/11 (BRIEF 4 x 14; same 56 total). Measured from
  the ref: roof-slab height / facade width ~ 0.5 and wall above the roof ~ 1.2 storeys. With 12 / 34 the outline
  was too flat. If the client's scale needs 12-stud floors, change `floor_h` and the three `*_top` values.
- D2 Read as 2 complete storeys + destroyed 3rd (BRIEF says "ground + 2 floors complete"); the ref shows 2 rows of bays
  under the standing pieces.
- D3 A low blockout rubble berm is already in M1 (75 tris) because the reference outline includes the base rubble;
  M2 replaces it.
- D4 Modelling method: one labelled box grid; faces only between a filled and an empty cell, then planar dissolve +
  triangulate. Parts never share coplanar faces, hidden faces (wall ends in columns, wall tops under slabs, ground
  contact) are never made. M2 jagged cuts go on top of these meshes.
- D5 Ref camera found by search on silhouette IoU: azimuth -16 deg (front-left), height 9 studs (slightly low),
  distance 220 (`out/building01/work/ref_cam.json`).

### Numbers (M1)
- Tris: frame 1,083 - walls 586 - slabs_broken 24 - rubble 75 - **total 1,768** (limit 18,000 at M1).
- Bounds (studs): x -10.0 .. 60.0, y -13.9 .. 29.1, z 0.0 .. 44.0 (building 56 x 28 between column centres).
- Silhouette IoU **0.859** (target 0.70); bbox aspect ref 1.50, render 1.53. `out/building01/sil_diff.png`.
- Avatar 2 x 5.5 x 1: walks through all 4 ground-floor front bays; stands on ground slab (z 0.5), level-1 slab
  (z 14) and level-2 slab (z 28). Clear storey height 12.5 / 13.
- Mesh: 0 duplicate verts, 0 zero-area faces, 0 edges < 0.05 studs, 0 non-manifold edges. Open edges (frame 225,
  walls 243, rubble 25) are only where hidden faces against another part or the ground were deleted (intended).
- Smallest layer gap: no stacked/coplanar layers between parts in M1 (by construction); the fallen slab plates are
  tilted, they cross the slabs, never coplanar.
- Export factor: FBX `global_scale=0.01, apply_unit_scale=True` (lesson value). Raw FBX coordinates are studs
  (max 56.4). Blender re-import reads the file unit as cm -> 0.70 x 0.43 x 0.44 m. **Reviewer: please confirm Studio
  imports it as ~70 x 43 x 44 studs.**
- Files: `out/building01/` building01.fbx/.glb (blockout, plain grey), m1_sheet.png, ref_cam.png, view_34/side/back.png,
  sil_diff.png, m1_stats.json, work/building01.blend. Render 900 px, Cycles 48 spp.

## Open
- Full-size reference may arrive as `ref/building1_ref.png` (render script picks it up automatically).
- Client's game scale unknown (D1).
- Tool notes: in the bpy wheel `import bmesh` only works after `import bpy`; Workbench/EEVEE need libEGL (missing on
  the VM), so the camera search uses 1-sample Cycles for the alpha mask.
