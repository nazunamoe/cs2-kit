# 도구 사용 안내 (Claude Code용)

CS2 한국 건물 에셋을 만들 때 쓰는 도구 모음이다. 모든 명령은 **키트 폴더(이 파일이 있는 곳)** 에서 실행한다.
규칙은 `CLAUDE.md`(+ `AGENTS.md`), 이 문서는 "어떤 도구를 언제 어떻게 쓰나"만 다룬다.

## 1. 한눈에 보기

| 하고 싶은 일 | 도구 | 한 줄 |
|---|---|---|
| 만들기 + 검사 + 미리보기 + 사진 비교를 한 번에 | `cycle.py` | `python tools/cycle.py <이름>_cs2.py --label 단계이름` |
| 프로젝트 관리 (새 건물·전환·이전·memory 만들기) | `project.py` | `python tools/project.py new <이름> [--template cw]` / `use` / `list` / `where` / `migrate <이름> --apply` |
| 검사만 | `check.py` | `python tools/check.py output/<에셋>` |
| 그림만 | `render.py` | `python tools/render.py output/<에셋> -o previews/a.png` |
| 사진 ↔ 모델 비교 | `photo_check.py` | `python tools/photo_check.py output/<에셋>` (보통 cycle 이 대신 부름) |
| 모델이 사진보다 단순한 곳 찾기 | `tile_compare.py` | `python tools/cycle.py <이름>_cs2.py --tiles` (또는 `python tools/tile_compare.py output/<에셋>`) |
| 사진에서 좌표 읽기 | `sat_grid.py` | `python tools/sat_grid.py grid 사진.jpg -o previews/g.png --step 50` |
| 사진에서 재질 뽑기 | `extract_texture.py` | `python tools/extract_texture.py 사진.jpg --pts ... --size 3.0x2.9 -o textures_src/stone` |
| 스캔(.glb)에서 치수 재기 | `glb_measure.py` | `python tools/glb_measure.py scan.glb --list` |
| 스캔(.glb) 단면에서 벽 세그먼트(각도) 뽑기 (신규, v1) | `tools/glb_slices.py` | `python tools/glb_slices.py scan.glb --z 1.5,15,30` |
| 사진 한 벽에서 층·창·도색 읽기 (범용) | `tools/facade_paint.py` | `python tools/facade_paint.py all --name front --fh 3.0 --feature-floor 29` |
| photo_refs 의 벽 전부를 U/V 정규화 좌표로 한 번에 (신규, v1) | `tools/facade_read.py` | `python tools/facade_read.py --refs photo_refs.json` |
| 벽을 층x열 그리드로 나눠 도색 색 뽑기 (신규, v1) | `tools/band_scan.py` | `python tools/band_scan.py --refs photo_refs.json --name front` |
| 상세 사진에서 층·도색·창 읽기 (특정 생성기용) | `tools/samhan_facade/*` | `python tools/samhan_facade/refuge_scan.py ...` (사용법: `tools/samhan_facade/README.md`) |
| 고치기 전/후 비교 | `compare.py` | `snap` → 수정 → `diff` |
| Blender 찾기·실행·FBX→OBJ | `run_blender.py` | `python tools/run_blender.py --find` |

`put.py` / `edit.py` / `show.py` 는 PowerShell 에서 작은 모델이 파일을 쓰기 위한 도구다. **Claude Code 에서는 쓰지 않는다**(Read/Write/Edit 사용).

**이름 겹침 주의**: `tools/samhan_facade/` 안에도 `glb_slices.py`/`band_scan.py` 가 있다 - 그건 삼한골든뷰
생성기 구조 전제(`README.md` 의 "생성기 조건")의 **별도 도구**다. 위 표의 `tools/glb_slices.py`,
`tools/band_scan.py` (키트 루트, 생성기 구조 전제 없음, 4번 절) 와 헷갈리지 않는다.

