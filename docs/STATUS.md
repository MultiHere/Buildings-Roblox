# Status

Now: **M1 pushed, waiting for review.** Pushed to `main` and to the session branch `claude/exciting-gauss-qjbc9q`
(same commit). Do not start M2 before the review.

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
| 14 | rebar sticking up top-left, bars hanging from left balcony | missing -> M2 |
| 15 | collapsed slab leaning in the left bay (1st storey), slab piece in the ground-floor left rubble | found, tilted plates |
| 16 | rubble mounds at base, higher at left; rubble on slab edges; chunks on floors | blockout berm only -> M2 |
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

## Numbers (M1)
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
