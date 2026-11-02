# Lessons (running log)

Every failure or bad-looking result, what happened and the fix. Newest at the bottom of each day.

## 2026-10-26 setup
- download.blender.org is blocked by the network policy (403 on CONNECT). apt only has Blender 4.0.2. Fix: the
  official `bpy` wheel from PyPI (5.2.3) in a venv at `/opt/bpyenv`. Quadriflow, Cycles CPU, Freestyle and GLB/FBX
  export all work headless with it.
- `bpy.types.CyclesRenderSettings` is not exposed in the wheel; read settings off `scene.cycles` instead.
- `uv.unwrap` on a closed sphere with no seams fails ("failed to solve 1 of 1 island"): every closed part needs a cut.

## 2026-10-26 Pebbloon (first creature, pipeline shake-out)
- First turntable was blown out white: area-light power in the 1000s of W at 1.6 m scale. Fix: key 140, fill 40,
  rim 160 (x span^2) and "Standard" view transform. Always do a one-view `--only test` render before the 4-up.
- Painted shadows (value x0.70 + AO 0.85) plus real Cycles lighting doubled the darkness; the creature read muddy.
  Fix: painted shadow value 0.80, AO strength 0.70. The albedo carries the mood, the lights carry the form.
- The face UV island cut through the outer eye outlines (seam across a painted eye). Fix: FACE_REGION must contain
  every painted face mark with margin; check the uv.png, not just the render.
- 6 open edges: the feet dipped 1 cm below the marching-cubes grid, so the dense mesh was clipped and Quadriflow left
  two triangle holes. Fix: grid padded by 4 cells, `march` raises if the field touches the boundary, the build
  raises on any open edge, and the mesh is grounded (min z = 0) only at export.
- Small parts (moss blobs, the thin hat rim) facet at ~2.5k quads because Quadriflow spaces quads evenly. Fix: fewer,
  larger small shapes and ~3.4k quads (6.3k tris).
- Freestyle edge marks moved in Blender 5: `use_freestyle_mark` is gone, it is a boolean edge attribute
  `freestyle_edge`. A new lineset also has no linestyle until one is assigned.
- UV stretch: SLIM ("minimum stretch") balanced angle and area (anisotropy 1.32, 82% in density band); ABF kept
  angles (1.07) but crushed the underside between the feet holes. The real fix was topology of the cut, not the
  solver: an automatic sole shell (down-facing faces of the body), ABF, and apex-to-boundary relief cuts on the
  worst island. Result 1.05 mean anisotropy, 0 overlap. "Cut next to the worst vertex" relieved nothing (1-edge cuts).
- A `cmd | grep` chain hides failures: a failed build fell through to stats and renders of the old mesh. Use
  `set -o pipefail` and check PIPESTATUS before the next step.
- The design bounds guard fired when the top stone grew: widen `bounds` in the creature module, never pad the guard.
- UV usage stuck at ~51-53% whatever the packer settings (concave/convex/AABB, rotate any): islands with holes are
  the limit. Accept for blobs, or merge foot domes into the sole shell when usage matters more than stretch.

## 2026-10-26 Emberlotl
- Gill fronds read as thorns: tapered round cones are spikes. Flames need a fat middle and a curled tip (4-point
  tube, radii 0.075 / 0.112 / 0.075 / 0.02) and colour that runs ember -> orange -> gold -> pale tip.
- Lumpy "melted" rims on flattened parts: `Tube` smooth-unioned its own segments and every smooth-min joint adds a
  bulge. Consecutive round cones that share end spheres are already smooth; Tube now uses plain union (k=0).
- Painted shadow turned the gold flame tips khaki. Flames are the light of the design: blend most of the unshaded
  colour back on emissive-looking parts (no emission in the material, Roblox and the brief say no neon).
- Self-overlapping UV islands with zero flipped faces: ABF folds in concave notches (between two gill fronds, at the
  end of a rim cut). Fixes in order: give each frond its own part (seam in the crease), rim cuts to split flat parts
  into front/back shells, then per-island fallbacks RELAX -> SLIM -> conformal -> isolate the folded faces.
- With UV sync selection on (Blender 5 default), `uv.select_all` selects the whole mesh: a "local" minimize_stretch
  relaxed all 30 islands and stretch jumped from 1.06 to 1.23. Select faces, edges and vertices explicitly, never
  call uv.select_all inside a per-island fix. Proved with a probe that counts changed loops outside the island (0).
- Camera framing from the bounds box put a long creature small in frame. Recentre Y at export and frame on the
  real horizontal radius.
- Torn / crumpled flame tips and wobbly ear rims: any part thinner than ~1.5 quad edges (about 4 cm at 3.5-4k quads
  on a 1.5 m creature) cannot be held by Quadriflow and the surface projection pulls vertices through it. Rule:
  minimum full thickness ~6-7 cm, tip radius >= 0.04 m. Thin looks come from the painted edge, not the geometry.
- Quadriflow overshoots the face target by up to ~3% (3900 -> 4025 quads = 8,050 tris). Aim 3800 for an 8k cap.
- `split_concave` used to overwrite the cached retopo, so every UV rerun added triangles. The post-UV mesh now goes
  to final.npz; low.npz stays the pristine Quadriflow result.
- One gill collapsed into a stalk with a bulb while its mirror twin was fine. Measured: 63 vs 93 vertices on the two
  sides. Quadriflow's `use_mesh_symmetry` had no effect at all (same output with it on and off). Fix: retopo only the
  x >= 0 half and mirror it: march a half SDF capped by a plane, Quadriflow it, delete the cap faces, snap the open
  border to x = 0, mirror-weld. Mirror mismatch went from 0.019 m mean to 0.0000, both gills 118 vertices.
