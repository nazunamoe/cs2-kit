# facade 측정 도구 (스캔 정사영 → 창·도색 표)

`facade_engine.py`(키트 루트)의 zone 표를 채울 때 쓴다. 모두 `FACADE_PPM`(기본 20 px/m), `FACADE_ZTOP`(그림 위 끝 z, 기본 97)을 환경변수로 받는다.

| 도구 | 용도 |
|---|---|
| `elevs.py` | Blender 에서 스캔 glb 한 메시를 텍스처째 정사영으로 여러 장 렌더. `blender -b -P elevs.py -- <scan.gltf> <mesh> <ppm> <절대경로 출력접두> yaw:view:a0:a1:z0:z1 ...` (출력 경로는 반드시 절대경로) |
| `dumpw.py` | 같은 변환을 정점에 적용해 (모델좌표 ↔ 정사영좌표) 대응을 json 으로 덤프 → 회전한 동체의 `a` 좌표 변환식(회전 + 이동)을 최소제곱으로 구할 때 |
| `mkframe.py` | 층 바닥 높이 json (`mkframe.py <1층 z> <층고> <층수> frame.json`) |
| `winlist.py` | 한 주기(층)의 창 목록 → `wa=[(a0, a1, (sill, head)), ...]` |
| `wmask.py` | 흰 틀(기둥·띠) 사각형 목록 → `wf=[dict(r=[...])]` |
| `colstrips.py` | 세로로 끝까지 이어지는 흰 띠·갈색 띠 |

주의: `elevs.py` 는 메시를 bbox 가운데로 옮긴 뒤 `-yaw` 만큼 돌려 그린다(가로축 a 는 view 0: +x, 90: +y, 180: -x, 270: -y).
정사영의 a 를 생성기 좌표로 바꾸는 식은 반드시 `dumpw.py` 로 확인한다(눈짐작으로 하면 몇 m 어긋남).

## 추가된 도구 (여러 프로젝트에서 같은 파일이 반복돼 공용으로 옮김)
| 도구 | 용도 |
|---|---|
| `pair_ortho.py` | **스캔 정사영 \| 모델 정사영을 같은 축척으로 나란히**. `--auto-shift` 가 가로 어긋남(회전 동체 30 px 등)과 상관값을 알려 줌. 면을 고칠 때마다, 보고 전에는 모든 면에 |
| `modelelev.py` | (Blender) 에셋 .blend 의 정사영 렌더. `pair_ortho.py` 가 부름. view 180 은 가로 범위 부호가 월드 x 와 반대 |
| `coplanar_diag.py`, `coplanar_pair.py` | (Blender) COPLANAR 면 쌍의 위치·재질 찾기 (레일 끝 vs 기둥 3 mm 같은 경우) |
| `winx.py`, `wmeas.py`, `slotwin.py`, `shelves.py` | 정사영에서 여러 층 중앙값으로 창 가로/세로, 계단실 작은 창, 창턱 선반 재기. **층 무늬 주기에 맞춰** 쓴다 |
| `fcrop.py`, `crop.py`, `floors.py` | 정사영 확대 + 생성기 좌표 눈금 / 층 줄 번호 그림 |
| `secimg.py`, `secseg.py`, `topmap.py`, `hmap.py`, `dumptop.py`, `meshnpz.py` | 스캔 수평 단면·위에서 본 높이장·선분을 벽으로 합치기 |
| `rail_edges.py` → `rail_survey.py` → `rail_decide.py` → `rail_table.py` (+ `rail_plan.py`, `rail_report.py`) | 옥상 가장자리의 띠가 흰 벽인지 철제 난간인지 텍스처 색으로 가르는 조사 → `ROOF_RAILS` 표 |
| `vsphoto.py` | 사진 \| 같은 방향 렌더 |
| `scan_photo_cam.py`, `model_photo_cam.py` | **VR 사진과 같은 카메라(pos·fov)로 스캔 / 모델을 렌더**해 사진과 나란히 (사진 = 스캔 렌더 확인됨). 사진 픽셀 → 벽 위치 환산의 기준 |
| `ktx2png.js` | glb 의 KTX2 텍스처를 PNG 로 (three.js basis_transcoder 필요) |

일부는 옛 프로젝트의 인자 순서·환경변수를 가정한다. 각 파일 머리의 usage 주석을 먼저 읽는다. 정리된 노하우는 `docs/FACADE_KNOWHOW.md`.

`rail_edges.py` / `rail_plan.py` / `rail_table.py` 는 생성기 파일 경로를 환경변수 `FACADE_GEN`에서 읽는다(절대 경로로 줄 것. 기본값 `generator_cs2.py` 는 `tools/scan/` 기준이라 대개 맞지 않는다).

## 2026-11-03 추가·통합
| 도구 | 용도 |
|---|---|
| `pair_ortho.py --frames work/scanframe_<동>.json --dong <동> --blend ...` | 여러 면 일괄 비교 (옛 pairE/pair/pair2/cmp). 파일 형식은 `pair_ortho.py` 맨 위 설명 |
| `elevstat.py cols\|profile\|runs\|rows` | 정사영 한 장의 가로 창 열·색 클래스 줄·여러 높이 창 구간·창 줄 간격 (옛 wincols/profile/runs/rows) |
| `elev.py` `scancam.py` `scancam_raw.py` `mgrid.py` `sheet.py` | 스캔 정사영 한 면, 생성기 좌표 원근 렌더 / 스캔 좌표 그대로 원근 렌더, 미터 눈금 크롭, 콘택트 시트 |
| `rail_edges/plan/table.py` `vsphoto.py` | 활성 프로젝트 생성기를 `_gen.py` 로 찾음(프로젝트 폴더 안 가정 없음) |
