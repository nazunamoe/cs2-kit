# CS2 건물 에셋 키트 (cs2kit + tools)

Cities: Skylines II 건물 생성기를 만들 때 **매번 새로 짜던 공통 코드와 검증 도구**를 미리 만들어 둔 것.
작업 폴더에 그대로 풀어 넣고, 생성기는 `cs2kit` 을 불러 **형상만** 짜면 된다.

```
키트 루트/               ← 모든 작업을 여기서 한다 (건물은 projects/ 안에, 학습은 memory/ 에 쌓임)
  projects/<이름>/          ← 건물 하나 = 폴더 하나: TASK.md, photos/, <이름>_cs2.py, photo_refs.json, output/, previews/, 조사 메모
  memory/                   ← LESSONS.md(교훈) · LOG.md(프로젝트 기록) · VALUES.md(측정값). 키트를 업데이트해도 덮어쓰지 않음
  templates/                ← 빈 TASK.md, photo_refs 예시, memory 초기 파일 (project.py 가 복사해 씀)
  AGENTS.md                 ← 로컬 모델(Codex)용 작업 규칙 — Codex 가 자동으로 읽음
  CLAUDE.md                 ← Claude Code 용 규칙 (AGENTS.md 를 불러오고 차이만 덮어씀)
  .claude/settings.json     ← Claude Code: tools/ 실행을 매번 묻지 않게 허용
  .claude/skills/           ← Claude Code 명령: /build /resume /photo-refs /fix
  cs2kit.py                 ← 공통 라이브러리 (생성기가 import)
  example_building_cs2.py   ← 사용 예제 = 새 생성기 템플릿
  example_curtainwall_cs2.py ← 커튼월(룩) 아파트 예제 (K.curtainwall: 멀리언·트랜섬·스팬드럴·유리창)
  tools/
    cycle.py                ← 생성 → 검사 → 미리보기 한 번에 (짧은 출력). 진행 사진이 previews/progress/ 에 쌓임
    put.py / edit.py        ← 파일 쓰기·부분 수정 (PowerShell 따옴표·줄바꿈 문제 없이, 문법 오류면 반영 안 함)
    show.py                 ← 줄 번호 붙여 파일 보기 (깨지지 않는 ASCII 출력)
    photo_check.py          ← 로드뷰·위성 사진과 모델 비교 (크기·비율·층 간격·창 간격 → MATCH / MISMATCH)
    check.py                ← 검증 (오류면 종료 코드 1)
    render.py               ← 미리보기 PNG (Blender 불필요)
    extract_texture.py      ← 사진 → 반듯한 재질 텍스처 + 노멀·광택
    sat_grid.py             ← 사진 격자·축척·픽셀→미터
  facade_tools/             ← (선택) 상세 사진에서 층 번호·도색·창 읽기 보조 도구 묶음 — facade_tools/README.md
    compare.py              ← 수정 전 스냅샷 / 전후 비교
    run_blender.py          ← Blender 찾기 + 실행, FBX→OBJ
    objio.py                ← (내부용) OBJ·PNG 읽기
  (textures_src/ previews/ output/ backup/ 은 각 projects/<이름>/ 안에 생김)
    project.py              ← 프로젝트 관리: init · new <이름> · use · list · where · migrate
    proj.py                 ← (내부용) 모든 도구가 활성 프로젝트 폴더에서 일하게 함
```
## 프로젝트 구조 사용법 (요약)
```
python tools/project.py init                       # 처음 한 번: memory/ 만들기 (이미 있으면 건드리지 않음)
python tools/project.py new apt-01 [--template cw] # projects/apt-01/ 만들고 활성 프로젝트로 지정 (cw = 커튼월 예제)
python tools/project.py use apt-01 | list | where  # 활성 프로젝트 바꾸기 / 목록 / 확인
python tools/project.py migrate old --apply        # 예전 평면 구조(루트의 TASK.md·output/ 등)를 projects/old/ 로 옮기기 (--facade-tools 포함 가능)
```
- 모든 도구는 활성 프로젝트 폴더에서 일한다. 상대 경로(`output/<에셋>`, `previews/..`, `photo_refs.json`)는 그 폴더 기준이다. 한 번만 다른 프로젝트로 돌리려면 `--project <이름>`.
- 키트 업데이트 = `tools/`, `cs2kit.py`, `*.md`, `templates/`, `.claude/` 만 덮어쓰기. `projects/` 와 `memory/` 는 건드리지 않는다.

