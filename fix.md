# CS2 kit improvement log

Originally written on `deepseek-work`; items 1-8 were cherry-picked to
`claude-work` (the 101 palette tuning commits were not).

## 1-3
- mesh-hash FBX/LOD cache: `tools/cycle.py`
- LOD hole coordinates + margin warning: `tools/qa/lod_check.py`, `tools/qa/lod_check_bl.py`
- face map + corner-view warning: `tools/face_map.py`

## 4. CPU backface pre-check
- Tool: `tools/backface_check.py`
- Optional gate: `python tools/cycle.py ... --backface-check`
- Compares cull-on/cull-off masks from 8 low-res views, with a closed ground
  slab and a 1 px dilation to suppress raster cracks.
- Self-test: closed cube `0` holes, open-front cube `>0`.
- Current asset: `main/lod1/lod2 = 0.000%` at 128 px / 8 views.
- Limit: low-resolution CPU pre-check; Blender `lod_check.py` remains the
  final authority. Use `--res 256` for a closer look.

## 5. Vision wall-crop batch
- Tool: `tools/vision_batch.py`
- Modes:
  - `--refs photo_refs.json` -> one crop per facade ref (bounding box of corners)
  - `--photo ... --wall-box wall_id=x0,y0,x1,y1` -> explicit wall crops
- Writes `previews/vision/batch/<wall>_vision.jpg` and
  `work/vision_batch.json` with source/derived SHA-256, wall ID, crop, size.
- `--asset output/<asset>` adds a corner-view warning when a photo azimuth is
  more than 15 degrees away from the wall normal.
- Source photos are never modified; nothing is uploaded automatically.

## 6. glb-mass rooftop tier roles
- `tools/glb_shape.py` now writes per-volume:
  - `role`: `mass | screen | parapet | roof_mass | equipment`
  - `keep_solid`: boolean hint
  - `source_section_z`
- Large low roof tiers become `equipment` with `keep_solid=false` and a warning;
  tall roof volumes remain `roof_mass`. A `solar` role is intentionally not
  auto-assigned; verify solar/terrace tiers against photos.
- `shape_report.json` includes role/keep_solid.

## 7. Render/preview cache
- `tools/render.py` caches identical view/size/zoom/box/photo requests under
  `previews/_render_cache/` using content hashes of OBJ + textures.
- `--no-cache` bypasses it.
- Verified: first render writes, second prints `[render] cached ...`.

## 8. Wall-specific window preset
- `cs2kit.py`: `K.wall_window_layout(length, spec)` supports:
  - `kind="blank"`
  - `bays`, `width`, `margin`, `min_width`, `gap`, `target_pitch`
- Example:
```python
WALL_WINDOWS = {
    "mass_01_00:edge_06": dict(bays=3, width=1.20, margin=0.45),
    "mass_01_00:edge_10": dict(bays=2, width=0.80, margin=0.20),
    "mass_01_00:edge_05": dict(kind="blank"),
}
spans, gaps = K.wall_window_layout(wall["length_m"], WALL_WINDOWS.get(wall["wall_id"]))
```
- Fallback remains the existing length/pitch heuristic.

## Render preset bug fixed
`tools/render.py` `left`/`right` presets were swapped relative to the camera:
yaw90 looks from `-X` (left), yaw270 from `+X` (right). Presets are now
`left=(90, 8)`, `right=(-90, 8)`. This was the source of the earlier
left/right confusion. `front/back` are unchanged.

## Next (not applied)
- Planar Naver VR refs + `capture/naver_vr.py make_refs --debug` for real
  `photo_refs.json` and quantitative photo/tile checks (see new AGENTS note and
  `docs/agent/NAVER_VR.md`).
- Per-wall `WALL_WINDOWS` table in the project generator using
  `K.wall_window_layout`.
- Add closed window frame/piers to reach the 30k main-tri target.
- LOD margin: current main 0.048% remains marginal; close the
  `gen (-7.82, 1.20, 103.57)` / `(-17.22, 0.23, 104.25)` gaps.
