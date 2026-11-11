# CS2 Building Asset Kit — Claude Code

A kit for creating Cities: Skylines II building assets from photos, GLB scans, and natural-language descriptions. This branch provides **Claude Code–only skills and hooks**; all work shares the same verification engine and state files.

## 1. Prerequisites

Required environment:

- Python 3.9+
- `numpy`, `Pillow`
- Blender 5.2 or the `bpy` pip module — required for FBX generation and LOD checks (`bpy` works without a full Blender install)

Install and initial setup from the kit root:

```bash
pip install numpy pillow
python tools/project.py init
python tools/run_blender.py --find
```

If Blender isn't auto-detected, see `INSTALL.md` for manual path setup. To run without the Blender app, install `bpy` in a dedicated venv (Blender 5.0 → Python 3.11):

```bash
uv venv .venv-bpy --python 3.11
uv pip install --python .venv-bpy bpy
python tools/run_blender.py --find
```

## 2. Creating a New Project

```bash
python tools/project.py new my-apt
# Curtain-wall tower:
python tools/project.py new my-apt --template cw
# Mixed-use, school, irregular volumes:
python tools/project.py new my-building --template generic
```

Now prepare the following inside `projects/my-apt/`:

1. Place reference photos (and optional GLB) in `photos/`.
2. Fill `TASK.md` with known info; leave unknown values blank.
3. **Do not use real complex names, brands, or logos** in asset names or textures.

### Choosing Your Workflow

The starting point depends on your input. Three primary paths:

| Method | Input | Strengths | Start Command |
|--------|-------|-----------|---------------|
| 1. Naver VR + GLB | Tour URL, optional `3dview.glb` | Multi-tower, multi-angle photos, camera/plane metadata, auto mass reconstruction | `capture/naver_vr.py auto` → `agent.py glb-mass` |
| 2. Street View / Custom photos | 3–8 front/corner/detail shots | Real colors, materials, windows, podium, entrance | `agent.py evidence`, `agent.py observe` |
| 3. Natural language + photos | Era/type/floor description + photos | Quick style/floor/window family draft | `tools/brief.py` |

All three must pass the same quick/visual/final gates. Items without photo evidence remain `NOT_APPLICABLE` and never become PASS.

### Auto Mass Reconstruction from GLB

Instead of just overall W/D/H, the tool slices the scan at multiple heights, simplifies the outlines, and produces `generic_spec.json` with L-shapes, stepped footprints, and tiered volumes.

```bash
python tools/project.py new my-building --template generic
python tools/agent.py glb-mass --project my-building --json -- photos/scan.glb --list
python tools/agent.py glb-mass --project my-building --json -- photos/scan.glb --mesh-index 3 --out generic_spec.json --force
```

Check `previews/glb/shape.png` and `shape_report.json`, then connect windows and facade parts to the generated wall IDs. Use `--levels 6,12` to manually specify detected height tiers. `--force` replaces windows and parts in an existing spec, so use a different output file after facade work. **Original GLB meshes and textures are never copied into the asset.** See [GLB Mass Reconstruction](docs/agent/GLB_MASS.md) for details.

### Naver VR Capture and Paint photo_refs

`capture/naver_vr.py` saves per-tower multi-angle photos with camera/plane metadata. `make_refs` merges only truly coplanar runs (≤20° / ≤3 m) and picks the best frontal, highest-visible-height, highest-resolution photo per wall.

```bash
python capture/naver_vr.py auto --url https://fin.land.naver.com/complexes/<id>/tour --project <name> --make-refs
python capture/naver_vr.py run --dongs 101 --fit-wall --angles 4
python capture/naver_vr.py make_refs --dir capture/out/<complex> --dongs 101 --prefix photos/ --debug
python tools/band_scan.py --refs photo_refs.json --name 101_p1_1 --fh 2.9 --out previews/paint_grid
```

Run `make_refs --report work/refs_report.json` to see **which planes lack photos**, why, and per-plane resolution (px/m). Window-width reading needs ≥20 px/m; if lower, recapture wider (upsampling adds no information).

`auto` launches Chrome in debug mode from a single URL, captures directly into `projects/<name>/photos`, and writes `TASK.md` for new projects or `TASK.auto.md` suggestions for existing ones. Existing photos are not overwritten without `--overwrite`.