## 2. 기본 작업 흐름

(TASK.md 에 `complex_name` 이 있으면 모델링 전에 웹 조사 → `research_notes.md`. 도구가 아니라 CLAUDE.md 절차다.)

0. 활성 프로젝트 확인(`python tools/project.py where`), `memory/LESSONS.md` 읽기. 모든 상대 경로는 `projects/<이름>/` 기준이다(도구가 그 폴더로 옮겨 실행).
1. `TASK.md` 와 사진을 읽는다. 사진을 Read 로 직접 본다.
2. 사진이 있으면 `photo_refs.json` 을 **Claude Code 가 직접 만든다** → `/photo-refs` (사용자가 할 일 아님). 사용자가 이미 만들어 둔 파일은 건드리지 않고 그대로 쓴다. 이 파일이 없으면 `cycle.py` 의 사진 비교 단계가 빠진다.
3. 생성기는 `python tools/project.py new <이름>` 이 예제에서 복사해 둔다(커튼월·커튼월룩이면 `--template cw`).
4. 단계마다 `python tools/cycle.py <이름>_cs2.py --label <단계>` (덩어리 → 창 → 디테일 → 마지막)
5. `RESULT PASS` 와 `photo_mismatch=0` 이 될 때까지 고친다. 마지막은 `--label final`.
6. 일부만 고칠 때는 `/fix <내용>` (스냅샷 → 수정 → cycle → 변경 범위 확인).

슬래시 명령(스킬): `/build [추가 요청]` 전체 제작 · `/resume` 중단된 작업 이어서 · `/photo-refs` 사진 좌표 파일 만들기 · `/fix <내용>` 부분 수정.

## 3. 도구별 사용법

### cycle.py — 가장 많이 쓰는 도구
```bash
python tools/cycle.py my_building_cs2.py --label windows
python tools/cycle.py my_building_cs2.py --no-render           # 검사만 (그림 없음, 빠름)
python tools/cycle.py my_building_cs2.py --views front,iso --list 3
python tools/cycle.py my_building_cs2.py --full --json        # 검사+사진+타일+LOD, 결과 JSON 저장
```
- 하는 일: 생성기 실행 → `check.py` → `render.py` → (`photo_refs.json` 있으면) `photo_check.py`.
- `--full` 은 `tile_compare.py` 와 `tools/qa/lod_check.py` 까지 실행하고 `GATE` 줄을 하나 더 낸다
  (`lod_check` 는 FBX/.blend 와 Blender 가 필요, 없으면 `lod=SKIP`).
- `--json` 은 모든 결과를 `output/<에셋>/_check/gate.json` 에 쓴다(경로를 주면 그곳).
- 마지막 줄: `RESULT PASS|FAIL errors=N warnings=M [photo_mismatch=K] asset=<이름> preview=<경로>`.
  `GATE` 는 검사 오류·사진 불일치·LOD 를 합친 요약. 종료 코드는 예전과 같이 검사 오류만 본다
  (실행 실패 2 / 검사 오류 1 / 통과 0).
- 그림: `previews/<에셋>.png`(최신), `previews/progress/latest.png`(항상 최신 한 장), `previews/progress/<에셋>/NNN_시각_label.png`(단계별 기록).
  `--label` 은 영문·숫자·`-`/`_` 만 쓴다. 사용자는 `latest.png` 를 열어 두고 진행을 본다.
- 사진 비교 줄: `PHOTO_MISMATCH ...` 가 나오면 그 층 수·층고·창 간격을 고친다. 시트는 `previews/photo_check/*.png`.

