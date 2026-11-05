# Tool reference — Claude Code

Run commands from the kit root. `agent.py` requires `--project`; lower-level tools also accept `--project` or an explicit path inside a project. Read `docs/agent/WORKFLOW.md` for the build loop.

## Preferred agent commands

```bash
python tools/agent.py doctor --project P --json
python tools/agent.py resume --project P --json
python tools/agent.py cycle --project P --generator G --mode quick|visual|final --label STEP --brief --json
python tools/agent.py review --project P --status PASS|FAIL|NEEDS_HUMAN_REVIEW --note NOTE --artifact PATH --json
python tools/agent.py photos --project P --page 0 --page-size 16 --json
python tools/agent.py observe --project P --photo photos/front.jpg --side front --note NOTE --json
python tools/agent.py fix --project P --generator G --request TEXT --box=x0,x1,y0,y1,z0,z1 --json
python tools/agent.py fix --project P --generator G --finish --json
```

The agent result contains `status`, per-check states, errors/warnings, `next_action`, and paths to detailed gate/log/state files. It deliberately does not echo the full report. Agent runs use a per-project lock and explicit project paths.

## Shared cycle gate

```bash
python tools/cycle.py G --mode quick --json
python tools/cycle.py G --mode visual --label windows --json
python tools/cycle.py G --mode final --strict --label final --json
```

- quick: normal Python OBJ build + `check.py`.
- visual: OBJ + render + shared `visual_check.py` photo analysis when refs exist.
- final: Blender FBX + render + shared photo/tile analysis + full LOD + strict gate. LOD runs concurrently with CPU visual checks.
- Legacy `--no-render`, `--tiles`, and `--full` remain available.
- Strict exit: 0 PASS, 1 FAIL, 2 INCOMPLETE/NEEDS_HUMAN_REVIEW. Non-strict legacy exit considers geometry errors only.

`GATE`/`gate.json` distinguish `PASS`, `FAIL`, `NOT_CHECKED`, `NOT_APPLICABLE`, `PARTIAL`, and `NEEDS_HUMAN_REVIEW`. Empty refs are a failed configuration. A photo-analysis exception is a failed check. `tools/qa/verify.py` wraps the same gate and adds optional same-camera regression checks; `--fast` is quick-only and not valid for a final report.

## Geometry checks

```bash
python tools/check.py output/<asset> --list 10 --json previews/check.json
```

Errors include naming, ground/pivot, LOD budgets, coplanar faces, blocked windows, UV/atlas issues, and textures. Warnings include texel density, lot size, and main >95k tris. Coordinates are generator coordinates when a manifest exists.

`[CS2_AGENT_SUMMARY]` action tags:

| Tag | Meaning | Allowed response |
|---|---|---|
| `REDUCE_MAIN_DETAIL` | main >95k tris | Remove hidden/secondary detail; preserve floors, bays, and windows |
| `REDUCE_LOD_DETAIL` | LOD1/LOD2 over budget | Remove small LOD parts; preset mode may use `quality_stage=3` |
| `FIX_CUSTOM_UV` | ATLAS_UV | Use atlas UV helpers on custom quads |
| `FIX_WINDOW_UV` | WIN_UV | Rebuild with `WindowSet.add_face`; remove custom window UVs |
| `REMOVE_DEGENERATE_FACES` | zero-area warning | Inspect coordinates and duplicate calls/vertices |

Tags are suggestions tied to actual warnings/errors, not reasons to alter measured building structure.

## Render and photo comparison

```bash
python tools/render.py output/A -o previews/a.png --views front,iso,top,lod1,lod2
python tools/render.py output/A -o previews/z.png --views front --zoom 3,0.5,0.1
python tools/render.py output/A -o previews/b.png --views yaw30:pitch5 --box=-10,10,-5,3,0,8
python tools/render.py output/A -o previews/n.png --views front --night
python tools/photo_check.py output/A
python tools/tile_compare.py output/A --tile-m 6x5 --top 3
```

