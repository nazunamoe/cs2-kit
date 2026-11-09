# tools/photo_facade — 사진으로 외벽 도색·창을 읽는 보조 도구

> 다른 건물에는 생성기 없이 쓰는 범용판 `tools/facade_paint.py` 를 먼저 쓰세요. 이 폴더는 삼한골든뷰 생성기 구조 전용입니다.

삼한골든뷰 작업(2026-10-24~25)에서 만든 도구 모음입니다. 사진에서 **층 번호를 정확히 세고**, 벽마다
**도색 구간(층 범위 × 가로 범위)** 과 **창 위치·크기**를 읽어 생성기 표(WALLS / WIN)로 옮길 때 씁니다.

- 키트(`tools/`, `cs2kit.py`)는 건드리지 않습니다. 이 폴더는 프로젝트 루트에 두고 **루트에서 실행**합니다.
- 필요한 것: Python 3, numpy, Pillow. (`glb_*` 도구는 추가 라이브러리 없이 .glb 를 직접 읽습니다.)
- 결과 그림은 모두 `previews/` 에 저장됩니다.

## 0. 설치 / 설정

```
프로젝트루트/
  tools/photo_facade/        <- 이 폴더 통째로 복사
  <Name>A_cs2.py       <- 생성기 (아래 "생성기 조건" 참고)
  atype-1.png ...      <- 사진
  tools/ previews/ ...
```

환경 변수(선택):

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `FACADE_ROOT` | 현재 폴더 | 프로젝트 루트 |
| `FACADE_GEN` | 루트의 `*A_cs2.py` (없으면 유일한 `*_cs2.py`) | A동 생성기 모듈 이름 |
| `FACADE_GLB` | `3dview.glb` | 스캔 파일 |
| `FACADE_MESHES` | `981188,981185,981186` | 스캔 메시 이름(첫 번째가 기준 동) |

PowerShell: `$env:FACADE_GEN = "ResidentialHighFooA_cs2"` / bash: `export FACADE_GEN=ResidentialHighFooA_cs2`

### 생성기 조건
도구가 생성기에서 다음을 가져다 씁니다(이번 생성기 구조 그대로):
`HALF`, `full_poly()`, `edges_of()`, `FH`, `floor_z()`, `a_edge()`, `windows_of()`, `WIN_KIND`, `make_atlas()`,
`build_tower()`, `window_unit`. 다른 구조의 생성기라면 `facade_read.py` 의 창 표시와 `window_count.py` 만 영향을 받습니다.

## 1. 사진 구간 등록 — `photo_sections.py` 의 `PHOTOS`

새 건물에서는 `PHOTOS` 가 비어 있습니다. 같은 파일의 `EXAMPLE_PHOTOS`(삼한골든뷰 등록 예)를 보고 똑같은 형식으로 채웁니다.

사진 한 장을 **구간(section)** 으로 나눕니다. 구간 = 카메라를 향한 같은 깊이의 벽 묶음(예: 앞쪽 머리 벽, 뒤쪽 막대 벽).

```python
dict(file="atype-1.png", masks=labels(...), secs=[
    dict(name="bar", walls=[12, 14, 16, 18, 20, 22, 24],   # A동 평면의 edge 번호 (plan_index.py 그림 참고)
         a=(-5.6, 32.6), px=(590, 1047),                   # 평면 위치 a 두 개 <-> 사진 x 픽셀 두 개 (직선 비례)
         fl=((24, 1562), (56, 329)),                       # (층, 창 줄 y) 두 개 - 대략이면 됨
         rowx=(932, 947)),                                 # 매 층 같은 작은 창이 있는 세로 띠(x 픽셀) - 층 추적용
])
```
- `masks`: 매물 표시 글자 등 가릴 상자 `(x0, y0, x1, y1)`. 파란/분홍 강조 띠는 색으로 자동 제외됩니다.
- **주의(가장 중요)**: `fl` 의 층 번호를 손으로 정하면 사진마다 ±1층씩 어긋납니다. 번호는 반드시 아래 2번의
  `refuge_scan.py` 로 **대피층 줄부터 세어서** 확인하고, 어긋나면 `fl` 의 층 번호를 고칩니다.

## 2. 도구별 사용법

### plan_index.py — 평면 edge 번호 그림
`python tools/photo_facade/plan_index.py` → `previews/plan_A.png`, `plan_B.png` (벽 번호, 파랑=is_bal, 빨강=머리 벽).
edge `i` 와 `i+28` 은 점대칭 짝입니다(평면 위치 a → -a).

### facade_read.py — 표시된 확대 사진 + 층별 구역 표
```
python tools/photo_facade/facade_read.py A 0 bar --chunks 3 --f 24,57          # 확대 그림 3장
python tools/photo_facade/facade_read.py A 0 bar --table --walls 12,14         # 층별 구역 표
  옵션: --a al,ar --px pl,pr (구간 맞춤 덮어쓰기)  --zoom 2.5  --rowh 0.62
```
- 그림: 왼쪽 빨간 눈금 = 층 바닥선과 층 번호, 위쪽 자홍 = 벽 경계, 하늘색 = 모델 창 위치(L/M/m/S/V).
  **하늘색 창이 사진 창 위에 오면** 가로 맞춤이 맞은 것입니다.
- 표: 벽마다 구역(P=창 사이 기둥, 창 아래/위) × 층, 글자 W 흰색 / g 회색 / b 파랑 / n 어두움 / - 가림.
  그림자·반사에 약하므로 **참고용**. 최종 판단은 그림을 보고 합니다.

