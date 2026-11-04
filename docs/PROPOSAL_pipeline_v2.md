# PROPOSAL — 파이프라인 2차 개선안 (설계안, 미구현)

이 문서는 사용자가 2026-11-04에 요청한 5가지 개선점의 **설계안**이다. `AGENTS.md` Hard rule 3/4
("cs2kit.py / tools/ 편집 금지")와 `CLAUDE.md` 메모("키트 개선은 제안만")를 지키기 위해,
실제 코드는 아직 하나도 바꾸지 않았다. 아래 설계를 승인하면 다음 턴에 실제 구현으로 넘어간다.

현재 저장소 확인 결과: `glb_slices.py`, `facade_read.py`, `band_scan.py`, `lod_check.py` 는
전부 **새 파일**이다(기존에 없음). "lod_check.py"에 해당하는 기존 파일은 `tools/check.py` 이므로,
4번 항목은 `check.py`를 확장하는 것으로 본다. 기존 `facade_paint.py`(층/창/도색 3단계) 와
`glb_measure.py`(스캔 치수)의 입출력 스타일을 그대로 따른다.

---

## 1. `glb_slices.py` (신규) + `facade_read.py` (신규, facade_paint.py 와 역할 분리)

### glb_slices.py
```
python tools/glb_slices.py scan.glb --z 1.5,15.0,30.0 [--scale 1.0] [--up y] [--out previews/glb/slices.json]
```
- `glb_measure.py` 의 삼각형 로딩 코드(스케일/업축 처리)를 그대로 재사용하는 방식(복붙이 아니라 같은 로직
  패턴)으로, 지정한 각 z 에서 메시를 평면과 교차시켜 외곽 폴리곤(들)을 얻는다.
- 폴리곤 변마다: `id`("wall_0", "wall_1", ... — 둘레를 따라 순서대로 부여), `start`/`end` 정점(x,y),
  `length_m`, `normal_deg`(0~360, 외곽선 바깥쪽을 향하는 법선 방위각).
- 여러 z 레벨을 지정하면, 레벨 간에 **위치+각도 허용오차 안에서 겹치는 변을 같은 wall_id로 병합**해서
  건물 높이 전체에 걸친 벽 하나로 묶는다(단, 단차 구간은 자동으로 별도 wall_id가 된다 — 이게 의도된 동작).
- 출력 `previews/glb/slices.json`:
  ```json
  {"levels": [1.5, 15.0, 30.0],
   "walls": [{"id": "wall_0", "start": [x,y], "end": [x,y], "length_m": 12.3,
              "normal_deg": 182.4, "z_range": [0, 30]}]}
  ```
- **확인 필요(가정)**: `normal_deg` 의 0도 기준축을 `naver_vr.py` 가 카메라 방향을 쓰는 축과 맞춰야 한다.
  지금 코드를 안 읽어서 확정 못 함 — 구현 턴에서 `naver_vr.py` 의 방위각 정의를 먼저 확인하고 맞춘다.

### facade_read.py
```
python tools/facade_read.py --slices previews/glb/slices.json --vr-dir <naver_vr 출력 폴더> [--out previews/facade_read/]
```
- 각 wall의 `normal_deg` 와 8방향 캡처 이미지의 카메라 방위각(naver_vr.py 출력에 메타가 있다고 가정 —
  없으면 그 쪽에 yaw를 기록하도록 제안을 추가해야 함, 구현 턴에서 확인) 중 **원형 거리(circular distance)
  최소**인 이미지를 매칭한다.
- 매칭된 이미지와 벽의 각도차 `theta = camera_yaw - normal_deg` 에 대해:
  - `|theta| <= 45도`: 수평 폭을 `1/cos(theta)` 로 보정(평면 벽을 측면에서 봤을 때의 1차 근사. 진짜
    호모그래피가 아니라 "카메라가 벽과 같은 높이에서 수평으로만 돌아간" 단순 가정이라고 YAML/주석에
    명시 — 상하 기울임이 큰 사진에는 틀린다).
  - `|theta| > 45도`: 보정하지 않고 `confidence: "low_angle"` 로 표시, 창 열 인식은 하되 수치는
    참고용으로만 쓰라고 출력에 경고.