### check.py — 규격 검사
```bash
python tools/check.py output/<에셋>            # 에셋 하나
python tools/check.py output                    # 전부
python tools/check.py output/<에셋> --list 10 --json report.json --fast --ray 1.5
```
오류(✗)는 반드시 0, 경고(!)는 이유를 보고에 적는다. 주요 항목: 이름 규칙, 바닥 z<0, 피벗, LOD1<메인 50%, LOD2≤500 tris,
같은 평면 겹침, 창 UV(범위·겹침·비율), 창 앞 가림, 텍스처 5종 크기, 텍셀 밀도, 메인 9.5만 tris 초과.
`--list N` 으로 문제 위치(생성기 좌표)를 N개까지 본다. 좌표는 `manifest.json` 의 `pivot_shift` 로 생성기 좌표에 맞춰져 있다.
각 에셋 뒤에 기계 판독용 한 줄 `[CS2_AGENT_SUMMARY] {...}` 도 찍는다 - 4번 절 참고.

### render.py — Blender 없이 미리보기
```bash
python tools/render.py output/<에셋> -o previews/a.png
python tools/render.py output/<에셋> -o previews/a.png --views front,iso,top,lod1,lod2
python tools/render.py output/<에셋> -o previews/z.png --views front --zoom 3,0.5,0.1      # 3배 확대, 가로 50%·높이 10% 중심
python tools/render.py output/<에셋> -o previews/b.png --views yaw30:pitch5 --box=-10,10,-5,3,0,8   # 일부만
python tools/render.py output/<에셋> -o previews/c.png --views front --photo refs/a.jpg   # 사진과 나란히
python tools/render.py output/<에셋> -o previews/n.png --views front --mode normal        # color|normal|ctrl|emissive
```
- 보기 이름: `front back left right iso iso2 iso3 iso4 top lod1 lod2 atlas` 또는 `yaw<도>[:pitch<도>]` (yaw 0 = 정면, 90 = 오른쪽, 180 = 후면).
- `--box=` 처럼 `=` 로 붙인다(음수 때문). `--night` 는 발광만, `atlas` 는 칸 이름을 표시.
- 눈으로 확인할 때: 만든 그림을 Read 로 연다. 작은 부분은 `--zoom`/`--box` 로 확대한다.

### tile_compare.py — 타일별 디테일 비교 ("너무 단순함" 찾기)
```bash
python tools/cycle.py my_building_cs2.py --tiles --label detail      # cycle 안에서 (권장)
python tools/tile_compare.py output/<에셋>                            # 단독 실행 (photo_refs.json 필요)
python tools/tile_compare.py output/<에셋> --tile-m 6x5 --top 10      # 더 작은 타일, 나쁜 타일 10개
```
- 벽마다 사진을 정면도로 펴고 모델을 같은 크기로 그려 타일(기본 10x9 m, 옥상 15x15 m)로 나눈다. 타일마다 **recall**(사진의 선 중 모델에도 있는 비율 → 낮으면 디테일 부족)과 **precision**(모델의 선 중 사진에도 있는 비율 → 낮으면 엉뚱한 위치)을 잰다.
- 출력: `previews/tiles/<면>_map.png`(붉을수록 부족, 타일 번호 `r행c열`)와 나쁜 타일의 `previews/tiles/<면>/rXXcYY.png`(사진 | 모델 | 겹침: 파랑 = 사진의 선, 빨강 = 모델의 선).
- 줄: `TILE front r2c3 x[20,30]m z[9,18]m recall 38% precision 61%  SIMPLIFIED`, `DETAIL front recall 64% ...`. recall < 50% 면 SIMPLIFIED.
- **색 비교**: 타일마다 사진과 모델의 중앙값 색을 전체 노출 보정 후 비교한다. `COLOR front r2c3 ... photo #c9bfae model #e0e0e0 dE 21  COLOR_OFF`(dE > 14). `ZONES ... rows z`(높이별 띠)와 `cols x`(폭별 띠)는 사진·모델 둘 다 나와서 도색 구간이 빠졌는지 바로 보인다.
- **모델링 전 사진만**: `python tools/tile_compare.py --photo-zones front:60x45` → 사진 벽의 띠와 색.
- 숫자는 참고용이다(나무·그림자·원근이 점수를 낮춘다). 나쁜 타일을 Read 로 열어 사진에 있는데 모델에 없는 요소를 찾아 만든다. 종료 코드는 항상 0.

