# Tool reference — DeepSeek via Codex

Run commands from the kit root. `agent.py` requires `--project`; lower-level tools also accept `--project` or an explicit path inside a project. Read `docs/agent/WORKFLOW.md` for the build loop.

## Preferred agent commands

```bash
python tools/agent.py doctor --project P --json
python tools/agent.py resume --project P --json
python tools/agent.py deepseek-policy --project P --task data|edit|geometry|vision|review --json
python tools/agent.py vision --project P --photo photos/front.jpg --box=x0,y0,x1,y1 --wall-id W --json
python tools/agent.py require-final --project P --json
python tools/agent.py cycle --project P --generator G --mode quick|visual|final --label STEP --brief --json
python tools/agent.py review --project P --status PASS|FAIL|NEEDS_HUMAN_REVIEW --note NOTE --artifact PATH --json
python tools/agent.py photos --project P --page 0 --page-size 16 --json
python tools/agent.py observe --project P --photo photos/front.jpg --side front --note NOTE --json
python tools/agent.py probe --project P --shot 101_side5.png --frame work/frame_101.json --px X,Y [--px X,Y | --frac FX,FY] --json
python tools/agent.py colordiff --project P --shot 103_side15.png --frame work/frame_103.json --color tan --json
python tools/agent.py fix --project P --generator G --request TEXT --box=x0,x1,y0,y1,z0,z1 --json
python tools/agent.py fix --project P --generator G --finish --json
```

The agent result contains `status`, per-check states, errors/warnings, `next_action`, and paths to detailed gate/log/state files. It deliberately does not echo the full report. Agent runs use a per-project lock and explicit project paths. A lock whose process has exited (or whose pid was recycled) is removed with a `[lock]` notice on stderr; a lock held by a live run ends the command with exit code 3 and, with `--json`, `{"status": "LOCKED", "pid": ...}` on stdout. Exit codes: 0 PASS, 1 FAIL, 2 INCOMPLETE, 3 LOCKED.

`probe` (read-only, needs the asset `.blend` from a final build) answers "which face, material and coordinate does this photo pixel land on?" before you edit: it casts a ray through the pixel with the same camera as `tools/qa/cmp_cam.py --frame` (LOD meshes removed) and prints the object (main or window), atlas region, normal, asset xyz and generator xyz. Pixels are in the original photo; `--frac` takes fractions of width and height. Parts the generator rotates are not converted to local coordinates. 104 needs `--frame work/frame_104_gen.json`.

