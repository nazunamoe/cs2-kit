# Generic volumes and non-apartment buildings

Use composable volumes and wall features for shops, schools, and irregular buildings instead of adding a large preset for every building type.

## Start

```bash
python tools/project.py new my-building --template generic
```

This copies `example_generic_cs2.py` as the project generator and `templates/generic_spec.example.json` as `generic_spec.json`. Edit the JSON data rather than writing a new geometry engine.

## Schema

```yaml
volumes:
  - id: main
    footprint: [[0,0], [24,0], [24,10], [0,10]]
    height: 12
    z0: 0
    wall: wall
    roof: roof
    wall_ids: [main:front, main:right, main:back, main:left]
openings:
  - type: window_band
    wall: main:front
    u0: 0.08
    u1: 0.92
    z0: 4.4
    z1: 6.2
    bays: 8
attachments:
  - type: roof_equipment
    volume: gym
    size: [2, 1.5]
    height: 1
```

The actual example is JSON. Footprints must be simple, non-self-intersecting polygons. Clockwise input is normalized to CCW. Roof polygons are ear-clipped into triangles. Every wall gets a stable ID, length/height, normal, render box, and volume link in `manifest.metadata.walls`.

## Feature types

- `window_band`: normalized U range, absolute Z range, bay count, floor/unit.
- `shopfront`: glazed ground-floor band, optional generic sign slot and canopy.
- `sign_slot`: generic sign area only; no real brand or sign text.
- `louver_zone`: backing and repeated horizontal blades.
- `railing_zone`: solid top rail/posts and optional `_Gls` panel.
- `roof_equipment`: box equipment on a named volume.
- `covered_link`: a rectangular covered volume between two points.
- `entrance_canopy`: an existing entrance socket and thin canopy.

The same spec is built at FULL, SIMPLIFY_TRIM, and LOD_CULL. LOD1 removes small trim, while LOD2 preserves volume silhouettes and windows. Do not collapse a multi-volume building into one LOD2 box.

Use `K.volume_prism`, `K.build_volume_spec`, and `K.wall_quad` for custom generators. `WindowSet.add_pts` supports angled walls. Unique curved or highly articulated geometry may still need a custom generator; do not force it into an inaccurate preset.

## Validation

`validate_volume_spec` rejects empty/duplicate IDs, invalid footprints/heights, unknown wall references, and invalid U/Z ranges before geometry is built. The standard cycle then checks geometry, windows, textures, photos, tiles, and LOD.

For photo comparison, link `photo_refs.json` to the generated wall IDs. The checker uses the actual wall dimensions, render box, and normal rather than the whole building bounds.

## Example

`example_generic_cs2.py` plus `templates/generic_spec.example.json` builds a mixed-use main block and angled gym volume with a shopfront, classroom-style bands, angled windows, louver, canopy, roof equipment, and railing. It is a generic synthetic example, not a real building.

Run:

```bash
python tools/agent.py cycle --project P --generator G --mode quick --brief --json
python tools/agent.py cycle --project P --generator G --mode final --brief --json
```

Then inspect the artifacts returned in `next_action` and record the review.
