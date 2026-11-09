# CS2 건축 에셋 키트 — Claude Code

사진, GLB 스캔, 자연어 설명으로 Cities: Skylines II 건축 에셋을 만드는 키트입니다. 이 브랜치는 **Claude Code 전용 스킬과 훅**을 제공하며, 모든 작업이 같은 검증 엔진과 상태 파일을 공유합니다.

## 1. 준비

필요한 환경:

- Python 3.9 이상
- `numpy`, `Pillow`
- Blender 5.2 또는 `bpy` pip 모듈 — FBX 생성과 LOD 검사에 필요 (bpy는 앱 설치 없이 동작)

키트 루트에서 설치와 초기 설정을 실행합니다.

```bash
pip install numpy pillow
python tools/project.py init
python tools/run_blender.py --find
```

Blender를 자동으로 찾지 못하면 `INSTALL.md`의 수동 경로 설정을 참고하세요. Blender 앱 없이 쓰려면 전용 venv에 `bpy`를 설치합니다(Blender 5.0 → Python 3.11).

```bash
uv venv .venv-bpy --python 3.11
uv pip install --python .venv-bpy bpy
python tools/run_blender.py --find
```

## 2. 새 프로젝트 만들기

```bash
python tools/project.py new my-apt
# 커튼월 건축물:
python tools/project.py new my-apt --template cw
# 상가·학교·비정형 볼륨:
python tools/project.py new my-building --template generic
```

이제 `projects/my-apt/`에서 다음을 준비합니다.

1. `photos/`에 참고 사진과 선택적 GLB를 넣습니다.
2. `TASK.md`에 아는 정보를 적고, 모르는 값은 비워 둡니다.
3. 실제 단지 이름·브랜드·로고는 에셋 이름과 텍스처에 사용하지 않습니다.

### 작업 방법 선택

입력이 무엇이냐에 따라 시작점이 다릅니다. 아래 세 가지가 기본 경로입니다.

| 방법 | 준비물 | 강점 | 시작 명령 |
|---|---|---|---|
| 1. 네이버 VR + GLB | 투어 URL, 선택적 `3dview.glb` | 여러 동·다면 사진, camera·평면 메타, 매스 자동 재구성 | `capture/naver_vr.py auto` → `agent.py glb-mass` |
| 2. 로드뷰·직접 촬영 | 정면·모서리·디테일 3~8장 | 실제 색·재질·창·저층부·입구 | `agent.py evidence`, `agent.py observe` |
| 3. 자연어 + 사진 | 시대·유형·층수 설명 + 사진 | 빠른 스타일·층수·창 계열 초안 | `tools/brief.py` |

세 방법 모두 같은 quick/visual/final 게이트를 통과해야 합니다. 사진 증거가 없는 항목은 `NOT_APPLICABLE`로 남고 PASS로 바뀌지 않습니다.

### GLB가 있으면 매스부터 자동 재구성

전체 가로·세로·높이만 참고하지 않고, 여러 높이에서 자른 외곽선을 단순화해 L자·각진 평면과 단차 볼륨을 `generic_spec.json`으로 만듭니다.

```bash
python tools/project.py new my-building --template generic
python tools/agent.py glb-mass --project my-building --json -- photos/scan.glb --list
python tools/agent.py glb-mass --project my-building --json -- photos/scan.glb --mesh-index 3 --out generic_spec.json --force
```

`previews/glb/shape.png`와 `shape_report.json`을 확인한 뒤 생성된 벽 ID에 창·입면 부품을 연결합니다. `--levels 6,12`로 확인된 높이 경계를 직접 지정할 수도 있습니다. `--force`는 기존 spec의 창과 부품까지 바꾸므로 입면 작업 후에는 다른 출력 파일을 사용하세요. 원본 GLB 메시·텍스처는 에셋에 복사하지 않습니다. 자세한 절차는 [GLB 매스 재구성](docs/agent/GLB_MASS.md)을 참고하세요.

### 네이버 VR 캡처와 도색용 photo_refs