- 보정된 이미지에서 `facade_paint.py` 의 기존 창문/층 인식 로직과 같은 방식으로 창 열(세로)·층(가로) 경계를
  찾아, **절대 좌표 대신** 벽 기준 정규화 좌표로 변환:
  - `U: [u0, u1]` = (창 왼쪽, 창 오른쪽) / wall length_m, 0~1
  - `V: [v0, v1]` = (창 아래, 창 위) / 그 층의 층고, 0~1 (층 경계는 `glb_measure` 나 `TASK.md` 층고로 나눔)
- 출력 `previews/facade_read/<wall_id>.json`:
  ```json
  {"wall_id": "wall_2", "image": "cap_135.jpg", "normal_deg": 138.2, "camera_yaw": 135,
   "theta_deg": 3.2, "width_correction": 1.0015, "confidence": "ok",
   "columns": [{"u": [0.12, 0.18], "type": "window"}],
   "rows": [{"v": [0.0, 0.34], "floor": 1}]}
  ```
- `photo_refs.json` 수동 입력 방식은 그대로 둔다(사용자가 이미 만든 건 안 바꾸는 규칙 유지) — 이 도구는
  `photo_refs.json` 이 없을 때 자동으로 비슷한 결과를 만들어주는 **보조 경로**로 추가한다.

---

## 2. `band_scan.py` (신규) + `cs2kit.py::apply_facade_paint_grid`

### band_scan.py
```
python tools/band_scan.py --wall previews/facade_read/wall_2.json --photo <원본> [--k 4] [--out previews/paint_grid/wall_2.json]
```
- `facade_read.py` 가 찾은 행(층/스팬드럴 경계)·열(창/기둥 경계) 선을 그대로 그리드 축으로 쓴다(그리드를
  새로 추정하지 않음 — 1번 산출물을 재사용해 두 도구가 어긋나지 않게 한다).
- 각 셀(행×열)에서 `LESSONS.md` 의 기존 원칙대로 "셀 안에서 표준편차가 가장 낮은 박스"를 찾아 중앙값
  색을 뽑는다. 표준편차가 임계값(예: 12) 넘으면 `MIXED`(유리 반사·그림자 혼입)로 표시하고 클러스터링에서
  빼고, 나중에 가까운 깨끗한 셀의 색으로 채운다.
- 클러스터링 전에 각 셀의 L(명도)을 그 사진의 기준 L로 정규화(`LESSONS.md` 의 same-L dE 원칙)해서
  **조명 차이를 색 차이로 오판하지 않게** 한다. 단, LESSONS 에 적힌 "same-L만 쓰면 면 전체가 다른 색인
  경우를 못 본다"는 함정을 피하려고, 정규화 전 raw 명도 비율도 같이 저장해서 `band_scan.py` 출력에
  `raw_L_ratio` 필드로 남긴다(면적 비율 검산용).
- K-Means(`k` 기본 4: 주조색/보조색/강조색/저층부 석재)로 클러스터 ID를 셀마다 배정.
- 수평 악센트 밴드(한 행 전체가 같은 클러스터이고 위아래 행과 다른 경우)를 따로 찾아 `accent_bands` 로 기록.
- 출력 `paint_grid.json`:
  ```json
  {"wall_id": "wall_2", "rows": 12, "cols": 8,
   "cell_id": [[0,0,1,0,...], ...],
   "palette": {"0": "#dadcdf", "1": "#a49d9c", "2": "#2a2c56", "3": "#9a98a2"},
   "accent_bands": [{"row_range": [4,5], "note": "same-L dE 2.9, raw_L_ratio 0.31"}],
   "mixed_cells": [[3,5]]}
  ```

### cs2kit.py: apply_facade_paint_grid
요청 문구는 `bmesh.ops.bisect_plane` 으로 경계마다 칼선을 넣으라는 것인데, 두 가지 방법을 비교해서
**A안을 권장**한다.