### photo_check.py — 사진과 숫자 비교
`photo_refs.json` 이 필요하다 (`photo_refs.example.json` 참고, 또는 `/photo-refs`).
```bash
python tools/photo_check.py output/<에셋>
python tools/photo_check.py output/<에셋> --refs other.json
```
- 위성 사진: 가로/세로 비율(축척 있으면 실제 m), 외곽선 일치.
- 로드뷰 벽: 사진 벽을 정면도로 펴서 **층 간격**(층수)과 **창 간격**을 모델과 같은 방법으로 재서 비교. 허용 오차 비율 8%, 층 10%.
- 줄: `MATCH` / `MISMATCH` / `INFO`. 시트(`photo | model | overlay`)는 `previews/photo_check/`.
  펴진 사진이 벽에 딱 맞는지는 시트를 Read 로 열어 확인 — 안 맞으면 모서리 좌표부터 고친다.

### sat_grid.py — 사진 좌표 읽기
```bash
python tools/sat_grid.py grid refs/roof.jpg -o previews/g.png --step 50
python tools/sat_grid.py grid refs/roof.jpg -o previews/z.png --crop 400,300,800,600 --zoom 3 --step 10
python tools/sat_grid.py scale --p 102,330 --q 912,318 --meters 74        # 두 점 = 실제 74 m → m/px
python tools/sat_grid.py frame --corners 120,90,880,96,872,770,114,764 --size 74x89 --pts "300,200;450,610" --show previews/frame.png
```
격자 그림을 Read 로 보고 픽셀 좌표를 읽는다(눈금은 원본 픽셀). `frame` 은 건물 네 모서리(정면 왼쪽→정면 오른쪽→후면 오른쪽→후면 왼쪽)로
사진 픽셀을 건물 중심 기준 미터(정면 = -Y)로 바꿔 준다.

### extract_texture.py — 사진에서 재질 뽑기
```bash
python tools/extract_texture.py refs/a.jpg --pts 812,402,1290,380,1302,905,806,930 --size 3.0x2.9 -o textures_src/stone --show
```
- `--pts` 왼쪽 위·오른쪽 위·오른쪽 아래·왼쪽 아래 픽셀, `--size` 그 사각형의 실제 가로x세로 m.
- 옵션: `--clean x0,y0,x1,y1[;...]` 간판·사람·전선 지우기, `--flatten 0.8` 조명 평탄화, `--tile 0.15` 이음매 없는 타일(불규칙 면에만),
  `--normal 3.0` 노멀 세기, `--px`, `--max-ppm 256`, `--sharpen`.
- 고해상도·도색: `--target-ppm 256` 은 사진 해상도보다 높게 뽑는다(색은 사진 그대로, 미세한 결만 합성 → `synthesized`). `--paint` 는 도색 벽면용(색 띠 경계 유지 + 잡티 제거 + 결). 출력과 json 에 주요 색 4개(hex, 비율) `palette` 가 들어간다.
- 출력: `_albedo.png` `_normal.png` `_gloss.png` `.json` (+ `--show` 시 `_check.png`). 생성기에서
  `atlas.add("stone", px=768, tile=(3.0, 2.9), image="textures_src/stone_albedo.png", normal_image=..., gloss_image=...)`.
- 간판·로고·글자·사람·차량은 지우거나 피한다(상표 금지).