`capture/naver_vr.py`는 동별 다방면 사진과 camera·평면 메타데이터를 저장합니다. `make_refs`는 최대 20°·3 m 차이를 한 벽으로 합치지 않고, 실제로 같은 평면인 연속 변만 골라 정확한 네 모서리를 만듭니다. 벽마다 정면성·보이는 높이·해상도가 가장 좋은 사진 한 장을 기본 선택합니다.

```bash
python capture/naver_vr.py auto --url https://fin.land.naver.com/complexes/<번호>/tour --project <name> --make-refs
python capture/naver_vr.py run --dongs 101 --fit-wall --angles 4
python capture/naver_vr.py make_refs --dir capture/out/<complex> --dongs 101 --prefix photos/ --debug
python tools/band_scan.py --refs photo_refs.json --name 101_p1_1 --fh 2.9 --out previews/paint_grid
```

`make_refs --report work/refs_report.json`을 돌리면 **어느 평면이 사진 없이 남았는지**, 사진이
부족한 이유, 평면별 해상도(px/m)를 한눈에 볼 수 있습니다. 창 폭을 읽으려면 20 px/m 이상이
필요하므로, 낮게 나오면 캡처 폭을 키워 재캡쳐해야 합니다(리샘플로 늘려도 정보는 안 늘어납니다).

`auto`는 URL 하나로 Chrome 디버그 모드를 띄우고, `projects/<name>/photos`에 바로 캡처하며, 새 프로젝트만 TASK.md를 채우고 기존 프로젝트에는 `TASK.auto.md` 제안만 남깁니다. 기존 사진은 `--overwrite` 없이는 덮어쓰지 않습니다.

사진 캡처 없이 `data.xrx.json`만 있으면 동별 매스 초안을 만들 수 있습니다.

```bash
python tools/xrx_mass.py --project my-apt --xrx photos/data.xrx.json --dongs 101 --force --json
```

정면·좌표 규칙과 한계는 [네이버 VR 메타데이터 매스](docs/agent/XRX_MASS.md)를 참고하세요.

`paint_include`와 `paint_exclude`로 나무·간판·그림자 등을 정규화된 벽 U/V 좌표로 제외할 수 있습니다. 창은 자동 마스크에서 제외하고, 미확정 셀은 임의 색으로 채우지 않고 `cell_id=-1`로 남겨 기본 벽 재질을 유지합니다. `_mask.png`와 refs 디버그 이미지를 반드시 확인하세요. 캡처 재개, camera 필드, 성능 선택지는 [네이버 VR 캡처와 도색 refs](docs/agent/NAVER_VR.md)에 정리했습니다.

색을 뽑을 때는 그늘을 먼저 보정합니다. 그늘진 벽도 같은 재질이므로 밝은 흰 벽을 기준으로
블록별 배율을 만들어야 팔레트가 어두워지지 않습니다.

```bash
python tools/shadow_norm.py --project my-building \
  --refs photo_refs.json --out-refs photo_refs_lit.json
```

`--refs`는 refs가 가리키는 모든 사진을 한꺼번에 보정하고 **경로가 갱신된 새 refs 파일**을
만듭니다(원본 사진은 그대로). 도색·색 측정에는 이 파일을, 형상에는 원본 refs를 씁니다.
자세한 내용은 [그림자 정규화](docs/agent/SHADOW_NORM.md)를 참고하세요.

### 사진 평면을 모델 벽에 붙이기

캡처 사진은 자기 평면(장면 미터)을, 모델은 자기 벽(모델 미터)을 알고 있어서 둘을 맞춰야 창 열을 놓을 수 있습니다.

```bash
python tools/photo_plane_map.py --project my-building \
  --meta photos/<dong>_meta.json --mass generic_spec.json --refs photo_refs.json
python tools/facade_read.py --project my-building --refs photo_refs.json \
  --plane-map work/plane_to_edge.json --table
python tools/qa/plane_compare.py --project my-building --asset output/<asset> \
  --meta photos/<dong>_meta.json --refs photo_refs.json --plane-map work/plane_to_edge.json
```