- **A안 (권장): 사각형 합치기 + 기존 `K.paint()` 오버레이.**
  같은 클러스터 ID가 붙은 셀들을 "2D 이진 행렬에서 최대 사각형 찾기"(히스토그램 방법, 라벨별로 적용,
  O(rows*cols))로 합쳐서 큰 사각형 몇 개로 줄인다. 사각형마다 행/열 경계를 U/V → 실제 `a`(벽을 따라
  거리)/`z` 로 변환한 뒤 `K.paint(mb, axis, c, s, a0, a1, z0, z1, region, layer=N)` 를 호출한다.
  겹치는 사각형은 LESSONS 의 기존 규칙대로 layer 를 1씩 올려서 COPLANAR 를 피한다.
  장점: 이미 키트가 쓰는 "얇은 페인트 오버레이 + layer" 체계와 그대로 맞물려서 COPLANAR/UV 문제가
  새로 안 생기고, 벽의 기본 폴리곤 자체는 그대로라 tris 가 거의 안 늘어난다(사각형 수만큼만).
- **B안 (무거움): 진짜 `bmesh.ops.bisect_plane` 로 벽 폴리곤 자체를 색 경계마다 쪼개서, 각 조각에
  머티리얼 슬롯/UV를 배정.** 요청 문구와 더 가깝지만, 벽 하나의 tris 가 셀 수만큼 곱절로 늘고,
  현재 키트는 "메인 재질 1개" 규칙(LESSONS)과 `K.MeshBuilder` 가 이미 UV/아틀라스 셀 배정을 전담하므로
  `bisect_plane` 으로 만든 새 면에 UV를 다시 맞춰 넣는 코드를 따로 짜야 한다. 아틀라스 칸을 셀마다
  새로 쓰는 게 아니라 "색만 다른 평면 페인트"라면 B안이 주는 이득이 거의 없다.

제안: **도색이 평평한 색 구역이면 A안**, 만약 색 경계에서 실제로 요철(단차)이 있어야 하는 경우(석재
줄무늬처럼 입체감이 필요할 때)는 그 부분만 기존 `K.axbox`로 개별 처리하고 `apply_facade_paint_grid`는
"색만 다른" 영역에 한정한다. 함수 시그니처:
```python
def apply_facade_paint_grid(mb, wall_meta, paint_grid, palette, layer_base=1):
    # wall_meta: {"axis":..,"c":..,"s":..,"a0":..,"a1":..,"z0":..,"z1":.., "row_z": [...], "col_a": [...]}
    ...
```
`wall_meta` 는 3번 항목의 `BuildingMeta.WALLS[wall_id]` 를 그대로 넘기게 해서, 월드 좌표를 호출부에서
또 계산하지 않게 한다(요청의 "월드 좌표 직접 입력 금지" 원칙을 2번에도 일관되게 적용).

---

## 3. `cs2kit.py` 프리셋 + 소켓 장식 함수

### 프리셋
```python
def preset_plate_apartment(A, W, D, floors, floor_h, ground_h=4.5,
                            bays=4, core="back", balcony=True, railing="glass",
                            quality_stage=0) -> BuildingMeta: ...

def preset_tower_l_core(A, wing_a=(Lx, Wx), wing_b=(Ly, Wy), floors, floor_h,
                         core_pos="corner", corner_curtainwall=True,
                         quality_stage=0) -> BuildingMeta: ...

def preset_piloti_base(meta, piloti_h, column_grid, lobby_bay,
                        quality_stage=0) -> BuildingMeta:  # meta 를 받아 갱신 후 반환
```
- `preset_plate_apartment`: 판상형 4베이 매스, 발코니 통창 서브메시(확장형/비확장 — `TASK.md balcony`
  값과 그대로 연결), 철제 난간(`railing` 값), 후면 계단실 코어.
- `preset_tower_l_core`: L자 코어 타워 매스, 코너부를 `K.curtainwall` 서브메시로 자동 분리(코너
  멀리언은 `K.corner_post` 로 닫는 기존 규칙 그대로).
- `preset_piloti_base`: 저층부 필로티 기둥 배열 + 공동현관 로비 매스. 독립 프리셋이 아니라 다른 두
  프리셋이 만든 `meta` 에 **덧붙이는** 형태(필로티는 항상 어떤 동의 1층이므로).