You can also draft tower mass from `data.xrx.json` alone:

```bash
python tools/xrx_mass.py --project my-apt --xrx photos/data.xrx.json --dongs 101 --force --json
```

See [Naver VR Metadata Mass](docs/agent/XRX_MASS.md) for coordinate rules and limits.

Exclude trees, signs, shadows, etc. via normalized wall U/V coordinates using `paint_include` / `paint_exclude`. Windows are auto-masked; undecided cells stay `cell_id=-1` to keep the base wall material. Always verify `_mask.png` and refs debug images. Capture resume, camera fields, and performance options are in [Naver VR Capture & Paint Refs](docs/agent/NAVER_VR.md).

Normalize shadows when sampling colors. Shaded walls share the same material, so scale each block against a bright white wall to avoid a darkened palette.

```bash
python tools/shadow_norm.py --project my-building \
  --refs photo_refs.json --out-refs photo_refs_lit.json
```

`--refs` corrects all photos referenced by refs at once and writes a **new refs file with updated paths** (originals untouched). Use this file for painting/color measurement; keep the original refs for geometry. Details in [Shadow Normalization](docs/agent/SHADOW_NORM.md).

### Mapping Photo Planes to Model Walls

Capture photos know their own plane (scene meters); the model knows its walls (model meters). Align them to place window columns.

```bash
python tools/photo_plane_map.py --project my-building \
  --meta photos/<dong>_meta.json --mass generic_spec.json --refs photo_refs.json
python tools/facade_read.py --project my-building --refs photo_refs.json \
  --plane-map work/plane_to_edge.json --table
python tools/qa/plane_compare.py --project my-building --asset output/<asset> \
  --meta photos/<dong>_meta.json --refs photo_refs.json --plane-map work/plane_to_edge.json
```

- `photo_plane_map`: tells you **which model walls a photo plane covers, the meter offset, left/right flip, and actual resolution (px/m)**.
- `facade_read`: reads window columns **in meters** from the plane photo, finds louver bands, and writes a generator-ready table + `facade_read.json` (`--json` for machine summary).
- `plane_compare`: side-by-side photo/model comparison with **block SSIM and edge overlap auto-scoring**. Below-threshold results go to `photo_mismatch_notes.yaml` and can be appended to the spec via `--spec`.

If resolution is too low (<20 px/m for window width), that photo cannot measure windows — recapture. See [Photo Plane → Model Wall Mapping](docs/agent/PHOTO_PLANE_MAP.md).

### Working from Photos Without GLB

`tools/evidence.py` links photos and observations to walls. It records camera direction, occlusion, measurable items, source hash, and confidence. Windows are stored in wall-local U/V coordinates, not full-image pixels.

```bash
python tools/agent.py evidence --project my-apt --json -- photo \
  --photo photos/front.jpg --photo-id front_main --wall main:front \
  --view frontal --use floors,bays,color --confidence high --note "full wall"

python tools/agent.py evidence --project my-apt --json -- feature \
  --wall main:front --kind window --u 0.12,0.19 --v 0.20,0.78 \
  --floor 7 --photo-id front_main --confidence high --note "measured edges"

python tools/agent.py evidence --project my-apt --json -- validate
```

Records are saved to `work/photo_evidence.json`. Low-confidence measurements must be marked `estimated`.

`photo_refs.json` wall entries support:

- `wall_id`: links to actual walls in `manifest.metadata.walls`
- `size_m`: real width/height inside the four corners
- `box`: generator coordinate box rendering only that wall
- `yaw_deg`: optional explicit camera angle
- `confidence`, `occluded`: judgment confidence and occlusion notes

Camera yaw is derived from wall `normal_deg` with pivot shift applied, so protruding/recessed walls are compared by their actual wall area, not the whole building size. Low-confidence photos or weak patterns do not trigger auto floor-count changes.

A single frontal photo cannot determine depth or hidden geometry. Leave those as estimates and verify with oblique or multi-angle shots when possible.

### Natural Language and Styles

Recurring decisions (floor count, era, type, window family) can be drafted from a short description.

```bash
python tools/brief.py --project my-apt --text "2020s tower apartment 36F, extended, split-facade windows" --json
python tools/style_catalog.py --project my-apt --json
```

