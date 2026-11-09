# CS2 건축 에셋 키트 — OpenCode

사진과 건축 정보로 Cities: Skylines II 건축 에셋을 만드는 키트입니다. 이 브랜치는 **OpenCode**에서 실행하며, 모델은 OpenCode의 `provider/model` 설정을 따릅니다. 공통 생성기와 검증 엔진은 그대로 유지합니다.

## 1. 준비

필요한 환경:

- Python 3.9 이상
- `numpy`, `Pillow`
- Blender 5.2 또는 `bpy` pip 모듈 — FBX 생성과 LOD 검사에 필요 (bpy는 앱 설치 없이 동작)
- OpenCode와 사용할 모델 제공자 계정 — 설치는 [OpenCode 문서](https://opencode.ai/docs/) 참조

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

`auto`는 URL 하나로 Chrome 디버그 모드를 띄우고, `projects/<name>/photos`에 바로 캡처하며, 새 프로젝트만 TASK.md를 채우고 기존 프로젝트에는 `TASK.auto.md` 제안만 남깁니다. 기존 사진은 `--overwrite` 없이는 덮어쓰지 않습니다.

`make_refs --report work/refs_report.json`을 돌리면 **어느 평면이 사진 없이 남았는지**, 사진이
부족한 이유, 평면별 해상도(px/m)를 한눈에 볼 수 있습니다. 창 폭을 읽으려면 20 px/m 이상이
필요하므로, 낮게 나오면 캡처 폭을 키워 재캡쳐해야 합니다(리샘플로 늘려도 정보는 안 늘어납니다).

### 사진 준비와 보조 도구

| 도구 | 쓰는 때 |
|---|---|
| `tools/photo_quality.py --dir photos` | 캡처·추출 사진의 블러·해상도·중복·노출 점검 ([PHOTO_QUALITY](docs/agent/PHOTO_QUALITY.md)) |
| `tools/video_frames.py` | 영상 답사에서 프레임 추출, 사진처럼 refs에 등록 ([VIDEO_FRAMES](docs/agent/VIDEO_FRAMES.md)) |
| `tools/crop_360.py` | 360/equirectangular 사진을 원근 크롭 ([PANORAMA_360](docs/agent/PANORAMA_360.md)) |
| `tools/ifc_to_glb.py --check` | IFC·CAD를 GLB로 변환하는 경로 확인 ([IFC_TO_GLB](docs/agent/IFC_TO_GLB.md)) |
| `tools/xrx_mass.py` | VR 메타(`data.xrx.json`)만으로 매스 초안 ([XRX_MASS](docs/agent/XRX_MASS.md)) |
| `tools/lod_auto.py --asset output/<asset>` | main에서 LOD1/LOD2 후보 생성 ([LOD_AUTO](docs/agent/LOD_AUTO.md)) |

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

### 다른 입력 방법

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

## 3. OpenCode로 처음 실행하기

처음 보는 사람은 아래 순서대로 하면 됩니다. 설치는 [OpenCode 문서](https://opencode.ai/docs/)를 따릅니다.

### 3.1 준비 확인

```bash
opencode --version
python -c "import numpy, PIL; print('deps OK')"
python tools/run_blender.py --find      # Blender 5.2 또는 bpy 모듈
```

세 명령이 모두 정상이면 키트를 실행할 준비가 된 것입니다.

### 3.2 모델 연결

OpenCode가 쓸 모델은 **프로젝트 `opencode.jsonc`**(권장) 또는 전역 `~/.config/opencode/opencode.json`의 `model`로 지정합니다. 형식은 `provider/model`이고, 뒤에 `#variant`를 붙일 수 있습니다.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ollama-cloud/minimax-m3.1-flash#high"
}
```

- 사용 가능한 모델과 variant는 `opencode models`로 확인합니다. 모델마다 지원하는 variant가 다릅니다(`#low`, `#medium`, `#high`, `#xhigh`, `#max`).
- 공급자 인증은 `opencode auth`(또는 공급자별 환경 변수)로 설정합니다.
- **API 키를 `TASK.md`, README, 로그, 프로젝트 파일에 저장하지 않습니다.**
- 세션 중에 모델만 바꾸고 싶으면 파일을 고친 뒤 `opencode reload`를 실행합니다.

```bash
# 한 번만 다른 모델로 실행
opencode run --model ollama-cloud/minimax-m3.1-flash#high "TASK.md를 읽고 작업을 이어가줘"
```

### 3.3 세션 시작

키트 루트에서 `opencode`를 실행하면 `AGENTS.md`를 자동으로 읽습니다. 프로젝트는 항상 명시합니다.

```bash
cd <kit-root>
opencode
```

모든 에이전트 명령은 `--project <name>`을 요구합니다(`projects/.current`에 의존하지 않음). 여러 세션을 동시에 열어도 대상이 섞이지 않습니다.

### 3.4 첫 프롬프트

아래를 그대로 복사해 붙여넣으면 됩니다.

**새 건물 시작**
```text
AGENTS.md와 projects/my-apt/TASK.md를 읽고 프로젝트를 만들어줘.
tools/agent.py의 next_action을 따라 quick/visual/final 검증을 진행하고,
require-final이 PASS일 때만 완료 보고를 해줘.
```

**중단한 작업 재개**
```text
python tools/agent.py resume --project my-apt --json 을 실행하고,
next_action이 시키는 것만 이어서 해줘. 게이트를 건너뛰지 마.
```

**사진만 있는 프로젝트**
```text
projects/my-apt/photos 를 contact sheet로 분류하고,
벽별로 창·루버·도색을 읽어서 photo_refs.json과 관측 기록을 만들어줘.
읽지 못한 부분은 추정하지 말고 unknown으로 남겨.
```

프롬프트는 짧아도 됩니다. 판단 기준은 `AGENTS.md`에 있고, 진행 상태는 `work/agent_state.json`에 남습니다. 각 단계의 결과는 `next_action`(다음 명령)으로 돌려주므로, 그 명령을 그대로 실행하면 됩니다.

### 3.5 advisor / builder 모델 지정

조언과 복잡한 조형 작업을 강한 모델에 맡기도록 모델을 세 곳에서 지정합니다.

| 파일 | 역할 | 현재 값 |
|---|---|---|
| `.opencode/plugins/advisor/index.ts` | `advisor()` 툴이 대화 전문을 넘겨 조언을 받는 모델 (`const MODEL`) | `ollama-cloud/minimax-m3.1-flash` |
| `.opencode/agents/advisor.md` | 읽기 전용 `advisor` 서브에이전트 (편집·셸 금지) | `ollama-cloud/minimax-m3.1-flash#high` |
| `.opencode/agents/builder.md` | 작업 가능한 `builder` 서브에이전트 (매스·창·루버·도색·LOD·아틀라스) | `ollama-cloud/minimax-m3.1-flash#high` |

- 파일을 고치지 않고 플러그인 옵션으로 바꿀 수도 있습니다.

```jsonc
{
  "plugins": [
    {
      "package": "./.opencode/plugins/advisor",
      "options": { "model": { "providerID": "ollama-cloud", "id": "minimax-m3.1-flash" } }
    }
  ]
}
```

- 에이전트 정의(`.opencode/agents/*.md`)를 바꾸면 `opencode reload` 또는 새 세션에서 반영됩니다. 플러그인 모델은 다음 `advisor()` 호출부터 적용됩니다.
- `builder`는 같은 모델이지만 파일 편집·셸 실행 권한이 있고, `advisor`는 조언만 합니다. 게이트 통과와 최종 보고의 책임은 실행 에이전트에 남습니다.
- 위임 기준은 `AGENTS.md`의 `Work routing`에 있습니다. 여러 수정이 얽힌 작업이나 한 번 실패한 작업은 `builder`로 넘깁니다.
- 작업별 추론 강도를 참고하려면 `python tools/agent.py deepseek-policy --project my-apt --task geometry --json`을 씁니다(정책 조회일 뿐, 모델을 바꾸지는 않습니다).

### 3.6 막혔을 때

| 증상 | 확인할 것 |
|---|---|
| 모델을 찾지 못함 | `opencode models`에 그 `provider/model`이 있는지, `opencode auth`로 키를 넣었는지 |
| `Advisor unavailable` | `.opencode/plugins/advisor/index.ts`의 `MODEL` id가 실제 모델 id인지, 키가 유효한지 |
| `builder`가 목록에 없음 | `.opencode/agents/builder.md` 존재 여부, `opencode reload` 또는 새 세션 |
| 게이트가 `INCOMPLETE` | `next_action.command`(review 명령)를 그대로 실행 |
| `agent.py requires --project` | 모든 명령에 `--project <name>` 추가 |
| 사진 판독이 이상함 | `tools/photo_quality.py`로 품질 확인, 캡처 해상도(px/m) 확인 |

```bash
python tools/agent.py doctor --project my-apt --json      # 환경 점검
python tools/agent.py resume --project my-apt --json      # 상태 요약
```

## 4. 검증과 완료 기준

| 모드 | 검증 내용 | 사용 시점 |
|---|---|---|
| `quick` | OBJ 생성, 규격·형상 검사 | 문법·좌표·겹침 수정 반복 |
| `visual` | 미리보기, 사진 비교 | 매스·창·입면·재질 변경 후 |
| `final` | FBX, 사진·타일·LOD, strict gate | 최종 보고와 부분 수정 완료 전 |

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

JSON의 `next_action`을 따르고, 상세 로그는 지정된 파일이 필요할 때만 읽습니다. visual/final 후에는 `next_action`에 열거된 현재 미리보기와 비교 이미지를 확인하고, 같은 artifact를 지정해 결과를 기록합니다.

```bash
python tools/agent.py review --project my-apt --status PASS --note "reviewed final images" --artifact previews/<asset>.png --json
```

사진 검사가 있으면 photo sheet도 `--artifact`로 지정합니다. 일부만 본 `PARTIAL`은 PASS가 아니며, 이미지를 볼 수 없는 모델은 `NEEDS_HUMAN_REVIEW`를 사용합니다.

이 브랜치에는 자동 종료 훅이 없으므로, 외부 실행기 또는 에이전트가 완료 전에 최종 상태를 확인합니다.

```bash
python tools/agent.py require-final --project my-apt --json
```

final gate, FBX, visual review가 모두 PASS일 때만 PASS를 반환합니다. 상태가 없으면 `NOT_CHECKED`, 실패는 `FAIL`, 미완료 review는 `INCOMPLETE`입니다.

## 5. 사진, 결과, 재개

연락판은 사진 분류에만 사용하고, 창틀·난간·루버 측정은 벽 또는 세부 crop을 사용합니다. 관찰한 사진은 해시로 기록해 같은 이미지를 반복해서 읽지 않습니다.

```bash
python tools/agent.py photos --project my-apt --page 0 --page-size 16 --json
python tools/agent.py observe --project my-apt --photo photos/front.jpg --side front --note "36 floors" --json
python tools/agent.py vision --project my-apt --photo photos/front.jpg --box=100,200,1200,1400 --wall-id main:front --json
```

사람·번호판 등 민감한 영역은 `--redact=x0,y0,x1,y1`로 가립니다. 원본 사진은 바뀌지 않고 결과는 `previews/`에 저장됩니다. 키트는 사진을 자동으로 외부 업로드하지 않으므로, 전송 전에 파생 이미지를 직접 확인해야 합니다.

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

부분 수정 완료 시 final gate와 outside-scope 비교를 함께 실행합니다. 하나라도 실패하면 PASS로 보고하지 않습니다.

## 6. 생성과 편집 규칙

- 1 unit = 1 m, 지면 `z=0`, 정면은 `-Y`입니다.
- 생성기는 `import cs2kit as K`로 `Atlas`, `MeshBuilder`, `WindowSet`, `export_asset`을 사용합니다.
- LOD1은 main의 50% 미만, LOD2는 500 tris 이하입니다.
- main은 30k–60k tris를 목표로 하며 95k 초과는 경고입니다.
- 삼각형 수를 줄이기 위해 실제 층수, bay, 창 위치를 바꾸지 않습니다.
- OpenCode의 네이티브 edit/write/patch 도구를 우선 사용하고, 셸 문자열로 소스를 조합하지 않습니다.
- 코드·YAML 키·도구 출력·파일 이름은 ASCII를 사용합니다.

Windows에서는 PowerShell 7과 UTF-8을 권장합니다. 네이티브 편집이 반복해서 실패할 때만 [PowerShell 편집 fallback](docs/agent/POWERSHELL.md)을 사용합니다.

## 7. 더 보기

- [OpenCode 문서](https://opencode.ai/docs/)
- [설치와 업그레이드](INSTALL.md)
- [문서 지도](docs/README.md)
- [DeepSeek/Codex 연결 기록](docs/agent/DEEPSEEK.md) — 과거 실행기 참고용
- [전체 작업 절차](docs/agent/WORKFLOW.md)
- [도구와 API](TOOLS.md)
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

미리보기는 단순 정사영 렌더라 게임의 색·밝기와 다릅니다. 사진 지표는 나무·그림자·원근에 취약하며, `facade_read.py`와 `band_scan.py`는 실제 사진 확인이 필요한 v1입니다. FBX와 LOD는 Blender 없이 완료할 수 없습니다. 최종 크기, 창, 알파, 야간 조명, 정면, 입구, 시그니처 등록은 게임에서 확인하세요. 선택한 모델의 실제 작업 완료율·토큰·시간은 모델 연결 후 별도로 측정해야 합니다.
