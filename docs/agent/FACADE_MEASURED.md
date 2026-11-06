# 측정 기반 파사드 작업 가이드 (cs2kit)

이 문서는 `cs2kit` 생성기에서 평면 사진 ref로 창·루버·도색·저층부를 맞출 때
반복해서 틀렸던 원인과, 다시 했을 때 바로 효과가 있었던 방법만 기록한다.
특정 건물의 좌표·색·창 수는 여기에 넣지 않는다. 그 값은 해당 프로젝트의
`building_spec_<Name>.yaml`과 생성기에 둔다.

## 0. 먼저 확인할 것

- **실제 렌더 색은 style YAML에서 온다.** `templates/styles/*.yaml`의
  `palette`/`window`/`layers`를 고쳐야 asset이 바뀐다. `building_spec`의 색 설명은
  문서이며 렌더 입력이 아니다.
- 창 배치의 실제 입력은 생성기의 `WALL_WINDOWS` 같은 테이블이다.
  spec의 `per_face` 설명만 고쳐도 geometry는 바뀌지 않는다.
- mass는 GLB에서 온 `generic_spec.json`을 유지한다. 사진이 안 맞는다는 이유로
  층수·bay 수·mass를 줄이지 않는다.

## 1. 근거 우선순위

1. `TASK.md`, GLB mass, `generic_spec.json`
2. 측정된 평면 ref의 `wall_id`, segment, `size_m`, `corners`
3. 생성기의 측정 테이블(`columns`, paint grid, offset)
4. style YAML의 재질·색
5. `building_spec`의 설명과 `estimated` 목록

문서와 렌더 입력이 다르면 **렌더 입력이 진실**이다. 둘 다 맞춘다.

## 2. 평면 ref 매핑

- ref마다 `wall_id`, 벽 시작 기준 offset, `size_m`, `side`, flip 여부를 기록한다.
- `size_m`은 **사진이 실제로 덮는 구간**이다. GLB edge 전체 길이와 다를 수 있다.
  - ref 구간이 벽보다 짧으면: 사진 구간만 crop하고, 창은 그 구간 안에 배치한다.
  - ref 구간이 벽보다 길면: `column_scale = wall_length / ref_length`를 명시한다.
- 픽셀 → 미터: `size_m / ref_pixel_width`. 가로·세로를 같은 ppm으로 warp한다.
- `corners` 순서가 뒤집히면 창 순서가 좌우 반전된다. 비대칭 특징(창 폭, 루버 위치)으로
  반드시 한 번 확인한다.
- p16+p15처럼 한 벽을 여러 ref로 덮으면 offset을 더해 **하나의 벽 좌표계**로 합친다.

## 3. 자동 margin/gap 대신 측정 column

측정된 면은 자동 분배를 쓰지 않는다.

```python
"mass_01_00:edge_05": dict(columns=[
    ("wide", 1.10, 4.31),
    ("small", 5.84, 7.28),
    ("louver", 10.31, 11.25),
], column_scale=1.0)
```

- `columns`는 `(kind, start_m, end_m)`다.
- 측정 면의 `layout_face`는 margin/gap 재분배를 건너뛰고 좌표를 그대로 쓴다.
- 창 폭은 kind 기본값이 아니라 **측정 폭**을 유지한다. kind는 높이/sill 결정에만 쓴다.
- 모든 column이 `0 <= start < end <= wall_length`인지 검증한다.
- 측정 면에 `pattern`과 `columns`를 동시에 쓰지 않는다. 우선순위를 코드에 명시한다.
- 반복해서 `gap=`, `margin=`만 바꾸는 것은 해결이 아니다. 2회 이상 같은 면이
  어긋나면 pixel run을 다시 재서 column 좌표로 바꾼다.

### 사진에서 열 좌표 재기

1. 창 한 줄이 잘 보이는 y band를 고른다(상단 3~5층 권장).
2. 각 열의 어두운 run / 회색 louver run의 x 시작·끝을 기록한다.
3. `x_m = x_px / ref_px_width * size_m`로 변환한다.
4. 같은 높이의 이웃 면과 폭이 지나치게 다르면 ref 구간 또는 scale을 의심한다.
5. 상단 crop과 하단 crop을 따로 본다. 전체 세로 시트만 보면 열을 놓친다.

## 4. 이미지 공간 비교

`box`로 geometry를 자르는 비교는 렌더러가 면 중심으로 필터링하고 벽을 쪼개지 않으면
실패한다. 이때는 full side를 렌더해 **이미지에서 crop**한다.

```bash
python tools/render.py output/<asset> -o previews/full_front.png \
  --views front --size 1200x3200 --nolabel --no-cache
```

- 벽의 `p0/p1`과 카메라 side 범위로 화면 x 비율을 계산해 crop한다.
- photo와 model crop을 같은 `size_m` 폭·같은 ppm으로 맞춘다.
- **segment ref를 whole-wall render와 비교하지 않는다.** 반대도 마찬가지다.
  이 실수로 두 번째 창이 crop 밖으로 사라진 적이 있다.
- left/right preset과 `photo_check`의 side 명칭이 반대일 수 있다. 실제 렌더 방향으로 확인한다.
- 뒤집힘(flip)은 crop 후 창 순서로 검증한다.
- 비교 시트는 `photo | model | diff`로 저장하고, 상단·하단을 확대해 본다.
- raw pixel diff는 조명(햇빛/그늘)이 지배한다. **열 수·위치·폭 판정에는 유효**하지만
  albedo 판정으로 쓰지 않는다. 색 판정에는 조명 정규화가 별도로 필요하다.

## 5. Per-cell paint