`brief.py` picks a style from `templates/styles/*.yaml` and writes `building_brief.yaml` with palette, window dimensions, band/spandrel, and night-light policy. The generator reads the same values via `templates/facade_style.py`.

`brief.py` is a deterministic parser, **not an LLM call**. Values not in the text and floor-count defaults are marked `estimated`. Natural language alone cannot fix footprint shape, bay count, or hidden faces. Nail mass first with GLB or measured dims, then correct window positions, entrance, and podium with photos and `work/photo_evidence.json`.

### Other Input Methods

| Input | Support | Use & Limits |
|-------|---------|--------------|
| GLB scan only (no photos) | Supported | `glb-mass` for mass/planes/tiers + style preset for facade. Photo checks = `NOT_APPLICABLE`. |
| Naver VR metadata only (no photos) | Partial | `tools/xrx_mass.py` for per-tower footprint/height mass draft. No facade evidence. |
| Satellite / plan images | Supported | `photo_refs.json` `satellite` for roof shape and W/D ratio. Not facade evidence. |
| Drawings / dimension text | Supported | Write directly to `TASK.md` and `generic_spec.json`. Windows/materials from photos or style. |
| Natural language only (no photos) | Partial | Style/floor draft only. Bays/entrance/colors are estimates. Photo gates empty. |
| Drone / 360° photos | Partial | Drone photos used as regular photos. 360/equirectangular → `tools/crop_360.py` for perspective crops. |
| IFC / CAD / BIM | Needs conversion | `tools/ifc_to_glb.py` to check conversion path, export GLB, then `glb-mass`. |
| Other 3D assets | Mass reference only | Import GLB, simplify mass only. Original meshes/textures **not copied**. |
| Video walkthrough | Partial | `tools/video_frames.py` to extract frames as photos. No auto-alignment. |

Drone/360 photos use the same pipeline after perspective crop.

```bash
python tools/crop_360.py --project my-apt --image photos/pano.jpg \
  --yaws 0,90,180,270 --fov 90 --out photos/crops
```

See [360° Perspective Crop](docs/agent/PANORAMA_360.md) for yaw rules and limits.

Extract video frames into the photo pipeline.

```bash
python tools/video_frames.py --project my-apt --video photos/walk.mp4 \
  --every 2.0 --width 1600 --out photos/frames
```

If ffmpeg is missing: `pip install imageio-ffmpeg`. See [Video Frame Extraction](docs/agent/VIDEO_FRAMES.md) for segment/count/quality options.

Check captured/extracted photo quality before facade work.

```bash
python tools/photo_quality.py --project my-apt --dir photos --json
```

Blur/resolution/duplicate/exposure criteria in [Photo Quality Gate](docs/agent/PHOTO_QUALITY.md). Normalize shadows against white walls when sampling colors.

```bash
python tools/shadow_norm.py --image photos/wall.png --out photos/wall_lit.png --block 64
```

`shadow_norm` computes per-block scale factors against a bright white wall so shaded walls measure the same material color.

Convert IFC/CAD to GLB first, then build mass.

```bash
python tools/ifc_to_glb.py --check --json
python tools/ifc_to_glb.py --plan
```

BlenderBIM/Bonsai, IfcConvert, FreeCAD paths and post-conversion checks in [IFC to GLB](docs/agent/IFC_TO_GLB.md).

### Mixed-Use / School / Irregular Buildings

`--template generic` composes **multiple volumes and per-wall parts** instead of apartment-only presets. Feed `generic_spec.json` with:

- Arbitrary simple-polygon footprints, per-volume height and base height
- Per-wall `window_band`, `shopfront`, `louver_zone`, `railing_zone`
- `sign_slot`, `roof_equipment`, `covered_link`, `entrance_canopy`

`build_volume_spec` emits FULL/SIMPLIFY_TRIM/LOD_CULL from the same data — no separate LOD design needed. LOD2 preserves multi-volume silhouettes.

Generated walls carry ID, length, height, normal, and render box in `manifest.metadata.walls` for direct photo-check linking. Arbitrary polygon roofs are triangulated; OBJ supports both tri and quad vertex UVs.

`example_generic_cs2.py` and `templates/generic_spec.example.json` are a synthetic main-building + angled gym combo. Quick, FBX, photo, tile, LOD, and visual review all PASS. Curved surfaces and very complex junctions still need a custom generator.