### BuildingMeta (반환값, dataclass)
```python
@dataclass
class BuildingMeta:
    mb: K.MeshBuilder
    WALLS: dict          # wall_id -> {axis,c,s,a0,a1,z0,z1,normal_deg,row_z,col_a}
    ROOF_PERIMETER: list  # [(x,y), ...] 옥상 외곽 링
    FLOOR_RINGS: dict     # floor_index -> [(x,y), ...] 그 층 슬래브 상단 링
    ENTRANCE_SOCKETS: list  # [{"pos":(x,y), "facing_deg":.., "bay_index":N}]
```
`WALLS` 의 키(wall_id)는 프리셋이 의미 있는 이름("front", "wing_a_left", ...)으로 붙인다. 1번 항목의
`glb_slices.py` 가 뽑은 `wall_0`.. 과는 별개 ID 체계이므로, `facade_read.py`/`band_scan.py` 를 쓸 때는
**normal_deg + 위치로 최근접 매칭**해서 glb 쪽 wall_N 결과를 프리셋의 의미있는 wall_id 로 옮겨 쓰는
작은 매칭 단계가 하나 더 필요하다(구현 턴에서 `cs2kit.match_wall_ids(meta, slices_json)` 같은
헬퍼로 추가 제안).

### 소켓 장식 함수
```python
def attach_roof_crown(meta, style="parapet_light", height=1.2, quality_stage=0): ...
def attach_cornice_band(meta, target_floors, depth=0.15, height=0.3, quality_stage=0): ...
def attach_entrance_canopy(meta, bay_index, style="flat", quality_stage=0): ...
```
- 모두 `meta.ROOF_PERIMETER` / `meta.FLOOR_RINGS` / `meta.ENTRANCE_SOCKETS` 만 읽고, 내부에서
  해당 구간의 `meta.WALLS` 정보로 axis/c/s 를 찾아 기존 `K.axbox`/`K.paint`/`mb.box` 를 호출한다
  (월드 좌표 하드코딩 없이).
- `attach_entrance_canopy(style="flat")`: LESSONS 규칙("캐노피는 덩어리가 아니라 얇은 슬래브 + 기둥")을
  기본값으로 박아 넣는다.

### quality_stage (0~3) 공통 규약
```python
class QualityStage(IntEnum):
    FULL = 0        # 베벨, 음각 홈, 난간 메시 봉+유리 전부
    SIMPLIFY_RAIL = 1   # 난간을 알파컷 스트립 패널로, 베벨 제거
    SIMPLIFY_TRIM = 2   # 보조 음각 홈/몰딩 생략, 창틀 멀리언 수 축소
    LOD_CULL = 3        # 장식 함수는 즉시 반환(no-op), 프리셋은 LOD2용 박스만
```
모든 프리셋/장식 함수는 맨 앞에서 `if quality_stage >= QualityStage.LOD_CULL: return ...(경량 버전 또는 None)`
형태로 분기한다. `K.export_asset` 에 넘기는 `lod1=l1, lod2=l2` 를 만들 때 **같은 프리셋 호출을
quality_stage 를 다르게 줘서 세 번(메인/LOD1/LOD2) 부르는 패턴**을 표준으로 삼는다(지금처럼 생성기마다
LOD1/LOD2를 손으로 따로 쌓는 대신).

---

## 4. `tools/check.py` (요청의 "lod_check.py") — 에이전트 액션 태그

`check.py` 는 이미 리포트 dict(`report["main"]["tris"]`, LOD1/LOD2 tris, UV 오류 목록, 퇴화 면 목록 등)를
들고 있으므로, `main()` 끝에서 **기존 `RESULT ...` 줄은 그대로 두고 그 다음에 한 줄 추가**한다
(출력 순서상 추가이므로 `cycle.py` 의 기존 `RESULT ` 줄 파싱에는 영향 없음 — 다만 구현 턴에서
`cycle.py` 가 정말 "RESULT " 로 줄을 찾는지 재확인 필요).