- Quadriflow refuses non-manifold input ("needs to be manifold and have consistent normals"). Two causes found: a cap
  plane lying exactly on the marching-cubes sample plane (degenerate triangles; offset it 0.35 cell), and some
  decimation ratios. The build now retries cap offset / decimation combinations. On a 264k-tri input it also
  returned FINISHED with the mesh untouched, so always decimate to ~60k first and check the face count.
- Faces lying in the mirror plane (thin fin rims) get doubled by the mirror and leave non-manifold edges; they can
  appear only after the border snap. Remove in-plane faces after the weld, then loose edges and vertices.
- My own tooling misled me: after the concave-quad split the edge order changed, but the export applied the seam
  flags by index, so the .blend had wrong seams and the island viewer showed one island. Seams are now stored as
  vertex pairs. A debugging view that disagrees with the measurement is a bug in the view until proven otherwise.
- Deviation from RESEARCH.md topology rule 2 (eye loops from sculpted sockets): not done. The reference's eyes are
  painted flush on a smooth head, and a socket ring would bend the painted eye. The meshes therefore have an even
  quad grid over the face, fine for a painted-eye game creature, not set up for blink morphs. Next step if a client
  needs facial animation: a guided retopo with an eye-ring curve field, or hand-placed loops.
- UV folds at the rounded tips of a thin fin on the mirror plane survived relax, SLIM, conformal and bisection.
  The guaranteed last step gives the folding faces their own little shell. Design-side fix: drop parts that add
  little (the dorsal fin) rather than fight them.
- The mirrored retopo turned Clovern's sprout into strings webbing to the ears: the sprout leaves were designed
  asymmetric, so mirroring x >= 0 copied one thin leaf onto both sides. Pebbloon (tilted hat) went through the same
  batch and got its hat straightened. The build now samples the SDF against its mirror and refuses a symmetric
  retopo when they differ by more than 5 mm; asymmetric designs set SYMMETRIC = False.
- `pkill -f pattern` from a shell whose own command line contains the pattern kills that shell (exit 144). Use
  `pgrep -f "[t]ools/build.py name"`.
- Stats crashed on Fungoad (NaN in the SVD): 2 zero-area triangles from the mirror weld. Clovern had 2 as well,
  unnoticed. Now `dissolve_degenerate` runs after the weld, the build refuses any zero-area face (and retries with
  the next Quadriflow seed), and stats.md reports the degenerate count, so it can never hide again.
- A monitor reading `batch.sh | grep` output never fires per item: grep block-buffers into the task file. Watch the
  per-creature logs instead.
- Ripplefin v1 scored ~6.5: jagged notches in the belly stripe (the painter took the frame of the single nearest
  spine segment, which jumps where the neck passes over the coil), heart-shaped broken spots (spots on a per-segment
  grid), and a coil of even thickness that read as a pool float. Fixes: frame softly blended over nearby segments
  (softmin of distance), spots as true 3D dots placed along the spine, coil that thickens mid-way and rises as it wraps.
- Zero-area faces on Clovern on every seed: not from the weld but from projection, which pulled near-midline vertices
  under the seed-pod tail onto their midline neighbours. A cleanup after relax merges coincident vertices, dissolves
  collapsed faces and triangulates any resulting n-gon.
- All dense meshes were inside-out (negative volume): my winding flip in `march` was backwards. Cycles renders both
  sides so nothing showed, and Quadriflow re-oriented its output (every exported GLB measured positive volume), but
  Skyray was refused outright. Fixed at the source; stats.md now reports orientation for every export.
- Quadriflow refused Frostmoth's capped halves on every variant (bow-tie vertices where a wing grazes the collar).
  Fallback: full retopo + Blender Symmetrize + rejoin triangles. Leaves a few triangles / pentagons on the midline.
- Collinear fan triangles inside quads (Brasshorn) survive vertex merging: re-split those quads on the other diagonal.
- Skyray's thin flat wing tips: thicker wing (flat 0.48, tip radius 0.075) and a smaller V let Quadriflow accept it.
- Lost about 20 minutes to a deadlock: three queued batch waiters each ran `pgrep -f "[t]ools/batch.sh"`, and each
  waiter's own command line contained "tools/batch.sh", so they waited on each other forever. Run one consolidated
  batch instead of chained waiters; if chaining is needed, wait on a PID or a finish file, never on a name pattern.

## 2026-10-27 local Windows run, Studio import, kaiju
- A MeshPart made with `AssetService:CreateMeshPartAsync(Content.fromObject(editableMesh))` keeps the mesh's own
  origin at the part centre: a mesh grounded at y = 0 floats by half its height. Centre the vertex bounds before
  building (`tools/to_roblox.py` does). Deleting files under a running `rojo serve` crashed it; overwrite instead.
- Roblox `Slate` material on a textured MeshPart takes the plastic shine off big creatures.
- Rig (`tools/rig.py`): bones from the SDF control points shifted by the export offset; auto weights gave 0
  unweighted vertices; IK feet keep the walk on the ground (audit: lowest vertex per frame). Pitching a tail that
  rests near the floor downward pushed it 11 cm through the ground in the roar; keep near-floor bones pitching up.
- Arm X-rotations on the arm chain changed little on screen (roll from `align_roll(X x dir)` on a sideways arm);
  a raised-claw pose needs a proper arm roll or an IK target for the hand.