필요: Python 3.9+, `numpy`, `Pillow` (tools 만 Pillow 사용, `cs2kit.py` 는 numpy 만 → Blender 안에서도 동작)
`pip install numpy pillow`

---

## 1. 빠른 시작
```bash
python tools/run_blender.py --find                                  # Blender 찾기 (한 번)
python tools/run_blender.py example_building_cs2.py -- --out output   # 생성 (Blender 없으면 OBJ 만)
python tools/cycle.py example_building_cs2.py                       # 생성 + 검증 + 미리보기 한 번에
python tools/check.py output                                        # 검증만
python tools/render.py output/<에셋> -o previews/a.png                # 미리보기만
```
`output/<에셋>/` 에 FBX 8종(메인·_Win·_Gls·_LOD1·_LOD1_Win·_LOD1_Gls·_LOD2·_LOD2_Win), 텍스처 5종 x (메인 + LOD1 + LOD2),
`manifest.json`(크기·로트·tris·아틀라스 배치), `_check/*.obj`(검사용 — 게임에 넣지 않음)이 생긴다.

## 2. cs2kit — 생성기 쓰는 법
좌표: 1 유닛 = 1 m, 지면 z = 0, 정면(도로) = **-Y**. 면 이름 front(-Y) back(+Y) left(-X) right(+X).

```python
import cs2kit as K
A = K.Atlas(size=4096, pad=16)                       # 가변 크기 칸 아틀라스
A.add("stone", color=(122,116,110), ctrl=(0,0,255), px=1024, tile=(3.0, 2.9), painter=my_painter)
A.add("frame", color=(70,74,80), metal=0.8, gloss=0.6, px=32)
A.add("led",   color=(250,246,236), emissive=(255,236,200), px=32)
A.add("stone2", px=768, tile=(3.0,2.9), image="textures_src/stone_albedo.png",
      normal_image="textures_src/stone_normal.png", gloss_image="textures_src/stone_gloss.png")

mb = K.MeshBuilder(A)
mb.box(x0,x1,y0,y1,z0,z1, "stone", skip=("bottom",))          # 면별 dict(default=, top=, front=...) 도 가능
K.axbox(mb, "y", 0, -1, a0, a1, 0, 0.3, z0, z1, "frame")       # 벽에 붙은 박스: 벽 쪽 면 자동 생략
K.paint(mb, "y", 0, -1, a0, a1, z0, z1, "accent", layer=1)     # 벽 앞 1 cm 칠 면 (칠 위 칠은 layer=2)
wins = K.WindowSet(); wins.add_face("y", 0, -1, a0, a1, z0, z1, floor=f, unit=u)
K.export_asset("ResidentialHighKMyApt01", 3, dict(main=mb, lod1=l1, lod2=l2, gls=g, lod1_gls=g1, windows=wins), A, out)
```
| 기능 | 내용 |
|---|---|
| `tile=(w,h)` | 칸 = 실제 크기 한 장. 면을 그 크기로 **자동 분할**해 붙임 → 판석·패널 줄눈이 실제 크기로 맞음 |
| `px` | 칸 크기. 텍셀 밀도 = px / tile 크기 (예 1024px / 3 m = 341 px/m) |
| `variants=n` | 같은 재질 n장 가로로 → 타일마다 돌려 써서 반복 티 줄임 |
| `painter(c)` | 칸에 직접 그림: `c.joints()` 줄눈+노멀 홈, `c.grain()` 결, `c.stains()` 얼룩·빗물, `c.noise()`, 배열 `c.rgb/alpha/height/gloss/emis`, 좌표 `c.u c.v`, `c.meters()` |
| `image=` | 사진 조각(extract_texture.py 출력)을 칸에 넣음 |
| 노멀맵 | `c.height` 를 그리면 자동으로 OpenGL 노멀 생성 (5 cm 미만 디테일) |
| 블리드 | 칸 바깥 여백을 가장자리 색으로 채움 (밉맵 번짐 방지) |
| LOD2 텍스처 | 메인 아틀라스를 줄여서 자동 생성 (`lod2_tex=1024`) |
| 창 UV | `WindowSet.build()` 가 25칸(5x5)에 층·세대별로 겹침 없이, 비율 유지해 배정 |
| 내보내기 | 피벗 바닥 중앙, 로트 자동(8 m 칸), 이름 `<Name>_L<lvl>_<w>x<d>`, FBX 는 `FBX_SCALE_NONE` (게임 1/100 문제 해결값) |
| 경고 | 이름 밑줄, 로트 > 6x6(시그니처), LOD1 ≥ 50%, LOD2 > 500, 메인 > 9.5만 tris |