Photo refs map road/satellite image corners to model walls. `photo_check` measures size/ratio/floor pitch and writes `previews/photo_check/`; exit 1=mismatch, 2=check failed. `tile_compare` writes heat maps and worst-tile sheets; its detail/color scores are advisory, while exit 2 means comparison failed.

`visual_check.py` loads the asset once, warps each photo once, and shares the elevation render between photo and tile metrics. Floor-pitch mismatch guidance requires usable photo and model patterns. Colour metrics use trusted tiles only; mixed, high-edge, and vegetation-heavy tiles are reported separately. `previews/elevation_cache/` computes mesh/texture fingerprints once per loaded asset and retains at most 64 images.

Run `python tools/qa/lod_check.py --self-test` for the LOD baseline: a closed cube must PASS and an open-front cube must FAIL.

## Photo measurement and materials

```bash
python tools/sat_grid.py grid photos/front.jpg -o previews/g.png --step 50
python tools/sat_grid.py grid photos/front.jpg -o previews/z.png --crop 400,300,800,600 --zoom 3 --step 10
python tools/sat_grid.py scale --p 102,330 --q 912,318 --meters 74
python tools/extract_texture.py photos/front.jpg --pts 812,402,1290,380,1302,905,806,930 --size 3.0x2.9 -o textures_src/wall --show
```

`extract_texture.py` performs perspective correction and writes albedo/normal/gloss plus source metadata. Avoid logos, text, people, and vehicles. `--paint` suits painted walls; use measured repeating units for joints. `--target-ppm 256` may synthesize fine grain beyond source resolution and must be reported.

## Facade and scan readers

- `facade_paint.py floors|windows|paint|all`: reads one wall from `photo_refs.json`; verify generated images visually.
- `facade_read.py`: normalized U/V facade output; v1, synthetic-image validation only.
- `band_scan.py`: paint grid and palette; v1, verify against real photos before applying.
- `glb_measure.py scan.glb --list`, then `--mesh`/`--box`: dimensions and elevations only.
- `glb_slices.py`: wall segments from GLB slices; v1.
- `tools/samhan_facade/`: one legacy generator structure only; do not use on unrelated generators.

Scans are measurement references. Never copy their geometry or textures into the asset.

## Scoped comparison and Blender

```bash
python tools/compare.py snap output/A
python tools/compare.py diff backup/SNAPSHOT output/A --box=-11,11,-8,0,0,6
python tools/run_blender.py --find
python tools/run_blender.py --set "C:\path\to\blender.exe"
python tools/run_blender.py --obj G -- --out output
python tools/run_blender.py G -- --out output
```

`--obj` skips Blender for fast iteration. Without `--obj`, Blender is used when found. `compare.py diff --box` fails on mesh changes outside the box; window UVs are compared by position because atlas allocation can reorder them.

## Preset/socket mode (v1, optional)

Use only for a generator explicitly written for this API:

```python
meta = K.preset_plate_apartment(A, W=42.0, D=16.0, floors=15, floor_h=2.9, ground_h=4.5, bays=4)
K.attach_roof_crown(meta, style="parapet_light", height=1.2)
K.attach_cornice_band(meta, target_floors=[5,10])
K.attach_entrance_canopy(meta, bay_index=0)
# windows still use WindowSet.add_face with meta.WALLS coordinates
```

Mass uses `preset_plate_apartment`/`preset_tower_l_core`, optional `preset_piloti_base`; decorations use `attach_*`; paint grids use `apply_facade_paint_grid`. Build LODs with separate preset calls at the chosen `quality_stage`. Special geometry may use core helpers with metadata coordinates. Window sockets are not implemented.

V1 limitations: piloti depth is simplified; facade_read/band_scan need real-photo verification; paint grids add color overlays, while physical relief still uses `axbox`. Existing non-preset generators remain valid.

## Known limits

The preview renderer is orthographic with simple lighting, not the game renderer. Window blocking samples three points per window. Photo and tile metrics are vulnerable to occlusion, shadows, and weak patterns. FBX and LOD require Blender. Always check game scale, appearance, night lights, alpha, entrance, and registration in game.