`colordiff` (read-only, same prerequisites) lists where the photo shows a colour the model does not paint there: it finds photo pixels of one colour class (`tan` is the validated one; `white`/`dark`/`bluegrey` are coarse), probes them, and compares with the colour of the material hit (read from the asset's BaseColor atlas, nothing hard-coded). Mismatches are grouped by wall normal, position along the wall and material; groups below `--min-hits` (default 3) are hidden. Use several shots of the same wall to confirm a group.

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

Errors include naming, ground/pivot, LOD budgets, coplanar faces, blocked windows, UV/atlas issues, and textures. Warnings include texel density, lot size, and main >95k tris. `WIN_DROPPED` is a warning read from the export manifest: the zone builder dropped that many windows because they sat within 5 cm of a wall-piece end, so it is a count of silent losses rather than a guess from the mesh. Coordinates are generator coordinates when a manifest exists.

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
- `facade_read.py`: normalized U/V facade output plus a combined `facade_read.json`; `--json` prints one machine-readable blob. v1, synthetic-image validation only.
- `tools/qa/color_diff.py` / `agent.py colordiff`: photo colour vs model material mismatch list (see above); built on `probe.probe_rows`.
- `tools/qa/lod_check.py` hole report: each `at gen` line (the BACK face seen through the hole) is followed by `near front face` lines = the nearest camera-facing faces around the hole (gap = distance from the hole to the face outline, m). A back-face point just beside the end of a near wall means a ray slipped past that wall's end; two near faces with gap ~0 on both sides mean a seam. Cached LOD results (`[lod] cached`, mesh unchanged) do not repeat these lines.
- `tools/qa/probe.py` / `agent.py probe`: photo pixel -> model face, atlas region (material), normal and coordinates (see above). Use it to find which zone a photo detail belongs to; shares `cmp_cam.frame_camera` so the pixel matches the cmp_cam render.
- `tools/qa/plane_compare.py`: register the capture camera, warp photo and model onto the same plane, and score each plane with block SSIM + edge overlap. Failing scores are written to `work/plane_compare/photo_mismatch_notes.yaml` and can be appended to the spec with `--spec`; `--strict` exits 1 on a miss.
- `band_scan.py`: paint grid/palette with window and normalized U/V exclusion masks; unknown cells stay `-1` and unpainted. Verify `_mask.png` and real photos.
- `capture/naver_vr.py`: repeatable VR capture, safe resume, camera-matrix planar refs. `make_refs` defaults to one best view per exact plane. See `docs/agent/NAVER_VR.md`.
- `glb_measure.py scan.glb --list`, then `--mesh`/`--box`: overall dimensions and elevations.
- `glb_slices.py`: individual wall segments from explicit GLB slices; v1.
- `glb_shape.py` / `agent.py glb-mass`: multi-height outer footprints, simplified polygon volumes, automatic or explicit height tiers, source provenance, and a review preview. See `docs/agent/GLB_MASS.md`.
- `xrx_mass.py --xrx photos/data.xrx.json --dongs 101`: draft a per-dong mass from Naver VR metadata only (no photo evidence). See `docs/agent/XRX_MASS.md`.
- `photo_quality.py --dir photos`: blur, resolution, duplicate and exposure gate for reference images. Add `--refs photo_refs.json --min-px-per-m 20` to block a capture whose planes are too low-resolution before registration. See `docs/agent/PHOTO_QUALITY.md`.
- `photo_plane_map.py`: register capture planes onto model walls; angle+length sliver rule, cached registration, and `--workers` for the coarse rotation sweep. See `docs/agent/PHOTO_PLANE_MAP.md`.
- `video_frames.py --video walk.mp4`: extract frames from a walkthrough video and add them as photos. See `docs/agent/VIDEO_FRAMES.md`.
- `crop_360.py --image pan.jpg --yaws 0,90`: perspective crops from a 360/equirectangular photo. See `docs/agent/PANORAMA_360.md`.
- `ifc_to_glb.py --check|--plan`: available IFC/BIM converters and the conversion route to GLB. See `docs/agent/IFC_TO_GLB.md`.
- `lod_auto.py`: main `.blend`에서 LOD1/LOD2 후보를 만들고 `lod_check`로 구멍을 확인. `--max-tris`/`--max-lod1-tris` 하드 상한과 UV 아틀라스 범위 검사를 함께 본다. 후보는 생성기 최종 LOD를 대체하지 않음. See `docs/agent/LOD_AUTO.md`.
- `tools/photo_facade/`: one legacy generator structure only; do not use on unrelated generators.

Scans are measurement references. Never copy their geometry or textures into the asset.

## Scoped comparison and FBX (Blender or bpy)

```bash
python tools/compare.py snap output/A
python tools/compare.py diff backup/SNAPSHOT output/A --box=-11,11,-8,0,0,6
python tools/run_blender.py --find
python tools/run_blender.py --set "C:\path\to\blender.exe"
python tools/run_blender.py --set-py ".venv-bpy\Scripts\python.exe"
python tools/run_blender.py --obj G -- --out output
python tools/run_blender.py G -- --out output
```

`--obj` skips FBX for fast iteration. Without `--obj`, the bpy module is used when found, otherwise Blender; `RUN_BLENDER_ENGINE=exe` forces the app. `pip install bpy` in a matching venv (Blender 5.0 → Python 3.11) writes the same FBX headlessly, with no Blender install; `tools/run_blender.py --fbx2obj` can also read FBX back without Blender. The LOD check prefers the Blender app when present (Workbench renders ~5x faster there) and otherwise uses bpy; `LOD_ENGINE=exe|py` forces one. `compare.py diff --box` fails on mesh changes outside the box; window UVs are compared by position because atlas allocation can reorder them. `--json` writes the same diff as structured data (mesh counts, out-of-box count, changed texture regions) and prints a `MESHDIFF PASS|FAIL` line; `agent.py fix` runs the same diff after its final cycle.

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

## Photo evidence and generic volumes

- `docs/agent/DEEPSEEK.md`: model choice, reasoning policy, crop/privacy, Codex setup, and final assertion.
- `docs/agent/PHOTO_ONLY.md`: wall-linked photo evidence, normalized U/V observations, confidence, wall-specific refs.
- `docs/agent/VOLUMES.md`: `--template generic`, arbitrary polygon volumes, wall features, volume LODs, and manifest wall metadata.
- `tools/evidence.py`: photo/feature/validate ledger commands; normally called through `agent.py evidence`.
- `K.volume_prism`, `K.build_volume_spec`, `K.wall_quad`: generic geometry API. `export_asset(..., metadata=...)` stores wall/volume metadata for photo alignment.

## State, briefs, and generated docs

```bash
python tools/state.py --project P --json        # per-stage projection in work/state.yaml
python tools/docs_gen.py                        # refresh docs/agent/TOOL_<name>.md
python tools/docs_gen.py --check --json         # exit 1 when a generated doc is stale
```

`work/state.yaml` mirrors `work/agent_state.json` into stage records (`quick`, `windows`, `final`, `fix`) with the gate status and preview/FBX hashes. A failing gate also writes `work/logs/builder_brief.md`, grouping the failed checks into `build`, `geometry`, `texture`, `lod`, `photo_match`, or `gate`. Generated `TOOL_<name>.md` files are derived from each tool's `--help`; edit the argparse text, not the generated file.

## Repository sync

```bash
python tools/sync_branches.py                       # fetch, fast-forward local branches, report drift
python tools/sync_branches.py --check --json        # no writes; exit 1 on any drift
python tools/sync_branches.py --branches opencode_work claude
```

The tool only fast-forwards: it never rebases, merges, force-pushes, or pushes. A branch
ahead of its remote or diverged from it is reported (`DRIFT`, exit 1). Cross-branch counts
show commits that exist on one branch but not the other, which is how a commit made on
`opencode_work` is noticed before it is cherry-picked to `claude`. Commit subjects should
use `feat:`, `fix:`, `docs:`, `perf:`, `refactor:`, `test:`, or `chore:`.

## Known limits

The preview renderer is orthographic with simple lighting, not the game renderer. Window blocking samples three points per window. Photo and tile metrics are vulnerable to occlusion, shadows, and weak patterns. FBX and the LOD check work with either Blender or the `bpy` module. Always check game scale, appearance, night lights, alpha, entrance, and registration in game.