### glb_measure.py — 스캔(.glb)에서 치수·형태 참고
```bash
python tools/glb_measure.py scan.glb --list                    # 메시 목록
python tools/glb_measure.py scan.glb --mesh Building           # 이름 일부 (쉼표로 여러 개) 또는 --mesh-index 3,4
python tools/glb_measure.py scan.glb --box=-40,40,-30,30       # 주변 건물·지형 잘라내기 (미터)
python tools/glb_measure.py scan.glb --mesh Building --scale 0.01   # cm 단위일 때
```
- 출력: 가로·세로(기울어도 OK), 메인 지붕 높이, 옥탑 높이, 단차 높이, 층 간격·층수, 창 간격·개수, `TASK.md lines:` 한 줄.
- 그림·JSON: `previews/glb/` (`top.png` 위에서 본 모양, `elev_a..d.png` 네 방향 입면 점 밀도, `glb_measure.json`). 이 그림을 Read 로 열어 덩어리 모양(단차, 코어 위치, 옥탑, 날개 방향)을 파악한다.
- `WARNING: numbers look wrong` 이 나오면 지형·주변 건물이 섞인 것 → `--list` 후 `--mesh`/`--box`.
- Draco 압축 파일은 못 읽는다 → Blender 로 불러와 압축 없이 다시 내보낸다. 층·창 간격이 `weak` 면 입면 그림을 눈으로 확인.
- **치수·형태 참고용만.** 스캔의 형상·텍스처를 에셋에 넣거나 `output/` 으로 복사하지 않는다(직접 모델링).

### K.curtainwall — 커튼월(룩) 면 만들기 (cs2kit)
`K.curtainwall(main, axis, c, s, a0, a1, z0, z1, fh, wins, lod1=, lod2=, module_w=1.5, spandrel_h=0.9, cell=)` 한 번 호출 = 벽 한 면.
세로 멀리언(길게 한 개) + 층마다 가로 트랜섬 + 스팬드럴 칠 + 시야 유리 창(`WindowSet`, 밤 조명 대응). 시험 예제: `example_curtainwall_cs2.py` (14층, 모듈 1.5 m → 본체 약 1.9만 tris, LOD2 38 tris, 검사 통과).
옵션: `modules=[폭..]` 직접 지정, `head_h` 위쪽 띠, `show_mullion/show_transom`(리본형·세로선형), `ends`, `unit_modules`(세대 묶음), `cell(i, f)` = `"solid"|"louver"|"open"`. 모듈 폭이 0.9~3.0 m 밖이면 WARN.
사진에서 모듈·스팬드럴 수치 얻기: `python tools/facade_paint.py windows ...` 의 `MODULE pitch` 줄.

### facade_paint.py — 범용: 사진 한 벽에서 층·창·도색 읽기
`photo_refs.json` 의 벽 항목(`corners`, `size_m`, 선택 `name`/`x_m`/`z_m`)만 있으면 어떤 건물이든 동작한다(생성기 불필요).
- 단계: `floors`(층 줄·번호) → `windows`(창 목록·특징 층) → `paint`(팔레트·큰 사각형·REPEAT/RULE·FIT dE). `all` 은 전부.
- 주요 옵션: `--name`, `--wall-size WxH`, `--fh`(층고 힌트), `--feature-floor N`(번호 기준), `--first-floor N`, `--window-mode auto|dark|color:#hex`, `--cell`, `--ppm`.
- 결과: `previews/facade/<name>_floors_N.png`, `<name>_paint_N.png`(사진 | 사각형 | 차이), `<name>.json`.
- 한계: 사진 속 원근·그림자·나무가 심하면 틀릴 수 있다. 번호 그림과 도색 그림을 반드시 눈으로 확인하고, 합성 사진으로만 시험했다.