`Atlas.uv(name)` 단색 / `uv_full` 칸 전체(알파 그림) / `uv_sub` 칸 일부 / `uv_tile` 실제 크기 — 직접 `mb.quad(pts, uv4, tag)` 할 때 사용.
`K.up_quad(q)` 바닥 깔개 면을 위로, `K.floor_quad(...)` 수평면, `K.face_pts(...)` 벽면 사각형.

## 3. tools
### check.py — 검증 (생성기와 무관, OBJ+PNG 만 봄)
```bash
python tools/check.py output/<에셋>      # 또는 output (전부)
python tools/check.py output --list 10 --json previews/check.json
```
ERROR(오류): 이름 규칙 · 필수 파일 · z<0 · 피벗 · 지면 아래 보는 면 · 크기 단위(1/100) · LOD1 ≥ 50% · LOD2 > 500 ·
같은 평면 겹침(메인·LOD1·LOD2·Gls·Win, 회전 면 포함 실제 다각형 교차) · 창 UV(0~1, 겹침, 비율) ·
창 앞 1.5 m 가림(**BaseColor 알파로 뚫린 곳은 통과**) · 텍스처(정사각·2의 거듭제곱·크기 일치) · 아틀라스 칸 넘는 UV
WARN(경고): 창 뒤 벽 없음 · 퇴화/비평면 면 · 텍셀 밀도 낮음 · 로트 > 6x6 · 9.5만 tris 초과
문제마다 좌표 예시가 나온다 (manifest 가 있으면 **생성기 좌표** — 피벗 이동 전 값이라 코드 숫자와 바로 비교 가능). 종료 코드 0 = 오류 없음.

### render.py — 미리보기
```bash
python tools/render.py output/<에셋> -o previews/a.png --views front,iso2,back,iso,top
python tools/render.py output/<에셋> -o previews/b.png --views front --zoom 4,0.5,0.05     # 4배, 가운데 아래
python tools/render.py output/<에셋> -o previews/c.png --views yaw20:pitch5 --box=-8,0,-3,3,0,6   # 일부만
python tools/render.py output/<에셋> -o previews/d.png --views front --photo refs/front.jpg     # 사진과 나란히
python tools/render.py output/<에셋> -o previews/e.png --views lod1,lod2,atlas
python tools/render.py output/<에셋> -o previews/f.png --views iso --night                    # 경관조명
```
`--mode normal|ctrl|emissive` 로 다른 맵 확인. 알파 컷·유리 반투명·노멀 음영 반영. 6만 tris 기준 장당 수 초.

### extract_texture.py — 사진 → 텍스처
```bash
python tools/sat_grid.py grid refs/a.jpg -o previews/a_grid.png --step 50         # 네 점 좌표 읽기
python tools/extract_texture.py refs/a.jpg --pts 812,402,1290,380,1302,905,806,930 --size 3.0x2.9 \
       -o textures_src/stone --grid 3x5 --show --clean 100,50,180,120
```
원근 보정(호모그래피) → 업스케일 없음(사진 해상도·256 px/m 상한) → 지울 곳 채우기 → 조명 평탄화 → 선명화 →
`_albedo/_normal/_gloss.png` + `.json`(출처·네 점·px/m). `--tile 0.15` 는 콘크리트처럼 **불규칙한 면에만** (줄눈 있는 재질은 네 점을 줄눈 한 주기에 맞출 것).
`_check.png` 로 고른 영역과 2x2 반복을 확인. 간판·로고·글자·사람·차량은 피하거나 `--clean`.

### sat_grid.py — 사진 좌표
```bash
python tools/sat_grid.py grid refs/roof.jpg -o previews/g.png --crop 400,300,800,600 --zoom 3 --step 10
python tools/sat_grid.py scale --p 102,330 --q 912,318 --meters 74
python tools/sat_grid.py frame --corners 120,90,880,96,872,770,114,764 --size 74x89 --pts "300,200;450,610" \
       --image refs/roof.jpg --show previews/frame.png
```
`frame`: 건물 네 모서리(정면 왼쪽→정면 오른쪽→후면 오른쪽→후면 왼쪽)로 사진 픽셀을 **건물 중심 기준 미터**로 변환(정면 = -Y). 옥상 시설·주차선 위치 잡을 때.