## 3. Running with Claude Code

### 3-1. Getting Started

1. Install [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) and log in (`claude` then follow prompts).
2. Run from the **kit root** (the folder containing this README) so `CLAUDE.md`, `AGENTS.md`, and `.claude/` settings are auto-loaded.

```bash
cd <kit-root>
claude
```

On first launch, `CLAUDE.md` rules (Korean responses, model roles, completion criteria) apply. `.claude/settings.json` pre-approves `python tools/...` runs so checks don't prompt for approval. Other commands prompt normally.

### 3-2. Model Settings

Type `/model` in-session to pick a model; the choice becomes the new-session default.

```text
/model
```

Or specify at launch:

```bash
claude --model <model-name>
```

Recommended (not required): main Sonnet 5.5 + advisor Opus 5.5. The main model does design, debugging, code edits, and photo/render judgments directly; only hard forks go to the advisor.

| Role | Recommended |
|------|-------------|
| Main (design, debugging, code edits, photo/render judgment) | Sonnet 5.5 |
| Advisor (design finalization, repeated errors) | Opus 5.5 |
| File search, long-log commands | Subagents (Explore, runner) per `CLAUDE.md` — no extra config needed |

This kit's instructions and skills are tuned for the above. Other models work but may yield lower quality on photo reading, shape judgment, and fix accuracy.

**Image input is required** for photo comparison. If unavailable, the kit stops at `NEEDS_HUMAN_REVIEW` and never invents findings.

### 3-3. Advisor Setup

The advisor is a stronger review model consulted before design lock or when stuck. Enable in-session:

```text
/advisor
```

Pick Opus 5.5 (or any model stronger than main). Once set, it persists across sessions. `CLAUDE.md` only calls the advisor in two cases:

- Just before locking design/approach (photo analysis done, chunk done, before proposing user-approved changes)
- Same error persists after two fixes

Otherwise it stays idle, so cost stays low.

### 3-4. Providing Input

Work goes to two places.