### tools/samhan_facade/ — 상세 사진에서 층 번호·도색·창 읽기 (삼한골든뷰 전용)
정면에 가까운 상세 사진이 여러 장 있는 고층 건물에서 **층 번호를 정확히 세고**(대피층 등 특징 층부터), 벽마다 **도색 구간(층 범위 x 가로 범위)** 과 **창 위치·크기**를 읽어 생성기 표(`WALLS`/`WIN`)로 옮기는 보조 도구 묶음이다. 사용법은 `tools/samhan_facade/README.md`.
- 프로젝트 루트에서 실행(`python tools/samhan_facade/<도구>.py`), 결과 그림은 `previews/`. 필요: numpy, Pillow.
- **특정 생성기 구조 전제**(`HALF`, `full_poly()`, `edges_of()` 등)와 이전 작업의 환경 변수 기본값(`FACADE_GLB`, `FACADE_MESHES`)이 들어 있다. 새 건물에 쓸 때는 README 의 "생성기 조건"을 확인하고 `FACADE_*` 를 지정한다.
- 도구: `plan_index`(평면 벽 번호) · `facade_read`(확대 사진+층별 표) · `refuge_scan`(대피층부터 층 세기, 핵심) · `band_scan` · `window_template`(한 층 창 모양) · `refuge_crop` · `montage` · `window_count` · `glb_slices`/`glb_mirror_test`(스캔 평면 비교).

### compare.py — 고친 곳 외에 안 바뀌었는지
```bash
python tools/compare.py snap output/<에셋>                                  # 고치기 전 (backup/<에셋>_<시각>/ 에 복사)
# ... 생성기 수정 + cycle.py ...
python tools/compare.py diff backup/<에셋>_<시각> output/<에셋> --box=-11,11,-8,0,0,6
```
메시별 tris 변화, 추가·삭제된 면의 개수·범위, 텍스처에서 바뀐 픽셀 영역을 보여 준다. `--box` 밖에서 바뀐 면이 있으면 오류(종료 코드 1).
창 UV 는 창 하나만 늘어도 전부 재배정되므로 창 면은 위치만 비교한다.

### run_blender.py — Blender
```bash
python tools/run_blender.py --find                          # 찾아서 tools/blender_path.txt 에 저장
python tools/run_blender.py --set "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
python tools/run_blender.py my_building_cs2.py -- --out output
python tools/run_blender.py --fbx2obj output/<에셋>        # FBX 만 있을 때 검사용 OBJ 만들기
```
순서: 환경변수 `BLENDER` → `blender_path.txt` → PATH → Windows 기본 설치 위치 등. Blender 가 없으면 일반 python 으로 실행되어
OBJ 만 나온다(검사·미리보기는 가능, **FBX 는 안 나옴** → 보고에 "FBX 없음" 적기).

## 4. 프리셋/소켓 API 전용 모드 (`cs2kit.py` 의 `preset_*`/`attach_*`, 2026-11 설계안 구현, v1)

이 절은 **새 건물**에서 아래 신규 API를 쓰기로 한 경우에만 적용된다. 기존 생성기(`axbox`/`paint`/
`MeshBuilder.box` 직접 호출)는 그대로 둬도 된다 — 이 절이 그것들을 금지하는 것은 "이 모드를 쓰는
생성기 안에서" 뿐이다. `docs/PROPOSAL_pipeline_v2.md` 가 전체 설계, 여기는 실제 구현 기준 규칙.

### 4.1 금지 / 필수
- 건물 **매스**는 반드시 `preset_plate_apartment` / `preset_tower_l_core` (+ 필요하면
  `preset_piloti_base`) 로 만든다. 프리셋이 못 만드는 특수 지오메트리만 예외로 손으로 만들되, 좌표는
  `BuildingMeta.WALLS`/`ROOF_PERIMETER`/`FLOOR_RINGS` 에서 읽어 오고 새 월드 좌표를 하드코딩하지 않는다.
- 장식(파라펫, 코니스, 캐노피)은 `attach_roof_crown` / `attach_cornice_band` / `attach_entrance_canopy`
  로만 붙인다(월드 좌표 직접 입력 금지 - 소켓/링/벽 레지스트리만 읽는다).