```python
def agent_summary(report) -> dict:
    tags = []
    ratio = report["main"]["tris"] / 50000
    if 1.0 < ratio <= 1.15:
        tags.append("APPLY_STAGE_1")
    elif ratio > 1.15:
        tags.append("APPLY_STAGE_2")
    if report["lod1_too_big"] or report["lod2_tris"] > 500:
        tags.append("APPLY_STAGE_3_LOD_CULL")
    if report["uv_out_of_range"] or report["atlas_uv_errors"]:
        tags.append("CLAMP_UV")
    if report["degenerate_tris"]:
        tags.append("MERGE_VERTICES")
    fix = _FIX_TEXT.get(tags[0], "문제 없음") if tags else "문제 없음"
    return {"status": "FAIL" if report["errors"] else "PASS",
            "verts": {"LOD0": report["main"]["verts"], "LOD1": report["lod1"]["verts"],
                      "LOD2": report["lod2"]["verts"]},
            "action_tags": tags, "exact_fix_instruction": fix}
```
출력 줄: `[CS2_AGENT_SUMMARY] {... json.dumps(agent_summary(report), ensure_ascii=False) ...}`
(에셋이 여러 개면 에셋마다 한 줄).

`_FIX_TEXT` 매핑은 5번 문서의 대응표와 똑같은 내용을 코드 쪽에도 상수로 둔다(문서와 코드가 따로
놀지 않게, 이상적으로는 `_FIX_TEXT` 를 코드에만 두고 `TOOLS_CLAUDE.md` 는 그 표를 손으로 옮겨 적은
것이라고 명시해서 나중에 코드가 바뀌면 문서도 같이 고치라는 메모를 문서 쪽에 남긴다).

---

## 5. `TOOLS_CLAUDE.md` (신규 문서)

`AGENTS.md` 와 별도로, "프리셋/소켓 API만 쓰는" 모드의 건물 생성기 작성 규칙을 담는다. 초안 목차:

1. **금지**: 건물 매스 단계에서 `bmesh` 직접 호출, `K.axbox`/`K.paint`/`K.MeshBuilder.box` 를
   좌표 손계산으로 쓰는 것 금지. 장식 디테일 중 프리셋이 못 만드는 특수 지오메트리에만 예외 허용.
2. **필수 순서**: `preset_*()` → (필요시) `preset_piloti_base(meta, ...)` → `attach_*()` 들 →
   `apply_facade_paint_grid()` → `K.export_asset()`.
3. **action_tags 대응표** (4번의 `_FIX_TEXT` 를 문서화):

   | tag | 뜻 | 고칠 파라미터 |
   |---|---|---|
   | `APPLY_STAGE_1` | main tris 1~15% 초과 | 모든 `preset_*`/`attach_*` 호출의 `quality_stage` 를 +1 |
   | `APPLY_STAGE_2` | 15% 이상 초과 | `quality_stage=2`, 추가로 bay 수·반복 디테일 밀도 축소 |
   | `APPLY_STAGE_3_LOD_CULL` | LOD1/LOD2 한도 초과 | LOD1/LOD2 생성 시 `quality_stage=3` 전달 |
   | `CLAMP_UV` | UV 0~1 이탈 | custom quad UV를 `A.uv_full`/`A.uv_tile` 로 교체 |
   | `MERGE_VERTICES` | 축퇴 삼각형 | 루프 들여쓰기 등으로 같은 prese/attach 가 중복 호출됐는지 확인 |

4. **Few-shot 예시** (판상형/타워형 각 20줄 내외, 실제 함수 시그니처가 구현 턴에서 확정되면 그걸로 채움).

---

## 미결 사항 (구현 턴 시작 전에 확인할 것)
1. `naver_vr.py` 가 캡처마다 카메라 방위각(yaw)을 메타데이터로 이미 남기는지 — 아니면 그쪽에 먼저
   추가해야 `facade_read.py` 의 자동 매칭이 성립한다.
2. `cycle.py` 가 `check.py` 출력에서 `RESULT ` 줄을 어떻게 찾는지(정규식/줄 시작 매칭) 확인해서
   `[CS2_AGENT_SUMMARY]` 추가 줄이 그 파싱을 깨지 않는지 확인.
2. 2번 항목의 A안(페인트 오버레이)과 B안(실제 bisect) 중 어느 쪽으로 할지 — 지금은 A안을 권장했지만
   사용자가 "진짜 메시 분할"을 원하면 B안으로 간다.
3. `preset_*` 가 기존에 손으로 짠 생성기(`namsan_xihanulche` 등)를 깨지 않는지 — 기존 건물은
   프리셋으로 재작성하지 않고 새 건물부터 적용하는 것으로 제안.
