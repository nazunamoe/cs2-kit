# CS2 Korean building asset kit — Codex / Kimi Code

사진과 건축 정보를 바탕으로 Cities: Skylines II 건축 에셋 생성기를 만드는 키트입니다. `cs2kit`는 형상·아틀라스·창·LOD·납출을 담당하고, `tools/`는 반복 빌드와 검증을 담당합니다.

## 구조

```text
AGENTS.md                 Codex/Kimi 자동 작업 규칙 (짧은 공통 규칙)
TOOLS.md                  필요할 때 읽는 도구/API 설명
docs/agent/WORKFLOW.md    빌드·검증·재개·부분 수정 절차
docs/agent/MODELING.md    상세 입면·사진·재질 규칙
docs/agent/MEMORY.md      전역 기억과 프로젝트 관찰값의 구분
cs2kit.py                 공통 생성 라이브러리
projects/<name>/          TASK.md, STATUS.md, photos, generator, output, previews, work
memory/                   재사용 가능한 절차와 기본값 (프로젝트 전용 색상/좌표 금지)
templates/                새 프로젝트 양식
tools/agent.py            모든 CLI가 공유하는 JSON 실행 엔진
tools/cycle.py            quick/visual/final 공통 게이트
```

## 설치와 시작

Python 3.9+, numpy, Pillow가 필요합니다. FBX와 LOD 검사에는 Blender 5.2가 필요합니다.

```bash
pip install numpy pillow
python tools/project.py init
python tools/run_blender.py --find
python tools/project.py new my-apt
# curtain wall이면: python tools/project.py new my-apt --template cw
```

`projects/my-apt/photos/`에 참고 사진과 선택적 GLB를 넣고 `TASK.md`를 채웁니다. 모르는 값은 비워 둡니다. 에셋 이름과 텍스처에는 실제 단지·브랜드 이름을 쓰지 않습니다.

Codex 또는 Kimi Code를 키트 루트에서 열고 `AGENTS.md`를 따르게 합니다. 모든 에이전트 명령은 프로젝트를 명시합니다.

```bash
python tools/agent.py doctor --project my-apt --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode quick --label mass --json
```

## 세 가지 검증 모드

| 모드 | 수행 내용 | 사용 시점 |
|---|---|---|
| `quick` | 일반 Python OBJ + 규격/형상 검사 | 문법·좌표·겹침 수정 반복 |
| `visual` | OBJ + 미리보기 + 사진 비교 | 매스·창·입면·재질 변경 후 |
| `final` | Blender FBX + 사진+타일+LOD+strict gate | 최종 보고·부분 수정 완료 전 |

```bash
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode visual --label windows --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode final --label final --json
```

- `PASS`: 요청한 검사가 모두 통과했습니다.
- `FAIL`: 실행된 검사가 실패했습니다.
- `INCOMPLETE`: 필수 검사나 이미지 확인이 아직 없습니다.
- `NOT_APPLICABLE`: `photo_refs.json`이 없어 사진 검사 대상이 아닙니다.
- `NOT_CHECKED`: 검증하지 않은 상태이며 PASS로 해석하면 안 됩니다.

visual/final 후에는 현재 미리보기와 표시된 비교 그림을 보고 기록합니다.

```bash
python tools/agent.py review --project my-apt --status PASS --note "reviewed final images" --json
```

## 사진과 토큰 사용

모든 사진을 원본과 확대본으로 반복해서 읽지 않습니다. 연락판을 페이지 단위로 보고 대표 사진과 불확실한 부분만 선택합니다.

```bash
python tools/agent.py photos --project my-apt --page 0 --page-size 30 --json
python tools/agent.py observe --project my-apt --photo photos/front.jpg --side front --note "36 rows; left bays hidden" --json
```

관찰값은 `work/observations.json`, 사진 해시는 `work/photo_manifest.json`에 저장됩니다. 자동 인식 결과는 실제 사진의 나무·그림자·원근 때문에 틀릴 수 있으므로 표시된 비교 그림을 확인합니다.

## 재개와 부분 수정

`work/agent_state.json`에는 생성기 해시, 마지막 gate, 다음 행동, mismatch 재시도, visual review가 저장됩니다. `STATUS.md`는 짧은 인수인계 요약입니다.

```bash
python tools/agent.py resume --project my-apt --json
```

부분 수정은 변경 전 스냅샷을 만들고, 완료 시 final gate와 변경 범위 비교를 함께 실행합니다.

```bash
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --request "change only entrance railing" --box=-5,5,-1,1,0,6 --json
# 반환된 next_action에 따라 수정 후:
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --finish --json
```

## 생성기 기본 형태

1 unit = 1 m, 지면 z=0, 정면=-Y입니다.

```python
import cs2kit as K
A = K.Atlas(size=4096, pad=16)
A.add("wall", color=(180,180,180), ctrl=(0,0,0), px=256, tile=(3.0,2.9))
mb = K.MeshBuilder(A)
mb.box(x0,x1,y0,y1,z0,z1,"wall",skip=("bottom",))
K.axbox(mb,"y",0,-1,a0,a1,0,0.2,z0,z1,"frame")
W = K.WindowSet(); W.add_face("y",0,-1,a0,a1,z0,z1,floor=f,unit=u)
l2 = K.MeshBuilder(A, split_tiles=False)
K.export_asset(NAME,LEVEL,dict(main=mb,lod1=l1,lod2=l2,gls=g,lod1_gls=g1,windows=W),A,K.out_dir_from_argv("output"))
```

LOD1은 main의 50% 미만, LOD2는 500 tris 이하입니다. main은 30k-60k를 목표로 하고 95k 초과는 경고입니다. 삼각형 수를 줄이기 위해 실제 층수·bay·창 위치를 바꾸지 않습니다.

## 도구 지도

- `check.py`: OBJ/PNG 규격·겹침·창·UV·LOD 검사
- `render.py`: Blender 없이 미리보기
- `photo_check.py`: 크기·비율·층간 비교
- `tile_compare.py`: 세부 선·색 비교, 점수는 참고용
- `sat_grid.py`: 사진 좌표·축척
- `extract_texture.py`: 사진에서 반복 재질 추출
- `facade_paint.py`, `facade_read.py`, `band_scan.py`: 층·창·도색 보조 인식
- `glb_measure.py`, `glb_slices.py`: 스캔 측정 전용
- `compare.py`: 수정 전후 변경 범위 비교
- `tools/qa/verify.py`: 공통 gate + 선택적 same-camera 회귀 검사
- `tools/facade/`, `tools/scan/`: 추가 측정·비교 도구, 각 README 참조
- `tools/samhan_facade/`: 특정 기존 생성기 전용, 새 건축물에 그대로 사용 금지

자세한 명령과 preset/socket v1 API는 `TOOLS.md`에 있습니다.

## Windows와 작은 로컬 모델

가능하면 PowerShell 7과 UTF-8을 사용합니다. 코드·YAML 키·도구 출력·파일 이름은 ASCII를 유지합니다. 네이티브 편집 도구가 있으면 사용하고, 반복 실패할 때만 `docs/agent/POWERSHELL.md`의 `put.py/edit.py` 방식을 씁니다. 셸 문자열로 소스를 조합하지 않습니다.

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임 색·밝기와 다릅니다. 창 가림은 세 지점을 표본 검사합니다. 사진 지표는 가림과 조명에 취약합니다. `facade_read.py`와 `band_scan.py`는 v1이며 실제 사진 확인이 필요합니다. FBX와 LOD는 Blender 없이 완료할 수 없고, 최종 크기·야간·알파·입구·시그니처 등록은 게임에서 확인해야 합니다.