- 도색은 `tools/band_scan.py` 의 `paint_grid.json` 을 `K.apply_facade_paint_grid()` 로 입힌다.
  창/층 인식은 `tools/facade_read.py`(내부적으로 `facade_paint.py` 그대로 재사용) 로 한다.
- 창 소켓은 아직 없다 — `WindowSet.add_face` 를 `meta.WALLS[...]` 의 axis/c/s/a0/a1/row_z 로
  생성기가 직접 호출한다.

### 4.2 호출 순서
```python
meta = preset_plate_apartment(A, ...)            # 또는 preset_tower_l_core(...)
preset_piloti_base(meta, ...)                    # 저층부가 필로티면
attach_roof_crown(meta, ...)
attach_cornice_band(meta, target_floors=[...])
attach_entrance_canopy(meta, bay_index=0)
# 창은 meta.WALLS 좌표로 생성기가 WindowSet.add_face 직접 호출
apply_facade_paint_grid(meta.mb, A, meta.WALLS["front"], paint_grid, palette)
K.export_asset(NAME, LEVEL, dict(main=meta.mb, lod1=l1, lod2=l2, windows=W), A, ...)
```
LOD1/LOD2 는 같은 프리셋/attach 호출을 `quality_stage` 를 바꿔 다시 불러서 만든다(LOD마다
`BuildingMeta`가 새로 생기므로, 그 `mb` 를 `export_asset` 에 `lod1=`/`lod2=` 로 따로 넘긴다).

### 4.3 `[CS2_AGENT_SUMMARY]` action_tags 대응표
`python tools/check.py output/<asset>` 가 에셋마다 마지막에 한 줄 찍는다:
`[CS2_AGENT_SUMMARY] {"status":..,"verts":{"LOD0":..,"LOD1":..,"LOD2":..},"action_tags":[...],"exact_fix_instruction":"..."}`

| action_tag | 뜻 | 고칠 파라미터 |
|---|---|---|
| `APPLY_STAGE_1` | main tris 가 50000 의 1~15% 더 큼 | 모든 `preset_*`/`attach_*` 호출의 `quality_stage` 를 현재값+1 |
| `APPLY_STAGE_2` | 15% 이상 더 큼 | `quality_stage=2`, bay 수·반복 디테일 밀도도 줄이기 |
| `APPLY_STAGE_3_LOD_CULL` | LOD1(메인의 50%↑) 또는 LOD2(500 tris↑) 한도 초과 | 그 LOD 빌드에서 `quality_stage=3` (attach_* 가 자동으로 아무것도 안 만듦) |
| `CLAMP_UV` | `ATLAS_UV`/`WIN_UV` 에러 | custom quad UV를 `A.uv_full`/`A.uv_tile` 로 교체 |
| `MERGE_VERTICES` | 축퇴 면 경고 | 같은 `preset_*`/`attach_*` 호출이 루프 들여쓰기 등으로 중복되는지 확인 |

`exact_fix_instruction` 은 `tools/check.py` 의 `_FIX_TEXT` 와 같은 내용이다 - 코드가 먼저 바뀌면
이 표도 같이 고친다.

### 4.4 Few-shot 예제
```python
import cs2kit as K

A = K.Atlas()
for n, c in [("wall", (210, 208, 205)), ("core", (190, 190, 190)), ("slab", (160, 160, 160)),
             ("parapet", (170, 170, 170)), ("coping", (180, 180, 180)), ("light_strip", (255, 250, 210)),
             ("cornice", (175, 175, 175)), ("canopy", (170, 170, 170))]:
    A.add(n, color=c, emissive=(255, 250, 210) if n == "light_strip" else None)

# 판상형
meta = K.preset_plate_apartment(A, W=42.0, D=16.0, floors=15, floor_h=2.9, ground_h=4.5, bays=4)
K.attach_roof_crown(meta, style="parapet_light", height=1.2)
K.attach_cornice_band(meta, target_floors=[5, 10])
K.attach_entrance_canopy(meta, bay_index=0)
K.export_asset("ResidentialHighPlateXXXX01", 1, dict(main=meta.mb), A, K.out_dir_from_argv("output"))

# 타워형(L자 코어)
meta2 = K.preset_tower_l_core(A, wing_a=(30.0, 14.0), wing_b=(20.0, 12.0), floors=36, floor_h=2.82,
                               corner_curtainwall=True)
K.attach_roof_crown(meta2, style="mechanical_screen", height=2.0)
K.attach_cornice_band(meta2, target_floors=[10, 20, 30])
# meta2.CORNER_WALLS 의 두 벽은 생성기가 K.curtainwall + K.corner_post 로 직접 닫는다(프리셋이 못 만듦)
```