- `photo_plane_map`: 사진 평면마다 **덮는 모델 벽·미터 오프셋·좌우 반전·실제 해상도(px/m)**를 알려줍니다.
- `facade_read`: 평면 사진에서 창 열을 **미터로** 읽고, 루버 밴드를 찾고, 생성기용 표를 씁니다.
- `plane_compare`: 같은 평면을 사진/모델로 나란히 비교해 입면이 맞는지 봅니다.

해상도가 낮으면(창 폭 측정에 20 px/m 미만) 그 사진으로는 창 폭을 읽을 수 없으니 다시 캡쳐해야 합니다.
자세한 내용은 [사진 평면 → 모델 벽 매핑](docs/agent/PHOTO_PLANE_MAP.md)을 참고하세요.

### GLB 없이 사진으로 작업

`tools/evidence.py`는 사진과 관찰값을 벽에 연결합니다. 사진의 촬영 방향, 가림, 사용 가능한 측정 항목, 출처 해시, 신뢰도를 기록하고, 창은 전체 이미지 픽셀 대신 벽 기준 U/V 좌표로 저장합니다.

```bash
python tools/agent.py evidence --project my-apt --json -- photo \
  --photo photos/front.jpg --photo-id front_main --wall main:front \
  --view frontal --use floors,bays,color --confidence high --note "full wall"

python tools/agent.py evidence --project my-apt --json -- feature \
  --wall main:front --kind window --u 0.12,0.19 --v 0.20,0.78 \
  --floor 7 --photo-id front_main --confidence high --note "measured edges"

python tools/agent.py evidence --project my-apt --json -- validate
```

기록은 `work/photo_evidence.json`에 저장됩니다. 저신뢰도 측정값은 `estimated`로 표시해야 합니다.

`photo_refs.json`의 벽 항목은 다음을 지원합니다.

- `wall_id`: `manifest.metadata.walls`의 실제 벽과 연결
- `size_m`: 네 모서리 안 벽의 실제 폭·높이
- `box`: 해당 벽만 렌더하는 generator 좌표 영역
- `yaw_deg`: 필요한 경우 카메라 각도 직접 지정
- `confidence`, `occluded`: 판정 신뢰도와 가림 기록

벽의 `normal_deg`에서 비축정렬 벽의 카메라 yaw를 계산하고, pivot shift를 적용합니다. 따라서 돌출되거나 들어간 벽도 전체 건축물 크기가 아닌 실제 벽 영역으로 비교합니다. 저신뢰도 사진이나 약한 패턴은 자동 층수 변경 지시를 만들지 않습니다.

단독 정면 사진으로 깊이와 가려진 형상을 확정할 수는 없습니다. 이런 값은 추정치로 남기고, 가능하면 사선 사진이나 다른 각도로 검증합니다.

### 자연어 설명과 스타일

층수·시대·유형·창 계열처럼 반복되는 결정은 짧은 설명으로 초안을 만들 수 있습니다.

```bash
python tools/brief.py --project my-apt --text "2020년대 타워형 아파트 36층, 확장형, 입면분할창" --json
python tools/style_catalog.py --project my-apt --json
```

`brief.py`는 `templates/styles/*.yaml`에서 스타일을 고르고 `building_brief.yaml`을 만듭니다. 팔레트, 창 치수, 띠·스팬드럴, 야간 점등 정책이 여기에 들어가며, 생성기는 `templates/facade_style.py`로 같은 값을 읽습니다.

`brief.py`는 결정론적 파서이지 LLM 호출이 아닙니다. 문장에 없는 값과 층수 기본값은 `estimated`로 표시하고, 자연어만으로는 평면 형상·베이 수·안 보이는 면을 확정하지 않습니다. 매스는 GLB나 실측 치수로 먼저 잡고, 창 위치·입구·저층부는 사진과 `work/photo_evidence.json`으로 보정합니다.

### 그 외 입력 방법

