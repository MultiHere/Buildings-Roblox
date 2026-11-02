# Review of M1 (local reviewer + owner, 2026-11-02)

Approved as the base: layout, part split, ref camera, D1 proportions (14-stud floors, wall top 44), D2-D5.
Keep all of it; M2 adds to these meshes, it does not rebuild them.

Fixes to do in M2, on top of the M2 scope in `docs/MILESTONES.md`:
1. **Slab edges too thin.** In the reference every floor level reads as a thick horizontal band: an edge beam about
   2 studs deep (downstand under the slab edge) on the front and the left side, its top broken and covered with
   rubble. Ours reads as thin lines. Add the edge beams to `frame` (no coplanar faces with the slab).
2. **Standing top wall too narrow and too clean.** In the reference it spans about 1.3 bays, with many small shell
   holes (8-15, small, some not through), 1-2 big ragged holes and a jagged broken top edge. Small pitting can be
   texture in M3; holes you can see sky through are geometry.
3. **Columns slightly thin.** Make them 1.8-2.0 studs, with chipped corners and broken ends where they stop.

Not checked yet: Studio import scale (checked at M3 on the textured FBX).