### 4.5 v1 한계 (아직 안 된 것)
- `preset_piloti_base` 의 기둥 깊이는 단순화(벽 바로 바깥 0~0.5 m) - 건물마다 사진으로 확인해야 한다.
- `tools/facade_read.py`/`tools/band_scan.py` 는 실제 사진으로 미검증(합성 이미지로만 실행 확인).
  색 클러스터링 결과를 생성기 표로 옮기기 전에 `previews/paint_grid/*.json` 을 사진과 눈으로 대조한다.
- `apply_facade_paint_grid` 는 색만 다른 "페인트 오버레이"만 만든다. 실제 요철이 필요한 경계는
  여전히 `K.axbox` 로 따로 만든다.

## 5. 생성기를 쓸 때 (cs2kit, 일반)

- 생성기 파일 이름: `<에셋이름>_cs2.py`, 에셋 이름에 밑줄 금지, 폴더/파일은 영어.
- `import cs2kit as K` 로 `MeshBuilder`(박스·면·창), `Atlas`(텍스처 칸), `WindowSet`(창), `export_asset`(FBX·OBJ·PNG·manifest)를 쓴다.
  LOD2 용 빌더는 `K.MeshBuilder(A, split_tiles=False)`.
- `cs2kit.py` 는 읽어도 되지만 **고치지 않는다**. 모자란 기능은 생성기 안에 헬퍼로 만든다(4번 절의
  `preset_*`/`attach_*` 는 이미 `cs2kit.py` 에 들어 있는 공식 API라 이 규칙의 예외가 아니라 그 자체다).
- 규격(1단위=1m, 피벗 바닥 중앙, 정면=-Y, 메인은 재질 1개, `_Win`/`_Gls` 는 재질 없음, 창 UV 는 5x5 격자 등)은 `AGENTS.md` 의 CS2 facts 를 따른다.

## 6. 자주 나는 문제

| 증상 | 원인 / 해결 |
|---|---|
| `NO FBX - Blender not found` | Blender 경로 못 찾음 → `python tools/run_blender.py --set "<경로>"` |
| `--box -11,...` 가 옵션 오류 | 음수 때문 → `--box=-11,11,...` 처럼 `=` 로 붙인다 |
| LOD2 가 500 tris 초과 | LOD2 빌더를 `split_tiles=False` 로 (또는 4번 절: `quality_stage=3`) |
| 창 앞 가림 오류 | 창 앞에 난간·루버·발코니가 막음 → `--list` 의 좌표 확인 후 간격 띄우기 |
| PHOTO_MISMATCH floor pitch | 층수·층고가 사진과 다름 → 메시지가 "더 많은/적은 층"이라고 알려 준다 |
| 사진 시트에서 사진이 비뚤어짐 | `photo_refs.json` 모서리 좌표가 틀림 → `sat_grid.py grid` 로 다시 읽는다 |
| 출력이 `\uXXXX` 로 보임 | 한글을 일부러 ASCII 로 바꿔 출력하는 것 (콘솔 깨짐 방지). 정상 |
| `BrokenPipeError` | `| head` 로 잘랐을 때만 나는 무해한 메시지 |