### glb_measure.py — 스캔(.glb)에서 치수·형태 참고
```bash
python tools/glb_measure.py scan.glb --list                      # 메시 목록 (이름·크기·tris)
python tools/glb_measure.py scan.glb --mesh Building             # 이름에 포함된 것만 (또는 --mesh-index 3,4)
python tools/glb_measure.py scan.glb --box=-40,40,-30,30         # 주변 건물·지형 잘라내기 (미터, 위에서 본 x/y)
```
가로·세로(기울어진 스캔도 최소 회전 사각형으로)·옥상 높이·옥탑 높이·층 간격/층수·창 간격(bay)을 출력하고
`previews/glb/` 에 JSON 과 점 밀도 입면도(`top.png`, `elev_a..d.png`)를 남긴다. 출력의 `TASK.md lines:` 를 TASK.md 에 옮기면 된다.
단위가 이상하면 `--scale`(예: cm 단위면 0.01). Draco 압축 파일은 Blender 에서 다시 내보낸다. **치수·형태 참고용 — 스캔의 형상·텍스처를 에셋에 쓰지 않는다.**

### compare.py — 전후 비교
```bash
python tools/compare.py snap output/<에셋>                                       # 고치기 전에
python tools/compare.py diff backup/<에셋>_<시각> output/<에셋> --box=-8,0,-3,3,0,6   # 이 범위 밖이 바뀌었으면 오류
```
메시별 추가·삭제 면 수와 범위, 텍스처 바뀐 픽셀 범위. "입구만 고쳤는데 다른 데가 바뀌지 않았나" 확인용.

### run_blender.py — Blender 찾기·실행
찾는 순서: 환경변수 `BLENDER` → `tools/blender_path.txt` → PATH → (Windows) 레지스트리·Program Files·Steam → macOS/Linux 기본 위치.
찾으면 `tools/blender_path.txt` 에 저장. 못 찾으면 `--set "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"`.
Blender 가 없으면 생성기를 일반 python 으로 돌려 OBJ·텍스처까지는 만든다 (검사·미리보기 가능).
`--fbx2obj output/<에셋>` : cs2kit 을 안 쓰는 생성기가 FBX 만 만들었을 때 검사용 OBJ 변환.

## 4. 로컬 모델 (Codex + Ollama, 예: gemma4:31b)
**준비 (한 번)**
1. 컨텍스트 64K 이상: `ollama serve` 전에 환경변수 `OLLAMA_CONTEXT_LENGTH=65536` (Codex 기본 지시문만 8~12K 토큰을 씀)
2. **한글 깨짐 방지** — Windows 기본 PowerShell 5.1 은 UTF-8 을 CP949 로 읽고 내보내서 파일 내용·명령 출력이 깨진다.
   - PowerShell 7 설치 후 그 창에서 Codex 실행: `winget install Microsoft.PowerShell` → `pwsh`
   - 같은 창에서: `chcp 65001`, `[Console]::OutputEncoding = [Text.Encoding]::UTF8`, `$env:PYTHONUTF8 = "1"`
   - 그래도 깨지면: Windows 설정 → 시간 및 언어 → 언어 및 지역 → 관리 언어 설정 → 시스템 로캘 변경 →
     "Beta: 세계 언어 지원을 위해 Unicode UTF-8 사용" 켜고 재부팅
   - 키트 쪽 대비: AGENTS.md·예제 생성기·도구 출력은 모두 영어(ASCII)라서 셸이 깨져도 읽힌다. 한글은 TASK.md 에만 들어가므로 TASK.md 는 숫자·영어 위주로 쓸 것.
3. Blender 5.2 경로 등록: `python tools/run_blender.py --set "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"`
   확인: `python tools/cycle.py example_building_cs2.py` → `[1/3 build] ... (FBX written)` 와 `RESULT PASS` 가 나오면 준비 끝