- `band_scan` grid는 **햇빛 받는 평면 ref**에만 albedo로 적용한다. 그늘 ref는 layout만.
- `cell_id=-1`은 칠하지 않는다. 창·루버·나무·사인·그림자는 mask/avoid로 제외한다.
- 적용 벽의 z 범위로 자른다:

```python
z0 = max(volume_z0, row_z[r])
z1 = min(volume_z1, row_z[r + 1])
```

  이 clamp가 없으면 podium row(z=0)까지 tower 평면에 칠해져 base 창을 가린다.
- ref 구간과 벽 길이가 다르면 `xscale`을 명시하고, 창 avoid 좌표도 같은 좌표계로 맞춘다.
- 도색은 창을 대신하지 않는다. 창은 `WindowSet` geometry로 만든다.
- `WIN_BLOCKED`가 뜨면 창 자체보다 **앞에 떠 있는 paint quad**를 먼저 의심한다.
  차단 위치의 UV가 어느 atlas cell인지 확인하면 범인을 바로 찾을 수 있다.

## 6. 저층부(podium)는 별도 건물로 본다

- tower 마감을 base에 복사하지 않는다. 각 면의 하단 crop을 보고 면별로 정한다.
- 한 podium이 전부 어두운 석재인 경우는 드물다. 밝은 벽, 어두운 벽, 유리 행,
  빈 벽이 면마다 다를 수 있다.
- base 창은 tower 창과 별도 row/floor/unit으로 추가하고, 개수를 spec에 함께 기록한다.
- base 벽 paint와 창 frame의 offset을 분리한다(벽 0.004, frame 0.034 등).
- podium 상단 band와 tower 첫 floor band가 겹치지 않게 z를 확인한다.

## 7. WindowSet, 유리 variant, 야간 점등

- 모든 창에 `unit=0`을 주지 않는다. **bay별 household ID**를 준다:
  `unit = bay_index + offset`.
- `WindowSet`의 UV는 `K.REF_GRID` 셀에 배정된다. style의 `patch_grid`를 쓸 경우
  반드시 `K.REF_GRID`와 같게 한다.
- 주간 유리 variant는 household 셀 전체에 적용한다. 창 중간만 밝/어둡게 나뉘면
  UV 셀보다 finer patch를 쓴 것이다.
- 야간 emissive:
  - 창 전체가 점등되어야 한다. 24×24 patch는 낮 preview에서도 35%가 더해져
    반쪽 창처럼 보인다.
  - 정확한 비율은 modulo threshold가 아니라 hash rank로 고른다:

```python
order = np.argsort(hash_values.ravel())
lit_lut[order[:int(round(cell_count * ratio))]] = True
```

- 흰색 emissive를 유지하고 적/녹색이 섞이지 않았는지 `--night`으로 확인한다.
- 창 수가 바뀌면 tower/podium/lobby를 나눠 spec에 다시 기록한다.

## 8. LOD silhouette

- `lod_check.json`의 `where`에 xyz와 normal이 나온다. 실패 지점을 먼저 읽는다.
- roof screen corner에서 main만 0.05%를 살짝 넘으면, 해당 모서리에 작은
  closed box post를 main에 추가한다. LOD1/LOD2 volume은 이미 닫혀 있으면 건드리지 않는다.
- post는 **측정 footprint를 바꾸지 않는** 최소 크기로 한다.
- 층수·bay·창 위치를 줄여 LOD를 맞추지 않는다.
- 0.049%처럼 limit에 가까우면 PASS라도 `marginal`과 여유를 보고서에 적는다.

## 9. Gate와 보고

- geometry 변경마다 `quick`, preview/photo가 필요하면 `visual`, 완료는 `final`.
- `final`의 `next_action`에 나온 artifact를 **전부** 보고, 반환된 review 명령을 실행한다.
- 마지막에 `agent.py require-final`.
- `photo`/`tiles` PASS는 구조 일치이지 픽셀 완벽이 아니다. 한계를 같이 적는다.
- spec에는 최소한 다음을 실제 값으로 맞춘다:
  - `main_tris`, `windows_total`, tower/podium/lobby 창 수
  - `louver_panels_total`
  - per-face 열 구성
  - `lod_check` max와 bad_views
- 창 수가 줄었으면 왜 줄었는지 설명한다(예: 잘못 넣은 4열 → 사진의 2열).

## 10. 운영 습관

- 한 iteration에 의미 있는 변경 하나. 비교 helper는 `work/`에 두고 `tools/`는 건드리지 않는다.
- interrupted `agent.py` 후 `work/agent.lock`이 남으면 PID가 실제로 없는지 확인한 뒤에만 지운다.
- ref 사진은 이동·수정·복사하지 않고 `output/`에 넣지 않는다.
- 브랜드/로고/간판 글자를 asset 이름이나 texture에 넣지 않는다.
- 같은 wall+metric이 3회 반복 실패하면 더 돌리지 말고 evidence와 이유를
  `photo_mismatch_notes`에 기록한다.

## 빠른 체크리스트

- [ ] style YAML이 실제 색 입력인지 확인
- [ ] ref segment와 wall 길이/offset/flip 확인
- [ ] 측정 column을 고정 좌표로 넣었는가
- [ ] 상단·하단 crop을 따로 봤는가
- [ ] per-cell paint가 volume z 범위를 벗어나지 않는가
- [ ] podium을 면별로 봤는가
- [ ] bay별 `unit`을 줬는가
- [ ] 야간이 창 전체 단위 흰색인가
- [ ] LOD `where`를 읽고 최소 post로 닫았는가
- [ ] spec 수치와 최종 gate를 실제 값으로 갱신했는가