**① `TASK.md` — Building Info (Primary)**: Write building name, floor count, photo locations, features in `projects/<name>/TASK.md`. `/build` reads this and builds. See [§2](#2-creating-a-new-project) and `templates/`.

**② Prompt — Extra Instructions**: Append natural language after the skill.

```text
/build
/build emphasize rooftop water tank detail
/fix lower 2F shop sign band by 0.4 m
/style-research 2020s slab apartment 30F
```

General chat works too: `Check floor count from this building photo`. Attach files with `@projects/<name>/photos/front.jpg` or drag images in. **Original photos must never be modified/moved/copied** — reference them in-place under `photos/`.

Input tips:

- Be specific with numbers/positions: not "balcony looks small" but "3–12F balcony depth to 1.2 m".
- Request one change at a time so `/fix` can scope verification.
- If interrupted, `/resume` continues from saved `next_action`.
- Kit-filled estimates appear in YAML as `# estimated` and in the final report. Correct wrong ones via prompt.

### 3-5. Skills

```text
/build
```

Extra requests can be appended:

```text
/build emphasize rooftop water tank detail
```

Available skills:

- `/build`: Full production
- `/resume`: Resume from saved `next_action`
- `/photo-refs`: Generate/validate photo corner coordinates
- `/photo-observe`: Read one wall photo with zoom/checklist, cross-check measurements, record via `agent.py observe`
- `/fix <request>`: Scoped fix, final gate, outside-scope diff
- `/style-research <building description>`: Research natural-language building type into facade style YAML draft + brief, stop for user review

Skills call `tools/agent.py`. No duplicate checkers or modeling rules.

## 4. Verification & Completion Criteria

| Mode | Checks | When to Use |
|------|--------|-------------|
| `quick` | OBJ generation, spec/geometry checks | Syntax/coord/overlap fix loops |
| `visual` | Preview + photo comparison | After mass/window/facade/material changes |
| `final` | FBX + photo/tile/LOD + strict gate | Pre-final-report and after scoped fixes |

Run manually with explicit project and generator:

```bash
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode quick --label mass --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode visual --label windows --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode final --label final --json
```

Result statuses:

- `PASS`: All requested checks passed.
- `FAIL`: An executed check failed.
- `INCOMPLETE`: Required check or image verification missing.
- `NOT_APPLICABLE`: No `photo_refs.json` → photo checks not applicable.
- `NOT_CHECKED`: Not yet verified; **do not interpret as PASS**.

After visual/final, inspect the current preview and comparison images listed in `next_action`, then record the result on the same artifact:

```bash
python tools/agent.py review --project my-apt --status PASS --note "reviewed final images" --artifact previews/<asset>.png --json
```

Photo sheets also need `--artifact` if photo checks ran. `PARTIAL` (only some images seen) is **not PASS**; if images can't be viewed, use `NEEDS_HUMAN_REVIEW`.

If LOD candidates are needed, build LOD1/LOD2 from the main `.blend` and run a quick hole check:

```bash
python tools/lod_auto.py --project my-apt --asset output/<asset> --check --json
```

`--check` runs 16-view quick test. Before final report, use `--check-full` or `tools/qa/lod_check.py` for full check. See [LOD Auto Candidates](docs/agent/LOD_AUTO.md).

The Stop hook notifies the saved `next_action` if final/fix exits without PASS. Report the failure reason as-is.

## 5. Photos, Outputs, Resume

Photos are reviewed contact-sheet → representative → zoom on ambiguous areas. Not every original and zoom is read repeatedly.

```bash
python tools/agent.py photos --project my-apt --page 0 --page-size 16 --json
python tools/agent.py observe --project my-apt --photo photos/front.jpg --side front --note "36 floors" --json
```

Key files:

- `output/<asset>/`: FBX and textures
- `previews/`: Previews and photo comparisons
- `work/agent_state.json`: Last verification, generator hash, next action
- `work/observations.json`: Photo observation log
- `STATUS.md`: Short handoff summary

Resume and scoped fix:

```bash
python tools/agent.py resume --project my-apt --json
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --request "change only entrance railing" --box=-5,5,-1,1,0,6 --json
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --finish --json
```

`/fix` automates this flow. If final gate or outside-scope diff fails, it does not report PASS.

## 6. Generation Rules

- 1 unit = 1 m, ground `z=0`, front/street = `-Y`.
- Generators use `import cs2kit as K` for `Atlas`, `MeshBuilder`, `WindowSet`, `export_asset`.
- LOD1 < 50% of main, LOD2 ≤ 500 tris.
- Main targets 30k–60k tris; >95k triggers a warning.
- **Never reduce actual floors, bays, or window positions just to cut triangles.**
- User-authored `photo_refs.json` is never modified.

## 7. Further Reading

- [Install & Upgrade](INSTALL.md)
- [Documentation Map](docs/README.md)
- [Full Workflow](docs/agent/WORKFLOW.md)
- [Tools & API](TOOLS_CLAUDE.md)
- [Detailed Modeling Guide](docs/agent/MODELING.md)
- [Measured Facade](docs/agent/FACADE_MEASURED.md)
- [Facade Know-how](docs/agent/FACADE_KNOWHOW.md)
- [GLB Mass Reconstruction](docs/agent/GLB_MASS.md)
- [Naver VR Capture & Paint Refs](docs/agent/NAVER_VR.md)
- [Photo-Only Evidence](docs/agent/PHOTO_ONLY.md)
- [Facade Style & Brief](templates/styles/README.md)
- [360° Perspective Crop](docs/agent/PANORAMA_360.md)
- [Video Frame Extraction](docs/agent/VIDEO_FRAMES.md)
- [Photo Quality Gate](docs/agent/PHOTO_QUALITY.md)
- [LOD Auto Candidates](docs/agent/LOD_AUTO.md)
- [IFC to GLB](docs/agent/IFC_TO_GLB.md)
- [Naver VR Metadata Mass](docs/agent/XRX_MASS.md)
- [Mixed-Use / School / Irregular Volumes](docs/agent/VOLUMES.md)
- [Memory Scope](docs/agent/MEMORY.md)

## Known Limitations

Previews are simple orthographic renders; colors/brightness differ from in-game. Photo metrics are vulnerable to trees, shadows, and perspective. `facade_read.py` and `band_scan.py` are v1 and need human photo verification. FBX and LOD require Blender. Verify in-game: real scale, window grid, alpha, flicker, night lights, front direction, colors, entrance, and signature registration.