| 입력 | 지원 | 용도와 한계 |
|---|---|---|
| GLB 스캔만 (사진 없이) | 지원 | `glb-mass`로 매스·평면·단차를 잡고 스타일 프리셋으로 입면을 채웁니다. 사진 대조는 `NOT_APPLICABLE`입니다. |
| Naver VR 메타만 (사진 없이) | 부분 지원 | `tools/xrx_mass.py`로 동별 footprint·높이 매스 초안을 만듭니다. 입면 근거는 없습니다. |
| 위성·평면 이미지 | 지원 | `photo_refs.json`의 `satellite`로 지붕 형상과 가로·세로 비율을 비교합니다. 입면 증거는 아닙니다. |
| 도면·치수 텍스트 | 지원 | `TASK.md`와 `generic_spec.json`에 직접 적습니다. 창·재질은 사진이나 스타일로 보완합니다. |
| 자연어만 (사진 없음) | 부분 지원 | 스타일·층수 초안은 나오지만 베이·입구·색은 추정입니다. 사진 게이트는 비어 있습니다. |
| 드론·360 사진 | 부분 지원 | 드론 사진은 일반 사진처럼 씁니다. 360/equirectangular는 `tools/crop_360.py`로 원근 크롭한 뒤 넣습니다. |
| IFC·CAD·BIM | 변환 필요 | `tools/ifc_to_glb.py`로 변환 경로를 확인하고 GLB로 내보낸 뒤 `glb-mass`를 씁니다. |
| 다른 3D 에셋 | 매스 참고만 | GLB로 가져와 매스만 단순화합니다. 원본 메시·텍스처는 에셋에 복사하지 않습니다. |
| 영상 워크스루 | 부분 지원 | `tools/video_frames.py`로 프레임을 추출해 사진으로 넣습니다. 자동 정합은 없습니다. |

드론·360 사진은 원근 크롭 후 일반 사진과 같은 경로를 씁니다.

```bash
python tools/crop_360.py --project my-apt --image photos/pano.jpg \
  --yaws 0,90,180,270 --fov 90 --out photos/crops
```

360 사진의 yaw 규칙과 한계는 [360 사진 원근 크롭](docs/agent/PANORAMA_360.md)을 참고하세요.

영상은 프레임으로 뽑아 같은 사진 경로에 넣습니다.

```bash
python tools/video_frames.py --project my-apt --video photos/walk.mp4 \
  --every 2.0 --width 1600 --out photos/frames
```

ffmpeg가 없으면 `pip install imageio-ffmpeg`로 설치합니다. 구간·장수·품질 옵션은 [영상 프레임 추출](docs/agent/VIDEO_FRAMES.md)을 참고하세요.

캡처·추출한 사진은 입면 작업 전에 품질을 점검합니다.

```bash
python tools/photo_quality.py --project my-apt --dir photos --json
```

블러·해상도·중복·노출 기준은 [사진 품질 게이트](docs/agent/PHOTO_QUALITY.md)를 참고하세요. 색을 추출할 때는 그림자 부분을 흰 벽 기준으로 보정해야 합니다.

```bash
python tools/shadow_norm.py --image photos/wall.png --out photos/wall_lit.png --block 64
```

`shadow_norm`는 밝은 흰 벽을 기준으로 블록별 배율을 만들어, 그늘진 벽도 같은 재질 색으로 측정되게 합니다.

IFC·CAD는 GLB로 변환한 뒤 매스를 만듭니다.

```bash
python tools/ifc_to_glb.py --check --json
python tools/ifc_to_glb.py --plan
```

BlenderBIM/Bonsai, IfcConvert, FreeCAD 경로와 변환 후 점검 항목은 [IFC에서 GLB로](docs/agent/IFC_TO_GLB.md)를 참고하세요.

### 상가·학교·비정형 건축물

`--template generic`은 아파트 전용 프리셋 대신 **여러 볼륨과 벽 단위 부품을 조합**합니다. `generic_spec.json`에 다음을 입력합니다.

- 임의의 단순 다각형 footprint, 볼륨별 높이와 시작 높이
- 벽별 `window_band`, `shopfront`, `louver_zone`, `railing_zone`
- `sign_slot`, `roof_equipment`, `covered_link`, `entrance_canopy`

`build_volume_spec`이 같은 데이터를 FULL/SIMPLIFY_TRIM/LOD_CULL로 생성하므로 LOD를 따로 설계하지 않아도 됩니다. LOD2에서도 여러 볼륨의 실루엣을 유지합니다.

