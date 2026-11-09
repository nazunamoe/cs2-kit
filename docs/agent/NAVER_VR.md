# Naver VR capture and paint-accurate photo refs

Use `capture/naver_vr.py` when a Naver complex tour provides repeatable building views and `data.xrx` geometry/camera metadata. It requires Chrome with remote debugging and Playwright; it is separate from the normal project photo workflow.

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

A Chrome instance must already run with remote debugging port 9222 and the Naver tour open. See the header of `capture/naver_vr.py` for its exact command.

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

### 커버리지 리포트 (`--report`)

`make_refs`는 어떤 평면이 ref를 얻었는지, **왜 얻지 못했는지**, **해상도가 측정에 충분한지**를
json으로 남길 수 있다. ref를 못 만든 평면이 조용히 사라지면 나중에 "이 면은 사진이 없구나"를
모르게 되므로, 캡처를 마친 뒤 반드시 한 번 돌린다.

```bash
python capture/naver_vr.py make_refs --dir photos/ref101 --dongs 101 \
  --prefix photos/ref101/ --per-wall 0 --report work/refs_report.json
```

리포트 내용:

| 항목 | 뜻 |
|---|---|
| `planes[].refs[]` | 만들어진 ref (사진 파일, px/m, 보이는 높이, 정면성, 신뢰도) |
| `planes[].shots[]` | 각 후보 사진의 판정: `verdict`(used/skip/candidate)와 `reason` |
| `planes[].best_px_per_m` | 그 평면에서 얻은 최고 해상도 |
| `planes[].warnings` | "no ref for this plane", "only N px/m: too low to measure window widths" 등 |
| `warnings[]` | 전체 요약(사진 없는 6 m 이상 평면, 20 px/m 미만 평면) |

탈락 사유는 사람이 읽는 말로 나온다: `other wall group`, `not frontal (cos 0.42 < 0.85)`,
`visible height 3.1 m < 6.0 m`, `width 120 px < 300 px`.

**해상도가 곧 측정 가능 여부다.** 평면의 px/m 은 그 평면이 사진에서 차지하는 픽셀 밀도다.
`px/m` 이 20 미만이면 창 폭을 읽을 수 없고(루버 슬랫은 30 이상 필요), ref 파일을
리샘플해서 늘려도 정보는 늘지 않는다. 이때는 `--width`(기본 0.4)를 키우고 브라우저 뷰포트를
크게 잡아 **재캡쳐**해야 한다. 리포트 표에 `--min-px`/`--min-h`/`--min-cos` 임계값을 낮게
넣으면 평면 자체가 아니라 사진이 부족한 것이 원인이므로, 임계값으로 값을 고치지 말고
캡처 설정을 고친다.

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
