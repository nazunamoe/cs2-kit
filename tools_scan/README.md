# tools_scan — glb/gltf 건물 스캔 분석 도구

3D 지도(네이버 부동산 등) glb 스캔을 **다른 프로젝트에서도 그대로** 뜯어볼 수 있는 도구.
키트의 `tools/`, `cs2kit.py` 는 건드리지 않는다. 의존성: numpy, matplotlib, Pillow (블렌더 불필요).

## 설치/실행

프로젝트 루트(키트 루트)에서:

```bash
python tools_scan/scan_tool.py list photos/3dview.glb
```

## 명령

| 명령 | 하는 일 | 출력 |
|---|---|---|
| `list` | glb 안의 건물 메시 목록 (이름, tris, 크기, 높이) | 콘솔 |
| `info` | 메시 하나의 크기·표면적·높이 레벨 요약 | 콘솔 |
| `roof` | **옥상 분석**: 위를 향한 면 → 높이 레벨 → 연결 성분(데크/파라펫 띠/옥탑 상자) | `roof_top.png`, `roof_heightfield.png`, `roof_levels.json` |
| `slice` | 높이별 단면 폴리곤 (꼭짓점 좌표 포함) | `slices.png`, `slices.txt` |
| `elev` | x-z / y-z 실루엣 입면 | `elev.png` |
| `top` | 위에서 본 평면 실루엣 | `top.png` |
| `compare` | 스캔 vs 모델 OBJ **자동 정렬**(x/y 뒤집힘 판별) + **옥상 레벨 비교** | `compare.png`, `compare_levels.json` |
| `report` | roof+elev+top+slice를 한 번에 | `report.md` + 그림 |

## 공통 옵션

```
--mesh 이름|번호   메시 선택 (list 로 확인)
--up y|z           높이 축 (기본 y, glTF 규격)
--axes x,-z        평면 두 축, 앞에 '-' 면 뒤집기 (기본 x,-z)
--shift dx,dy,dz   축 변환 뒤 이동 (기본 0)
--ground auto|값    높이 기준. auto = 최저점 0 (기본 auto)
--level 0.15       옥상 레벨 묶음 허용 오차(m)
--cell 0.25        높이장 칸 크기(m)
-o 폴더            출력 폴더 (기본 <glb 폴더>/scan_out)
```

### 좌표 맞추기 (가장 중요)

스캔 glb 마다 축이 다르다. 네이버 3D 지도 glb는 보통 **x=동서, y=높이, z=남북** 이고,
기존 프로젝트의 모델 좌표는 `x = x_scan − cx`, `y = z_scan − cy`, `z = y_scan − 지면` 으로 썼다.
그때는 이렇게 준다:

```bash
python tools_scan/scan_tool.py roof photos/3dview.glb --mesh 887188 \
  --axes x,z --shift=-218.38,-506.6,0 --ground 74.51 -o work/scan
```

- **부호가 헷갈리면** `compare` 를 돌려라. 모델 OBJ 와 자동으로 x·y 뒤집힘을 시험해
  가장 잘 맞는 조합과 IoU 를 알려준다. (x*1, y*1 이면 맞는 것)
- 축을 잘못 잡아도 단면·옥상 분석 자체는 되지만, 모델과 비교할 때만 틀어진다.

## roof 출력 읽는 법

`[z 63.67] area 240.3 comps 3` = 높이 63.67 m 에 위를 향한 면이 240 m², 3덩어리.

각 성분 줄의 태그:

| 태그 | 뜻 | 판정 |
|---|---|---|
| `DECK` | 그 레벨에서 가장 큰 성분(지붕판) | 면적 20 m² 이상 |
| `band` | 길고 좁은 띠 (파라펫·갓돌·루버 상단) | 짧은 변 ≤ 1.8 m, 종횡비 ≥ 3 |
| `box` | 옥탑·기계실 같은 상자 | 면적 3 m² 이상 |
| `small` | 그 외 작은 면 | |

- `rect W x H @ 각도` 는 **최소 면적 회전 사각형**이다. 45° 동체의 옥탑이면 45° 로 나온다.
- `bbox` 는 축 정렬 범위.
- 옥상 조형을 볼 때: **데크 높이와 파라펫 띠가 따로 있는지**, 옥탑 상자가 데크보다 얼마나 높은지,
  띠가 벽인지 난간인지(띠가 얇으면 난간·루버 후보)를 표로 바로 판단한다.

`roof_top.png` 는 높이별 색 + 성분 라벨, `roof_heightfield.png` 는 0.25 m 격자 높이장.

## compare — 옥상 조형이 맞는지 자동 점검

```bash
python tools_scan/scan_tool.py compare photos/3dview.glb --mesh 887188 \
  --axes x,z --shift=-218.38,-506.6,0 --ground 74.51 \
  --model output/<에셋>/_check/<에셋>.obj -o work/scan
```

- 모델 OBJ 는 키트가 내보낸 `_check/*.obj` (y=높이, z=깊이 중심) 를 그대로 읽는다.
- x·y 뒤집힘 4가지를 시험해 **평면+입면 IoU** 가 가장 좋은 정렬을 고른다.
- 이어서 **스캔과 모델의 옥상 레벨을 나란히** 표로 보여준다.
  예: `scan 65.06 (A 4.1) / model 65.01 (A 336.2)` → 모델이 옥상 가장자리를 벽으로 채워
  지붕판이 안 보인다는 뜻. (실제로 이 프로젝트에서 그 문제를 이 표로 잡았다)

## 주의

- **LOD 스캔 경고**: tris < 3000 이면 지도 LOD 메시다. 옥탑·난간·루버 같은 작은 구조는
  뭉개져 있을 수 있다 → 반드시 **roofview 사진**으로 대조한다 (그래서 `roof`·`report` 가 경고를 찍는다).
- **winding 반대**: 스캔 메시는 노멀이 뒤집힌 경우가 있다. `info`/`roof` 가 경고하고
  `|nz|` 로 판정한다. `roof_top.png` 제목에 `winding flipped` 로 표시된다.
- 텍스처는 읽지 않는다(형상 전용). KTX2/basis 텍스처가 있어도 무관.
- Draco 압축 glb 는 지원하지 않는다(오류 메시지로 알려 줌). Blender 로 풀거나 키트 `glb_measure` 사용.
- 스킨드/애니메이션 메시, 여러 primitives 는 합쳐서 읽는다. 노드 변환(matrix/TRS)은 적용한다.

## 이 프로젝트(101동)에서 쓴 예

```bash
python tools_scan/scan_tool.py report projects/<name>/photos/3dview.glb \
  --mesh 887188 --axes x,z --shift=-218.38,-506.6,0 --ground 74.51 \
  -o projects/<name>/work/scantest
python tools_scan/scan_tool.py compare projects/<name>/photos/3dview.glb \
  --mesh 887188 --axes x,z --shift=-218.38,-506.6,0 --ground 74.51 \
  --model projects/<name>/output/<Asset>/_check/<Asset>.obj \
  -o projects/<name>/work/scantest
```