생성된 벽은 ID, 길이, 높이, 법선, render box를 `manifest.metadata.walls`에 기록하므로 사진 검사에 그대로 연결할 수 있습니다. 임의 다각형 지붕은 삼각형으로 분할하고, OBJ는 삼각형과 사각형의 꼭짓점 UV를 모두 지원합니다.

`example_generic_cs2.py`와 `templates/generic_spec.example.json`은 본관과 각진 체육관을 조합한 합성 예제입니다. 이 예제의 quick, FBX, 사진, 타일, LOD, visual review를 모두 PASS로 확인했습니다. 곡면이나 매우 복잡한 접합은 여전히 custom generator가 필요합니다.

## 3. Claude Code로 실행

### 3-1. 시작하기

1. [Claude Code](https://docs.claude.com/en/docs/claude-code/overview)를 설치하고 로그인합니다(`claude` 실행 후 안내에 따름).
2. **키트 루트**(이 README가 있는 폴더)에서 실행합니다. 루트에서 열어야 `CLAUDE.md`, `AGENTS.md`, `.claude/` 설정이 자동으로 읽힙니다.

```bash
cd <키트 루트>
claude
```

처음 열면 `CLAUDE.md`의 규칙(한국어 응답, 모델 분담, 완료 조건)이 적용됩니다. `.claude/settings.json`이 `python tools/...` 실행을 미리 허용하므로 검사 명령마다 승인을 묻지 않습니다. 그 밖의 명령은 평소처럼 승인을 묻습니다.

### 3-2. 모델 설정

세션 안에서 `/model`을 입력하면 모델 선택 목록이 나오고, 고른 모델이 새 세션의 기본값으로 저장됩니다.

```text
/model
```

시작할 때 지정할 수도 있습니다.

```bash
claude --model <모델 이름>
```

권장 설정(필수 아님): 메인 Sonnet 5.5 + advisor Opus 5.5. 메인 모델이 설계·코드 편집·사진 판단을 직접 하고, 어려운 갈림길에서만 advisor(Opus 5.5)에게 상의합니다.

| 역할 | 권장 |
|---|---|
| 메인(설계, 디버깅, 코드 편집, 사진·렌더 그림 판단) | Sonnet 5.5 |
| advisor(설계 확정 직전, 반복 오류) | Opus 5.5 |
| 파일 탐색, 긴 로그 명령 실행 | `CLAUDE.md`가 서브에이전트(Explore, runner)에 맡기도록 지시하므로 따로 설정할 필요 없음 |

이 키트의 지침과 스킬은 위 구성을 기준으로 다듬었습니다. 다른 모델을 지정해도 동작은 하지만, 사진 판독·형태 판단·수정 정확도 같은 결과 품질이 최적에 못 미칠 수 있습니다.

사진 비교가 핵심이라 **이미지 입력이 되는 모델**이 필요합니다. 입력이 안 되면 키트는 `NEEDS_HUMAN_REVIEW`로 멈추고 임의로 판단하지 않습니다.

### 3-3. Advisor 설정

advisor는 메인 모델이 막히거나 설계를 확정하기 전에 상의하는 더 강한 검토 모델입니다. 세션에서 켭니다.

```text
/advisor
```

모델 목록에서 Opus 5.5를 고르는 것을 권장합니다(메인보다 강한 모델이면 무방합니다). 한 번 설정하면 이후 세션에도 유지됩니다. 이 프로젝트에서는 다음 두 경우에만 advisor를 부르도록 `CLAUDE.md`에 정해 두었습니다.

- 설계·접근을 확정하기 직전(사진 분석 끝, 덩어리 하나 끝, 사용자 승인이 필요한 수정을 제안하기 전)
- 같은 오류를 두 번 고쳐도 안 풀릴 때

그 외에는 호출하지 않으니 비용이 크게 늘지 않습니다.

### 3-4. 프롬프트 입력 방법

작업 내용은 두 곳으로 전달합니다.

**① `TASK.md` — 건축물 정보(기본)**: `projects/<이름>/TASK.md`에 건축물 이름, 층수, 사진 위치, 특징을 적습니다. `/build`는 이 파일을 읽고 만듭니다. 항목은 [2. 새 프로젝트 만들기](#2-새-프로젝트-만들기)와 `templates/`를 참고하세요.

**② 프롬프트 — 추가 지시**: 스킬 뒤에 자연어로 붙입니다.

```text
/build
/build 옥상 물탱크 디테일 강조
/fix 2층 상가 간판 띠를 0.4m 낮춰줘
/style-research 2020년대 판상형 아파트 30층
```

일반 대화로도 요청할 수 있습니다. 예: `이 건물 사진 보고 층수 다시 확인해줘`. 파일 경로는 `@projects/<이름>/photos/front.jpg`처럼 `@`로 붙이면 사진을 직접 읽습니다. 이미지는 드래그해서 넣어도 됩니다. 단, 원본 사진은 수정·이동·복사하지 않는다는 규칙이 있으므로 `photos/` 안의 파일을 그대로 참조하게 하세요.

입력 팁:

- 수치와 위치를 구체적으로: "발코니가 작아 보여" 보다 "3~12층 발코니 깊이를 1.2m로".
- 한 번에 한 가지 변경을 요청하면 `/fix`가 범위를 좁혀 검증합니다.
- 대화 중간에 끊겼으면 `/resume`으로 저장된 `next_action`부터 이어갑니다.
- 키트가 모델 자리를 추정값으로 채운 항목은 YAML에 `# estimated`로 표시되고 최종 보고에 나열됩니다. 틀린 값은 프롬프트로 바로잡아 주세요.

### 3-5. 스킬 사용

```text
/build
```

추가 요청도 전달할 수 있습니다.

```text
/build 옥상 물탱크 디테일 강조
```

사용 가능한 스킬:

- `/build`: 전체 제작
- `/resume`: 저장된 다음 행동부터 재개
- `/photo-refs`: 사진 모서리 좌표 생성·검증
- `/photo-observe`: 벽 사진을 확대·체크리스트로 읽고 측정값과 교차 확인 후 기록
- `/fix <요청>`: 범위 수정, 최종 검증, 변경 범위 비교
- `/style-research <건물 설명>`: 자연어 건물 유형을 조사해 파사드 스타일 YAML 초안과 브리프를 만들고, 사용자 검토에서 멈춤

스킬은 `tools/agent.py`를 호출합니다. 별도 검사기나 중복된 모델링 규칙을 두지 않습니다.

## 4. 검증과 완료 기준

| 모드 | 검증 내용 | 사용 시점 |
|---|---|---|
| `quick` | OBJ 생성, 규격·형상 검사 | 문법·좌표·겹침 수정 반복 |
| `visual` | 미리보기, 사진 비교 | 매스·창·입면·재질 변경 후 |
| `final` | FBX, 사진·타일·LOD, strict gate | 최종 보고와 부분 수정 완료 전 |

직접 실행할 때는 프로젝트와 생성기를 명시합니다.

```bash
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode quick --label mass --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode visual --label windows --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode final --label final --json
```

결과 상태:

- `PASS`: 요청한 검사가 모두 통과했습니다.
- `FAIL`: 실행된 검사가 실패했습니다.
- `INCOMPLETE`: 필수 검사나 이미지 확인이 아직 없습니다.
- `NOT_APPLICABLE`: `photo_refs.json`이 없어 사진 검사 대상이 아닙니다.
- `NOT_CHECKED`: 아직 검증하지 않았으며 PASS로 해석하면 안 됩니다.

visual/final 후에는 `next_action`에 열거된 현재 미리보기와 비교 이미지를 확인하고, 같은 artifact를 지정해 결과를 기록합니다.

```bash
python tools/agent.py review --project my-apt --status PASS --note "reviewed final images" --artifact previews/<asset>.png --json
```

사진 검사가 있으면 photo sheet도 `--artifact`로 지정합니다. 일부만 본 `PARTIAL`은 PASS가 아니며, 이미지를 볼 수 없으면 `NEEDS_HUMAN_REVIEW`를 사용합니다.

LOD 후보가 필요하면 main `.blend`에서 LOD1/LOD2를 만들고 빠른 구멍 검사를 실행합니다.

```bash
python tools/lod_auto.py --project my-apt --asset output/<asset> --check --json
```

`--check`는 16시점 quick 검사입니다. 보고 전에는 `--check-full` 또는 `tools/qa/lod_check.py` 전체 검사를 사용하세요. 자세한 내용은 [LOD 자동 후보](docs/agent/LOD_AUTO.md)를 참고하세요.

Stop 훅은 final/fix 단계에서 PASS가 아닌 채 종료하면 저장된 다음 행동을 알려 줍니다. 실패 원인은 그대로 보고해야 합니다.

## 5. 사진, 결과, 재개

사진은 연락판 페이지 → 대표 사진 → 필요한 영역 확대 순서로 확인합니다. 모든 원본과 확대를 반복해서 읽지 않습니다.

```bash
python tools/agent.py photos --project my-apt --page 0 --page-size 16 --json
python tools/agent.py observe --project my-apt --photo photos/front.jpg --side front --note "36 floors" --json
```

주요 파일:

- `output/<에셋>/`: FBX와 텍스처
- `previews/`: 미리보기와 사진 비교
- `work/agent_state.json`: 마지막 검증, 생성기 해시, 다음 행동
- `work/observations.json`: 사진 관찰 기록
- `STATUS.md`: 짧은 인수인계 요약

재개와 부분 수정:

```bash
python tools/agent.py resume --project my-apt --json
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --request "change only entrance railing" --box=-5,5,-1,1,0,6 --json
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --finish --json
```

`/fix`를 사용하면 이 절차를 자동으로 안내합니다. final gate나 변경 범위 비교가 실패하면 PASS로 보고하지 않습니다.

## 6. 생성 규칙

- 1 unit = 1 m, 지면 `z=0`, 정면은 `-Y`입니다.
- 생성기는 `import cs2kit as K`로 `Atlas`, `MeshBuilder`, `WindowSet`, `export_asset`을 사용합니다.
- LOD1은 main의 50% 미만, LOD2는 500 tris 이하입니다.
- main은 30k–60k tris를 목표로 하며 95k 초과는 경고입니다.
- 삼각형 수를 줄이기 위해 실제 층수, bay, 창 위치를 바꾸지 않습니다.
- 사용자가 작성한 `photo_refs.json`은 수정하지 않습니다.

## 7. 더 보기

- [설치와 업그레이드](INSTALL.md)
- [문서 지도](docs/README.md)
- [전체 작업 절차](docs/agent/WORKFLOW.md)
- [도구와 API](TOOLS_CLAUDE.md)
- [상세 모델링 지침](docs/agent/MODELING.md)
- [측정 기반 파사드](docs/agent/FACADE_MEASURED.md)
- [입면 작업 노하우](docs/agent/FACADE_KNOWHOW.md)
- [GLB 기반 매스 재구성](docs/agent/GLB_MASS.md)
- [네이버 VR 캡처와 도색 refs](docs/agent/NAVER_VR.md)
- [GLB 없는 사진 증거 작업](docs/agent/PHOTO_ONLY.md)
- [파사드 스타일과 브리프](templates/styles/README.md)
- [360 사진 원근 크롭](docs/agent/PANORAMA_360.md)
- [영상 프레임 추출](docs/agent/VIDEO_FRAMES.md)
- [사진 품질 게이트](docs/agent/PHOTO_QUALITY.md)
- [LOD 자동 후보](docs/agent/LOD_AUTO.md)
- [IFC에서 GLB로](docs/agent/IFC_TO_GLB.md)
- [네이버 VR 메타데이터 매스](docs/agent/XRX_MASS.md)
- [상가·학교·비정형 볼륨](docs/agent/VOLUMES.md)
- [메모리 범위](docs/agent/MEMORY.md)

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임의 색·밝기와 다릅니다. 사진 지표는 나무·그림자·원근에 취약하며, `facade_read.py`와 `band_scan.py`는 실제 사진 확인이 필요한 v1입니다. FBX와 LOD는 Blender 없이 완료할 수 없습니다. 최종 크기, 창, 알파, 야간 조명, 정면, 입구, 시그니처 등록은 게임에서 확인하세요.
