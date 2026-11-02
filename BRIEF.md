# Brief: building 1 of 10 - bombed-out 3-storey concrete frame building

## The client's words (Discord, 2026-11-02)
"make sure you keep it under 35k tris and seperate the parts of the model such as the door roof building etc so that
the textures can be clean and not packed into 1 model entirely"
Their post: realistic, low-poly, urban (residential, shops, city structures), varied shapes, convincing damage, fits
the game's art direction, optimised for Roblox without losing visual quality, follow references accurately.

## Reference
`ref/building1_ref_small.png` (399x266, cropped from a chat screenshot; a full-size version may be added as
`ref/building1_ref.png` - use it if it is there). Read it carefully; describe every feature in STATUS before building.
What the reviewer sees in it:
- Reinforced-concrete column-and-slab frame, seen from the front-left, slightly low. Ground floor + 2 floors complete,
  3rd-floor level mostly destroyed.
- Front: 4 bays (5 column lines). Slabs stick out past the columns a little; on the LEFT the slabs overhang more,
  like thin balconies, with broken ends.
- Infill walls mostly blown out: big ragged openings, leftover wall chunks at bay edges, shell pitting everywhere.
- Top: one tall standing wall piece left of centre (about 1 storey high, with 3-5 holes through it), a room frame
  on the right with a column and a lintel, a short wall stub at the far right. Rebar sticks up at the top-left corner.
- A collapsed slab piece hangs/leans inside the ground floor left bays. Rubble mounds at the base (front and sides,
  higher at the left), rubble on every slab edge, broken chunks on the floors.
- Colour: dusty grey-brown concrete, darker soot in openings, lighter fresh breaks.

## Size (in studs; one number to change if the client gives their scale)
- Floor-to-floor 12 studs, slab 1 stud thick, columns 1.6 x 1.6 studs, bay 14 studs.
- Front 4 bays = 56 studs between outer column centres; depth 2 bays = 28 studs. Left overhang 2.5 studs.
- Standing wall at the top reaches about 34 studs above ground. Ground floor sits on the ground (y = 0).
- A normal Roblox avatar (about 5.5 studs tall) must walk through the ground floor and stand on the slabs.

## Triangle budget (total under 35,000; aim 30,000 to leave room for the client's changes)
| part (FBX object = MeshPart) | material | budget |
|---|---|---|
| `frame` columns + slabs | Concrete044D | 7,000 |
| `walls` infill chunks + standing top wall | Plaster007 over Concrete036 | 7,000 |
| `slabs_broken` hanging / cracked pieces, broken balcony ends | Concrete044D | 3,000 |
| `rubble` mounds at the base and on slabs | Ground108 + concrete chunks | 9,000 |
| `debris` loose chunks, blocks, a few broken slab plates | Concrete036 | 3,000 |
| `rebar` exposed bent bars (thin, 4-6 sided) | Metal041B, darkened rust | 1,000 |
Each part under 20,000. Hidden faces (inside walls, under rubble, slab tops covered by rubble) deleted.

## Textures
- One 1024 set per part: `<part>_color.png`, `<part>_normal.png` (OpenGL), `<part>_roughness.png` (+ metalness for
  rebar). Built from the CC0 sets in `textures/` (tile at world scale, about 1 texture repeat per 8 studs on concrete)
  with baked AO, darker soot inside openings, lighter edges at fresh breaks, dust on top faces, shrapnel pitting in
  the normal map. Keep a clean UV layout (no overlaps inside a part, consistent texel density) so the client can
  repaint or swap materials.

## Deliverable of this repo (per building)
`out/building01/`: `building01.fbx` (+ `.glb`), `textures/`, `sheet.png` (ref vs render at the ref camera, 3/4 view,
side, back, wireframe, UV layout), `stats.md` (tris per part, bounds in studs, texel density, smallest layer gap,
silhouette score, open edges, export factor).

## Not in scope
Interiors beyond what the ruin shows, collision setup, scripts, uploading to Roblox (the local session imports).
