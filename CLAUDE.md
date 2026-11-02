# Ruined city buildings for a Roblox urban combat game (cloud build rules)

A paid commission for MultiHere (Roblox builder, paid in Robux). The client is making a large urban combat game and
ordered 10 realistic low-poly buildings; this repo makes them one at a time. You are the builder in the cloud. A local
Claude session with Roblox Studio imports and reviews every milestone; the owner decides. Read `BRIEF.md` (what to
make), `docs/MILESTONES.md` (order, time boxes, done-checks), then `docs/STATUS.md` (where we are).

## 1. Finishing and asking (owner, 2026-11-02)
- **When the milestone is done: commit, push to `main`, update `docs/STATUS.md`, then STOP.** Do not end with a
  question: an answer would only restart the chat and spend tokens. The local reviewer reads STATUS from the repo.
  (Check with `git ls-remote --heads origin`; if the session forces a `claude/...` branch, name it in STATUS.)
- Never start the next milestone yourself.
- Use AskUserQuestion only when you are truly blocked mid-milestone (a check failing 3 times, a tool that will not
  install after 3 tries, the time box passed): push what is there, write the problem in STATUS, ask once.
- Defaults you can pick yourself: pick them and write them in STATUS.

## 2. Spend (limited credit)
- Model is set in `.claude/settings.json`; do not switch. `.claude/hooks/budget.py` estimates spend from the
  transcript and blocks tools near the cap: finish, commit, push, write STATUS, ask.
- Short tool output: `| tail -20`, `grep`, `head`, `wc`. Never dump meshes, JSON or big listings. Read files with
  offset/limit, never twice.
- Images are expensive: numbers first (tris, bounds, silhouette score, UV overlap), then **one contact sheet per
  check** (<= 1200 px wide), at most 3 looks per milestone.
- **Reuse, don't invent.** `pipeline/` is a proven headless Blender setup from an earlier run (bpy wheel, Cycles
  render, bake, stats). It was written for organic creatures: reuse its render/bake/export plumbing, NOT its SDF or
  Quadriflow parts. Read `pipeline/LESSONS_creatures.md` once before the first build (known bpy-wheel bugs). Buildings
  are hard-surface: model them directly with bmesh, booleans and modifiers.
- No web research unless `docs/MILESTONES.md` allows it. No new frameworks.
- `set -o pipefail` in every shell chain; check exit codes before the next step. Small commits, push after each part.

## 3. Halal and content (overrides everything)
- Damage reads as war damage to concrete only: no blood, bodies, bones, skulls, burned people.
- No religious buildings or symbols, no flags, no political or real-world graffiti, no writing in any script on walls,
  no posters or ads of people. A plain shop sign is fine only if the brief asks for one, with made-up words.
- No textures or models from anywhere except the CC0 sets in `textures/` and what you make yourself.

## 4. Quality bar (the client "wants builders who follow references accurately")
- Roblox: one MeshPart <= 20,000 triangles; the whole building under the budget in `BRIEF.md`. Textures 1024.
- Match the reference: proportions, number of floors and bays, where it is broken, where the rubble is. Compare a
  render from the reference's camera next to the reference at every milestone and measure the silhouette match
  (`tools/silhouette.py`, the reference has a white background).
- Damage in geometry only where it changes the outline (holes, broken slab edges, bent rebar, rubble, hanging slab).
  Pitting, shrapnel marks, cracks, soot and dust go in the textures (normal + colour), not in triangles.
- Low-poly done well: flat broken planes with sharp edges, weighted normals, no triangle soup, no tiny slivers, no
  hidden faces inside walls (delete faces nobody can see, they cost triangles), no duplicate verts, no zero-area faces.
- No z-fighting: no coplanar overlapping faces between parts; offset stacked layers by >= 0.01 studs. Report the
  smallest gap measured.
- Separate parts by material, named like a person would: `frame`, `walls`, `slabs_broken`, `rubble`, `rebar`, etc.
- Scale: model in studs as Blender units (1 BU = 1 stud). Export FBX so Studio's Import 3D gives the right stud size
  (lesson: FBX `global_scale=0.01, apply_unit_scale=True` was right for metres -> studs; verify by re-importing and
  reading the bounds, and write the factor you used in STATUS).
- Self-scores are not proof. Report measured numbers; the reviewer judges the look in Studio.

## 5. Repo
`BRIEF.md` scope - `docs/` milestones, status - `ref/` reference images - `textures/` CC0 sets (ambientCG) -
`pipeline/` reused tools - `tools/` your new scripts - `out/building01/` outputs (fbx, glb, textures, sheet.png,
stats.md). First thing on a new VM: `bash tools/setup.sh`.