### refuge_scan.py — 대피층부터 층을 세어 층별 점수 (핵심 도구)
```
python tools/photo_facade/refuge_scan.py A 0 bar --rowa px:932:947 --gapa px:735:770 \
       --spans "w12:-5.3:4.4,w14:5.0:11.7" [--mode band|blue|light] [--show] [--refy 1375]
```
- `--rowa`: 매 층(대피층 포함) 창이 있는 세로 띠(작은 창 S 열). `px:x0:x1` 또는 평면 위치 a.
- `--gapa`: 대피층에서 **없어지는** 큰 창(L/M) 열. 이 열이 밝은 줄 = 대피층 = 29층.
- `--spans`: 점수를 낼 가로 구간 `이름:a0:a1`.
- `--mode band`(기본): 창 아래 흰 띠 밝기 x100. **높음(80~100) = 흰 띠 있음(줄무늬 층/흰 벽), 낮음(30~50) = 통 패널(블록 층)**.
  `blue`: 파란 정도, `light`: 기둥 밝기.
- 대피층을 못 찾으면 `--show` 로 줄 목록을 보고 `--refy <y>` 로 직접 지정.
- 맨 위 몇 줄(옥상·하늘)은 100 으로 나오니 무시합니다.

### band_scan.py — 등록된 층 번호 그대로의 띠 점수
`python tools/photo_facade/band_scan.py A 0 bar "12,14,s1:-3.6:-2.4" 24,56 [--shift -1]`
`refuge_scan` 과 같은 점수지만 `PHOTOS` 의 `fl` 번호를 씁니다(`--shift` 로 보정). 두 사진(앞/뒤 짝 벽) 결과를 나란히 비교할 때 편합니다.

### window_template.py — 여러 층을 겹친 "한 층 창 모양"
`python tools/photo_facade/window_template.py A 4 head 42 56 [a_l a_r px_l px_r]`
→ 창마다 평면 위치 a 범위, 폭(m), 높이 z(m)를 출력하고 `previews/wtpl_*.png` 저장. 대피층은 자동 제외
(`f0 = f1 = 29` 로 주면 대피층만). 해가 드는 사진에서 가장 정확합니다. 이 값으로 생성기 `WIN` 표를 씁니다.

### refuge_crop.py — 27~31층만 3배 확대
`python tools/photo_facade/refuge_crop.py A 0 bar previews/ref.png` → 대피층 줄을 빨간 막대로 표시. 대피층 창 확인용.

### montage.py — 겹침 그림 오른쪽 절반 이어 붙이기
`python tools/photo_facade/montage.py "previews/paint_detail/B_btype-*.png" previews/m.png`

### window_count.py — 모델 층별 창 개수
`python tools/photo_facade/window_count.py <GeneratorModule>` → 25~33층 창 개수.
생략하면 프로젝트의 `*A_cs2.py`(또는 `FACADE_GEN`)를 씁니다. 대피층만 개수가 줄어야 정상입니다.

### glb_slices.py / glb_mirror_test.py — 스캔 평면 비교
- `glb_slices.py`: 각 메시를 바닥+100 m 높이에서 잘라 위에서 본 외곽선 → `previews/glb_slices.png`.
- `glb_mirror_test.py`: 기준 메시(첫 번째)와 나머지를 회전/반전해 겹쳐 보고 거리(m)를 출력.
  "mirror" 쪽이 작으면 반전 평면. (몇 분 걸립니다)

## 3. 작업 순서 (이번에 효과가 있었던 방식)

1. `plan_index.py` 로 벽 번호 확인 → `PHOTOS` 에 사진 구간 등록.
2. `facade_read.py --chunks` 로 하늘색 창 표시가 사진 창에 맞는지 확인(가로 맞춤 `a`/`px` 수정).
3. `refuge_scan.py` 로 **대피층부터 층 번호 확정**. 앞/뒤(점대칭 짝) 사진 결과가 같으면 신뢰.
4. 창: `window_template.py` 로 벽별 창 목록 → 생성기 `WIN` (모든 층 동일, 대피층만 따로 `REFUGE_WIN`).
5. 도색: `refuge_scan.py --mode band/blue` 로 블록·묶음 층 범위 → 생성기 `WALLS`
   (벽마다 `(a0, a1, 규칙)` 사각형, 규칙 = 고정 색 또는 층 집합 함수). **칸 단위 자동 판정은 쓰지 않습니다.**
6. `python tools/cycle.py <Name>_cs2.py --label <단계>` 후 같은 각도 렌더와 사진을 나란히 비교:
   ```
   python tools/render.py output/<asset> -o previews/v.png --views "yaw0:pitch3,yaw180:pitch3,yaw270:pitch3,yaw90:pitch3" --size 700x1300
   python tools/render.py output/<asset> -o previews/z.png --views "yaw0:pitch2" --zoom 3.2,0.62,0.6 --size 900x1100
   ```
7. 고치기 전 `python tools/compare.py snap output/<asset>` 로 스냅샷.

## 4. 이번 작업에서 얻은 교훈
- **층 번호는 대피층 줄부터 센다.** 손으로 정한 기준점·매물 표시 층수는 ±1층 틀렸다.
- **도색은 큰 사각형 + 층 규칙.** 실제 아파트 도색은 규칙적이다(이번: 블록 5-4-4-3-2-1층, 기둥 4층 묶음 11층 간격).
  픽셀 칸 판정(옛 `photo_sections.main()`)은 유리·그림자·반사가 섞여 "그림"처럼 된다.
- **창은 벽별 목록, 모든 층 동일**(대피층 제외). 균등 간격 규칙은 창 크기를 다 같게 만든다.
- 해가 드는 사진에서 색·창 크기를, 흐린 날 사진에서 띠/블록(그림자 없음)을 읽는다.
- 대피층은 모든 벽에 적용(큰·중간·반높이 창 제거, 작은 창·루버만, 일부 벽에 작은 네모 창).