4. **파일 쓰기 문제** — 최신 Codex 의 파일 편집 도구(apply_patch)는 로컬 모델이 잘 못 쓴다. 그러면 모델이 PowerShell 명령으로
   파일을 쓰다가 따옴표·줄바꿈이 깨져 `SyntaxError: unterminated string literal` 이 난다.
   → AGENTS.md 가 `tools/put.py`·`tools/edit.py` 만 쓰게 한다. 내용은 작은따옴표 here-string(`@' ... '@`)으로 넘겨서 아무것도 이스케이프되지 않는다.
   edit.py 는 결과가 문법 오류면 파일을 바꾸지 않는다. (PowerShell 7 에서 따옴표·$·백슬래시·백틱 섞인 코드로 시험함)
   그래도 계속 깨지면 Codex 를 WSL(Ubuntu) 안에서 돌리는 것이 가장 확실하다 (bash heredoc 사용).

**작업**
1. `TASK.md` 채우기 → 폴더에서 `ollama launch codex` (모델 gemma4:31b, 승인 없이 실행되는 자동 모드 권장)
2. 첫 메시지:
   ```
   Read AGENTS.md and TASK.md fully. Then follow the Build order in AGENTS.md from step 1.
   Edit files only with tools/edit.py and tools/put.py using @' ... '@ exactly as AGENTS.md shows.
   After every small edit run: python tools/cycle.py <Name>_cs2.py
   Do not ask questions. Continue until the last line is RESULT PASS, then report in Korean.
   ```
3. SyntaxError·따옴표 문제가 또 나면: `Stop writing files with PowerShell strings. Use only: @' (new line) SEARCH/REPLACE block (new line) '@ | python tools/edit.py <file>. Show the lines first with python tools/show.py.`
4. 멈추거나 말로만 할 때: `Continue. Do the next step and run python tools/cycle.py <Name>_cs2.py now. No explanation first.`
5. 엉뚱한 곳을 고칠 때: `The coordinates in the ERROR lines are your generator coordinates. Fix only the part at that x,y,z, then run cycle.py.`
6. 대화가 길어지면 새 세션: `Read AGENTS.md. Continue <Name>_cs2.py. First run python tools/cycle.py <Name>_cs2.py, then do the remaining Build order steps.`
7. 결과 수정: `<change>. Before: python tools/compare.py snap output/<asset>. After: cycle.py must PASS and compare.py diff must show changes only there. Report in Korean.`

## 4-0. Claude Code 로 쓰기
같은 키트를 Claude Code 에서도 쓸 수 있다. 폴더에서 `claude` 를 실행하면 `CLAUDE.md` 를 자동으로 읽는다.
- 규칙은 AGENTS.md 와 같고(CLAUDE.md 가 `@AGENTS.md` 로 불러옴), 다른 점만 CLAUDE.md 에 있다:
  - 파일은 Claude Code 편집 도구로 고친다 (put/edit/here-string 불필요)
  - 사진을 직접 보고 `photo_refs.json` 을 스스로 만든다
  - 사진 비교를 숫자 + 비교 그림으로 확인하고 고친다
  - 디테일 목표를 더 높게 (3만~6만 tris, 4096 아틀라스, 로드뷰 재질 추출)
- 명령 (`.claude/skills/`):
  - `/build` — TASK.md 의 건물을 처음부터 끝까지 (예: `/build 옥상 물탱크 디테일 강조`)
  - `/resume` — 끊긴 작업 이어서
  - `/photo-refs` — 사진 모서리 좌표 파일 만들기·확인
  - `/fix <고칠 내용>` — 스냅샷 → 수정 → 검사 → 다른 곳이 안 바뀌었는지 비교
- `.claude/settings.json` 이 `python tools/...`·생성기 실행을 허용해 둬서, 검사·미리보기 때마다 승인 창이 뜨지 않는다.
- 준비는 로컬 모델과 같다: Blender 경로 등록 → `python tools/cycle.py example_building_cs2.py` 로 확인 → TASK.md 채우기 → `/build`

## 4-1. 사진 비교 (안 맞으면 다시 만들기)
`photo_refs.json` 이 있으면 `cycle.py` 가 돌 때마다 모델을 사진과 비교한다.
- 위성 사진: 건물 네 모서리 → 가로/깊이 비율, (축척을 주면) 실제 가로·깊이 m 비교
- 로드뷰: 벽 한 면의 네 모서리 → 사진을 모델 정면도 크기로 펴서, 같은 방법으로 **층 간격**과 **창 간격**을 재서 비교
  (사진 층 간격이 더 촘촘하면 "층수가 모자람"으로 판정)
