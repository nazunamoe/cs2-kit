# tools/ — 도구 폴더 지도

모든 명령은 **키트 루트**에서 실행한다(`python tools/<경로>`). 도구가 활성 프로젝트(`projects/<이름>/`)로 옮겨 실행하므로
`output/`, `previews/`, `photo_refs.json` 같은 상대 경로는 그 프로젝트 기준이다(`tools/proj.py`).

| 폴더 | 무엇 | 대표 명령 |
|---|---|---|
| `tools/*.py` (코어) | 만들기·검사·그림·사진 비교·프로젝트 관리 | `cycle.py`, `check.py`, `render.py`, `photo_check.py`, `tile_compare.py`, `sat_grid.py`, `extract_texture.py`, `facade_paint.py`, `glb_measure.py`, `compare.py`, `project.py`, `run_blender.py` (`put/edit/show.py` 는 코드 편집 도우미) |
| `tools/qa/` | **검증** (보고 전) | `verify.py`(병렬 일괄), `lod_check.py`(투명 구멍), `cmp_cam.py`(사진과 같은 카메라 비교), `lodcam.py`(LOD 하나만 뒷면 숨김 렌더), `modcam.py`(낮은 거리 카메라 렌더) |
| `tools/scan/` | 스캔(.glb) 분석·읽기 | `scan_tool.py list|info|roof|slice|elev|top|compare|report`, `scanlib.py`; 텍스처 풀기 `ktx2raw.js`+`raw2png.py`(KTX2→PNG; 변환기 `basis/` 는 배포본에 없음 — three.js `examples/jsm/libs/basis` 의 `basis_transcoder.cjs/.wasm` 을 `tools/scan/basis/` 에 둔다), `strip_glb.py`(블렌더용); 단면·높이장 `slice.py`, `slicez.py`, `toplevels.py`, `toptable.py`; 위에서 본 정사영 `top.py` |
| `tools/facade/` | 입면 측정·비교 (스캔 정사영, 창·띠·난간 측정, VR 카메라 렌더) | `pair_ortho.py`(단일 면, 또는 `--frames` 여러 면 일괄), `elevstat.py cols|profile|runs|rows`, `winlist.py`, `wmask.py`, `model_photo_cam.py`, `scan_photo_cam.py`, `elev.py`, `scancam.py`, `scancam_raw.py`, `rail_edges→rail_survey→rail_decide→rail_table`(활성 프로젝트의 생성기를 `_gen.py` 가 찾음), `vsphoto.py`, `coplanar_diag.py` … README |
| `tools/samhan_facade/` | 특정 생성기 구조(평면 API `HALF`, `edges_of()`, `floor_z()` …)와 사진 등록부에 묶인 도구. 같은 일을 생성기 없이 하는 공용판 = `tools/facade_paint.py` + `tools/facade/winlist.py` | `refuge_scan.py`, `window_template.py` … README |

## 병렬 검증 (`tools/qa/verify.py`)
`python tools/qa/verify.py --label <단계>` — `cycle.py --no-render`(빌드+규격 검사)가 통과하면 `lod_check`·미리보기 렌더·`cmp_cam`(프로젝트 `verify.json` 의 사진 목록)·(`photo_refs.json` 이 있으면) `tile_compare`/`photo_check` 를 동시에 돌려 한 번에 요약한다.
`verify.json` 예: `{"generator": "x_cs2.py", "ground": 74.51, "shots": [{"photo": "photos/101_side1.png", "meta": "photos/101_meta.json", "crops": {"roof": [1260,300,1760,640]}}]}`

## 사진과 같은 카메라로 비교 (`tools/qa/cmp_cam.py`)
meta 카메라(거리·fov·높이)로 에셋 `.blend` 를 렌더해 사진 실루엣에 맞춰 정렬하고 `pair_*.png`(사진 | 모델), `blend_*.png`(50% 겹침)를 만든다. 렌즈는 세로 화각 `fov_v` 가 되도록 `18/(tan(fov_v/2)·W/H)` (Blender 센서 36 mm 는 가로에 걸린다). 생성기 틀이 스캔에서 회전·이동된 건물은 `--frame work/frame_<동>.json`(에셋 좌표 = 생성기 좌표 + `manifest.json` 의 `pivot_shift`).

## 여러 면 정사영 비교 (`pair_ortho.py --frames`)
`python tools/facade/pair_ortho.py --blend output/<에셋>/<에셋>.blend --frames work/scanframe_<동>.json --dong <동>` — 파일 형식은 `pair_ortho.py` 맨 위 설명.
