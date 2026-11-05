# CS2 kit improvement backlog

Applied in this commit:

- **1. mesh-hash FBX/LOD cache** — `tools/cycle.py`
  - final build always writes OBJ first
  - `_check/final_cache.json` stores `mesh_sig`, FBX status, and the LOD result
  - same mesh signature reuses `.fbx`/`.blend` and the LOD check
  - paint/texture-only edits no longer rerun Blender/LOD
- **2. LOD diagnostics + margin warning** — `tools/qa/lod_check.py`, `tools/qa/lod_check_bl.py`
  - `where` now recorded for every hole (`hole_pct > 0`), not only `> 0.05`
  - preview PNG saved for holes above 0.02%
  - `HOLE_SMALL` lines print generator coordinates/normals
  - PASS line gains `marginal=1` and a WARN when max is between 0.03% and 0.05%
- **3. face map + corner-view warning** — `tools/face_map.py`
  - `previews/face_map.png` with wall IDs, roles, normals, lengths
  - `work/face_map.md` and `work/face_map.json`
  - optional `--refs photo_refs.json`: warns when a photo azimuth differs
    from the linked wall normal by more than 15 degrees (corner view)
  - default draws the `mass_01_00` top walls; `--volume all` includes tiers

Remaining proposals (4-8):

## 4. CPU backface pre-check in quick mode
Target: `tools/check.py` or `tools/render.py`.

Add `--backface-check` that rasterizes `main`, `lod1`, `lod2` from 8 low-res
directions twice (backface culling on/off), then reports visible backfaces and
saves a mask. This catches single-sided paint quads, open screen/solar corners,
and railing undersides before the Blender final gate.

Expected effect: fewer final LOD iterations; the current main 0.048% and LOD1/2
0.033% holes are exactly this class of defect.

## 5. Vision wall-crop batch
Target: `tools/agent.py vision`, `tools/vision_prepare.py`.

- `--wall-id mass_01_00:edge_06` should use `manifest.metadata.walls` plus the
  photo azimuth to compute a crop automatically.
- `--all-walls <photo>` should emit one crop per wall and append entries to
  `work/photo_evidence.json`.
- Store source hash, crop box, wall ID, confidence, occlusion, and whether the
  view is a corner view.

Expected effect: no repeated whole-photo reads; wall-linked evidence for
`photo_refs.json` and `facade_read`.

## 6. glb-mass rooftop tier roles
Target: `glb-mass` agent command.

Record per generated volume:

- `role: mass | parapet | screen | equipment | solar`
- `keep_solid: true/false`
- `source_section_z`
- optional `photo_refs` hint

The current tool turns a solar terrace and louver screens into solid prisms.
A role/keep_solid field lets the generator build a terrace/screen instead of a
solid block without manual reconstruction. Add a warning in `shape_report.json`
when a thin/near-edge volume looks like equipment rather than mass.

## 7. Render/preview cache
Target: `tools/render.py`, `tools/cycle.py`.

- cache mesh+texture fingerprint per view/size (similar to
  `previews/elevation_cache/`)
- generate a single `previews/review_faces.png` contact sheet:
  front/back/left/right + one wall crop
- keep the standard 4-view preview as the fast silhouette sheet

Expected effect: repeated high-resolution detail renders become cheap; visual
review uses one consistent artifact instead of many ad-hoc images.

## 8. Wall-specific window preset
Target: `cs2kit.py` or a project generator helper.

Replace the generic `layout_windows(length)` heuristic with a wall-ID table:

```python
WALL_WINDOWS = {
    "mass_01_00:edge_00": dict(kind="blank_strip", bays=1, w=0.72),
    "mass_01_00:edge_01": dict(bays=7, w=1.85, sill=0.85, h=1.55),
    "mass_01_00:edge_03": dict(kind="blank"),
    "mass_01_00:edge_05": dict(kind="blank"),
    "mass_01_00:edge_06": dict(bays=3, w=1.20, sill=0.90, h=1.35),
    "mass_01_00:edge_10": dict(kind="entry_core", core=2.8, side=0.8, slot=0.7),
    "mass_01_00:edge_12": dict(bays=4, w=1.85),
    "mass_01_00:edge_14": dict(bays=3, w=1.85),
}
```

Fallback to the current heuristic for unlisted walls. This keeps facade edits
stable when wall normals/positions change and makes the corner-view judgment
explicit per wall.

## Verification for 4-8

For each item, add a small self-test:

- backface pre-check: closed cube PASS, open-front cube FAIL
- vision batch: one source photo -> N wall crops with valid hashes
- glb-mass roles: synthetic roof box/screen fixture classified correctly
- render cache: same mesh + different BaseColor must reuse geometry but refresh texture
- window preset: wall table count matches generated `win` quad count