- 비교 그림: `previews/photo_check/` (펴진 사진 | 모델 | 빨간 선 = 모델 윤곽을 사진 위에)
- 오차 기준: 크기·비율 8 %, 층 간격 10 % (창 간격은 참고용)
- AGENTS.md 규칙: 덩어리 단계·창 단계·마지막에 PHOTO_MISMATCH 를 고치고 다시 돌림. 항목당 3번까지,
  나무·원근 때문에 안 맞는 건 YAML `photo_mismatch_notes` 에 이유를 적고 넘어감
- **모서리 좌표는 직접 적어 주는 게 가장 정확하다** (로컬 모델은 사진을 잘 못 볼 수 있음).
  `photo_refs.example.json` 을 `photo_refs.json` 으로 복사해서 채우기. 좌표는 그림판 아래쪽에 마우스 위치 픽셀이 나온다.
- 이 환경에서 합성 사진으로 시험: 맞는 모델은 전부 MATCH, 가로 27 m·12층으로 틀린 모델은 가로·비율·층 간격 MISMATCH.
  실제 사진(나무·그림자·원근)에서는 측정이 흔들릴 수 있어서, 패턴이 약하면 MISMATCH 대신 INFO 로 낮춘다.

## 5. 작업 순서 (권장)
1. `sat_grid.py` 로 사진 치수·위치 읽기 → 명세 YAML
2. 필요하면 `extract_texture.py` 로 재질 조각 → `textures_src/`
3. `example_building_cs2.py` 를 복사해 생성기 작성 → `run_blender.py` 로 실행
4. `check.py` 오류 0 될 때까지 수정 → `render.py` 로 사진과 비교
5. 큰 수정 전 `compare.py snap`, 수정 후 `compare.py diff --box=...`

## 6. 알려진 한계
- render.py 는 정사영·단순 조명. 게임 화면과 색·밝기가 다르다 (형태·겹침·알파 확인용).
- check.py 의 같은 평면 판정 허용치 1 mm·넓이 1e-3 m². 창 가림은 창 가운데와 두 모서리 3점만 본다.
- FBX 실제 출력은 Blender 안에서만 됨 (Blender 5.2 기준으로 작성, 4.x 도 동작하게 분기). FBX 의 게임 내 크기는 반드시 게임에서 확인.
- 이 키트를 만든 환경에는 Blender 가 없어, Blender 안 실행(FBX·.blend 저장, Blender 이미지 읽기)은 시험하지 못했다.
  FBX 내보내기 옵션 이름은 Blender 5.2.2 소스에서 그대로인 것을 확인했다. 처음 한 번은 `python tools/cycle.py example_building_cs2.py` 로 확인할 것.
- 도구 출력은 영어(ASCII)다. Windows 셸에서 한글이 깨져 로컬 모델이 엉뚱하게 움직이는 문제를 막기 위해서다.

## 7. 추가 도구 (이 배포본에 포함)

본 키트 외에 작업 중 만든 도구가 함께 들어 있다.

| 폴더 | 내용 | 필요 환경 |
|---|---|---|
| `tools_scan/` | glb/gltf 스캔 분석: 메시 목록, 높이별 단면(꼭짓점 좌표), **옥상 레벨·성분(데크/파라펫 띠/옥탑 상자)**, 높이장, 실루엣, 모델 OBJ 자동 정렬 비교 | Python + numpy, matplotlib, Pillow (Blender 불필요) |
| `tools_local/` | `lod_check.py`: 게임처럼 뒷면을 안 그릴 때 LOD별 구멍(투명) 비율 검사 | Blender |
| `facade_tools/` | 사진에서 층·도색·창을 읽는 보조 도구 (특정 생성기 구조 전용 — 폴더의 `README.md` 참고) | Python + numpy, Pillow |
| `capture/` | `naver_vr.py`: 네이버 부동산 VR 단지 뷰에서 동별 8방향 입면 캡처 | Chrome(원격 디버깅 포트) |

사용법은 각 폴더의 `README.md` 와 파일 머리 주석을 본다. `tools_scan` 은 `tools_scan/README.md` 에 예제가 자세히 있다.

**배포본에서 빠진 것**: `projects/`(건물 작업 폴더), `memory/`(개인 학습 기록 — 템플릿 `templates/memory/` 는 포함),
`previews/`, `output/`, `capture/out/`(캡처 이미지), `tools/blender_path.txt`(로컬 설치 경로), `__pycache__`.
