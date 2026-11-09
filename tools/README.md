# tools/ — 도구 폴더 지도

모든 명령은 **키트 루트**에서 실행한다(`python tools/<경로>`). 도구가 활성 프로젝트(`projects/<이름>/`)로 옮겨 실행하므로
`output/`, `previews/`, `photo_refs.json` 같은 상대 경로는 그 프로젝트 기준이다(`tools/proj.py`).

| 폴더 | 무엇 | 대표 명령 |
|---|---|---|
| `tools/*.py` (코어) | 만들기·검사·그림·사진 비교·프로젝트 관리 | `cycle.py`, `check.py`, `render.py`, `photo_check.py`, `tile_compare.py`, `sat_grid.py`, `extract_texture.py`, `facade_paint.py`, `glb_measure.py`, `compare.py`, `project.py`, `state.py`, `docs_gen.py`, `run_blender.py` (`put/edit/show.py` 는 코드 편집 도우미) |
| `tools/qa/` | **검증** (보고 전) | `verify.py`(병렬 일괄; `--fast` 반복용, `--all-shots`, 점수 기록), `cmp_all.py`(meta 사진 전부 비교), `plane_compare.py`(같은 평면 자동 채점), `lod_check.py`(투명 구멍; `--quick`), `cmp_cam.py`(사진과 같은 카메라 비교), `lodcam.py`(LOD 하나만 뒷면 숨김 렌더), `modcam.py`(낮은 거리 카메라 렌더) |
| `tools/scan/` | 스캔(.glb) 분석·읽기 | `scan_tool.py list|info|roof|slice|elev|top|compare|report`, `scanlib.py`; 텍스처 풀기 `ktx2raw.js`+`raw2png.py`(KTX2→PNG; 변환기 `basis/` 는 배포본에 없음 — three.js `examples/jsm/libs/basis` 의 `basis_transcoder.cjs/.wasm` 을 `tools/scan/basis/` 에 둔다), `strip_glb.py`(블렌더용); 단면·높이장 `slice.py`, `slicez.py`, `toplevels.py`, `toptable.py`; 위에서 본 정사영 `top.py` |
| `tools/facade/` | 입면 측정·비교 (스캔 정사영, 창·띠·난간 측정, VR 카메라 렌더) | `pair_ortho.py`(단일 면, 또는 `--frames` 여러 면 일괄), `elevstat.py cols|profile|runs|rows`, `winlist.py`, `wmask.py`, `model_photo_cam.py`, `scan_photo_cam.py`, `elev.py`, `scancam.py`, `scancam_raw.py`, `rail_edges→rail_survey→rail_decide→rail_table`(활성 프로젝트의 생성기를 `_gen.py` 가 찾음), `vsphoto.py`, `coplanar_diag.py` … README |
| `tools/photo_facade/` | 특정 생성기 구조(평면 API `HALF`, `edges_of()`, `floor_z()` …)와 사진 등록부에 묶인 도구. 같은 일을 생성기 없이 하는 공용판 = `tools/facade_paint.py` + `tools/facade/winlist.py` | `refuge_scan.py`, `window_template.py` … README |

`tools/sync_branches.py` 는 저장소 관리용이다(프로젝트 chdir 없음). 원격에서 fetch 한 뒤 로컬 브랜치를 **ff-only**로만 맞추고, 브랜치 간 드리프트(한쪽에만 있는 커밋)를 보고한다. `--check` 는 쓰기 없이 검사만 하고 드리프트가 있으면 exit 1.

`tools/state.py` 는 `work/agent_state.json` 을 `work/state.yaml` 로 투영한다(단계·게이트·산출물 해시). `tools/docs_gen.py` 는 각 도구의 `--help` 로 `docs/agent/TOOL_<name>.md` 를 다시 쓴다. 둘 다 프로젝트/키트 루트에서 실행한다.

## 통합 검증 (`tools/qa/verify.py`)
`python tools/qa/verify.py --label <단계>` — 공통 `cycle.py final` gate 를 실행한 뒤, 프로젝트 `verify.json` 에 지정한 same-camera 검사를 병렬로 추가한다. 일반 실행은 strict final 이므로 FBX·LOD·미리보기·사진·타일 결과가 한 gate 에 모인다.
`verify.json` 예: `{"generator": "x_cs2.py", "ground": 74.51, "shots": [{"photo": "photos/101_side1.png", "meta": "photos/101_meta.json", "crops": {"roof": [1260,300,1760,640]}}]}`

## 사진과 같은 카메라로 비교 (`tools/qa/cmp_cam.py`)
meta 카메라(거리·fov·높이)로 에셋 `.blend` 를 렌더해 사진 실루엣에 맞춰 정렬하고 `pair_*.png`(사진 | 모델), `blend_*.png`(50% 겹침)를 만든다. 렌즈는 세로 화각 `fov_v` 가 되도록 `18/(tan(fov_v/2)·W/H)` (Blender 센서 36 mm 는 가로에 걸린다). 생성기 틀이 스캔에서 회전·이동된 건물은 `--frame work/frame_<동>.json`(에셋 좌표 = 생성기 좌표 + `manifest.json` 의 `pivot_shift`).

## meta 사진 전부 비교와 점수 기록 (`cmp_all.py`, `scores.py`, `verify.py` 옵션)
- `python tools/qa/cmp_all.py --asset output/<에셋> --meta photos/<동>_meta.json --ground <지면 표고>` — meta 의 사진 전부를 같은 카메라로 렌더(Blender 1회, `multicam.py`)하고 실루엣 IoU 가 최대가 되게 크기(1±0.1)·위치를 맞춘 뒤, 표(IoU·scale)·사진별 `pair.png`·접촉 시트 `sheet_*.png`(긴 변 1000 px 이하)를 `work/chk_all/` 에 쓴다. 방위는 `az = 180 + angle` (한 건물 8방위를 눈으로 확인한 규칙이므로 다른 캡처는 시트로 먼저 확인, 아니면 `--az-offset`).
- IoU 는 회귀 감시용이다: 거의 대칭인 건물에서는 반대 면도 비슷하게 나오고 크기 변화는 흡수하며 창·기둥 같은 구조는 못 본다. 시트와 pair 를 눈으로 본다.
- `verify.py --fast` = 공통 quick OBJ/규격 검사(끝 줄 `VERIFY FAST` 는 보고용 아님), `--all-shots` = 위 비교 포함. 매번 `work/chk/scores.json` 에 IoU·scale·LOD 최대 구멍·tris 를 쌓고 전보다 나빠지면 `SCORES REGRESS`/`SCALE_CHANGE` 를 낸다.
- `lod_check.py --quick` = 16시점·256 px(약 5 s). 얇은 구멍을 놓칠 수 있어 결과 줄이 `LODCHECK QUICK`. `cmp_cam.py --max-side N` = pair/blend 그림 축소(토큰 절약).

## 여러 면 정사영 비교 (`pair_ortho.py --frames`)
`python tools/facade/pair_ortho.py --blend output/<에셋>/<에셋>.blend --frames work/scanframe_<동>.json --dong <동>` — 파일 형식은 `pair_ortho.py` 맨 위 설명.
