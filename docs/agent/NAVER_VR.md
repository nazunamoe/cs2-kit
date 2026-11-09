# Naver VR capture and paint-accurate photo refs

Use `capture/naver_vr.py` when a Naver complex tour provides repeatable building views and `data.xrx` geometry/camera metadata. It requires Playwright. `auto` starts Chrome with remote debugging itself; the older `run`/`batch` commands still expect a Chrome window opened by hand. It is separate from the normal project photo workflow.

## One-command URL flow (`auto`)

```bash
python capture/naver_vr.py auto \
  --url https://fin.land.naver.com/complexes/125062/tour \
  --project namsan_xihanulche \
  --dongs 101,107 --fit-wall --angles 4 --make-refs --dry-run
```

Remove `--dry-run` to capture. The command:

1. accepts only `land.naver.com` tour URLs and rejects a page whose `data.xrx` id differs from the URL;
2. reuses port 9222 or launches Chrome with a dedicated profile (`capture/.chrome-vr`) at `--window-size 2400,1800` (larger canvas = more ref pixels);
3. creates `projects/<name>` with `project.py new` when missing; an existing project's TASK/generator is not touched;
4. writes captures straight into `projects/<name>/photos` (no second copy of the images);
5. refuses to overwrite existing captures unless `--overwrite`; partial captures from this tool resume;
6. `--make-refs` merges one best planar view per exact plane into `<project>/photo_refs.json` and writes `photos/refs_check/`;
7. writes TASK: a new project gets `TASK.md`; an existing project gets `TASK.auto.md` only. `--task write` forces the write with `TASK.md.bak`.

TASK fields are filled only while empty or still holding the template placeholder: `building`, `photos`, `complex_name`, `floors` (highest selected dong), `known_facts`, `blender_path`. `name`, `region`, `built_year` are filled only when `--asset-name`, `--region`, `--built-year` are passed. `glb`, `refuge_floor`, `size_m`, `louver`, `railing`, `balcony`, `curtainwall`, `window_type` stay for the human because the tour data does not prove them.

Useful options: `--refs-min-px 200` (lower accepts narrower planes), `--on-blocked ask` (wait for a popup/login), `--close-chrome` (close only the Chrome that `auto` started). If the facade count is low, inspect `photos/refs_check/`; a larger `--window-size` or `--angles 8` adds pixels/directions.

## What the capture command does

For each selected building, `run`/`batch`:

1. Opens the tour and captures `applyCamera`, scene, footprint, and building metadata.
2. Focuses one building, hides DOM labels and translucent listing-highlight meshes, and selects image quality.
3. Fits the building or selected wall to the requested screen width.
4. Rotates through 8 directions, or 4 wall-aligned directions with `--fit-wall`.
5. Extends the allowed vertical camera range, captures overlapping top-to-bottom sweeps, and waits for image stability.
6. Saves `<dong>_side<N>.png` plus `<dong>_meta.json` with camera view/projection matrices, actual azimuth, image size, ground/roof, footprint, and wall groups.

`list` lists buildings, `overview` captures complex overviews, and `probe` diagnoses rotation/camera behavior. Existing source photos are not edited.

```bash
pip install playwright
python capture/naver_vr.py list
python capture/naver_vr.py run --dongs 101,103 --fit-wall --angles 4
python capture/naver_vr.py batch urls.txt --file urls.txt
```

`run`/`batch` need a Chrome instance already running with remote debugging port 9222 and the Naver tour open. `auto` starts that Chrome itself. See the header of `capture/naver_vr.py` for the manual command.

## Performance and resume

Capture time is dominated by browser rendering, stable-frame screenshots, vertical overlap, and the number of directions/buildings. Reduce only unnecessary work:

- Use `--dongs` and `--fit-wall --angles 4` for targeted work.
- Use `--width 0.10 --center` when the whole wall must fit in one frame: the camera backs off to the viewer limit, the target is centered, and `sweep` saves one image per direction instead of top/bottom segments. Resolution drops, so use a larger browser viewport for measurement.
- Increase `--width`/`--wall-frac` only when more source pixels are needed; larger values can require more images.
- Keep overlap sufficient to avoid holes in floor/paint evidence.
- Completed buildings with the identical capture configuration are skipped. Changed settings recapture that building; `--overwrite` forces recapture.
- A complex `DONE` file is written only when no building failed. Partial or failed runs are retried instead of being falsely treated as complete.
- `make_refs --per-wall 1` emits one best view per exact plane, reducing later photo checks and paint analysis. Use `--per-wall 0` only when multiple exposures/views are intentionally needed.

No browser timing benchmark was run for this revision. These changes remove repeated work; they do not claim a measured speed percentage.

## Planar photo refs

```bash
python capture/naver_vr.py make_refs --dir capture/out/<complex> --dongs 101 \
  --prefix photos/ --per-wall 1 --debug
```

The previous broad wall grouping could combine edges up to 20 degrees apart or 3 m apart in depth. A four-corner homography of such a group samples the wrong surface. The planar-v2 path instead:

- merges only contiguous edges within `--ref-plane-deg 2` and `--ref-plane-gap 0.05` metres;
- keeps the original capture wall group as `source_wall_i` and gives each exact plane a `source_plane_i`;
- projects the actual plane corners through the saved camera matrices;
- scores views by frontality (`face_cos**4`), visible height, and resolution;
- records `confidence`, `face_cos`, `visible_fraction`, `plane_error_m`, `normal_deg`, and `camera_az_deg`;
- marks views with `face_cos >= 0.95` as suitable for color by default.

Always inspect `refs_check/` with `--debug`. The homography is exact only for the supplied plane and camera; terrain, incorrect XRX footprints, hidden surfaces, balconies, and vegetation still require review. `side` and street-front direction remain assumptions.

## Paint exclusions and palette safety

Add exclusions to a facade entry in normalized whole-entry wall coordinates. V is bottom=0 and top=1, not a per-floor value.

```json
{
  "paint": {"use_for_color": true},
  "paint_exclude": [
    {"u": [0.0, 0.12], "v": [0.0, 0.25], "reason": "trees"},
    {"u": [0.42, 0.62], "v": [0.08, 0.18], "reason": "sign"}
  ],
  "paint_include": []
}
```

If `paint_include` is non-empty, only those regions are eligible. Then exclusions and automatically detected windows are removed. Use it for windows, trees, signs, people, vehicles, reflections, deep shadows, and mixed materials. Do not mark an unknown surface as a paint color.

```bash
python tools/band_scan.py --refs photo_refs.json --name 101_p1_1 \
  --ppm 30 --fh 2.9 --window-mode auto --k 4 --out previews/paint_grid
```

`band_scan.py` now:

- excludes detected window pixels and explicit include/exclude regions;
- computes spread from pixel variation, not differences between R/G/B channel values;
- requires at least 35% eligible pixels in a cell;
- preserves observed Lab lightness instead of forcing all colors to the same L;
- leaves mixed/unknown cells as `cell_id=-1` instead of copying a neighboring color;
- writes `<name>_mask.png`, sample coverage, warnings, and `review_required=true`.

`apply_facade_paint_grid` skips `-1`, leaving the base wall material unchanged. Inspect the mask and generated large paint rectangles before applying them. Real-photo color validation is still required; synthetic tests do not prove illumination correctness.
