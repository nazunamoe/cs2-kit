# CS2 건축 에셋 키트 — OpenCode

사진과 건축 정보로 Cities: Skylines II 건축 에셋을 만드는 키트입니다. 이 브랜치는 **OpenCode**에서 실행하며, 모델은 OpenCode의 `provider/model` 설정을 따릅니다. 공통 생성기와 검증 엔진은 그대로 유지합니다.

## 1. 준비

필요한 환경:

- Python 3.9 이상
- `numpy`, `Pillow`
- Blender 5.2 — FBX 생성과 최종 LOD 검사에 필요
- OpenCode와 사용할 모델 제공자 계정 — 설치는 [OpenCode 문서](https://opencode.ai/docs/) 참조

키트 루트에서 설치와 초기 설정을 실행합니다.

```bash
pip install numpy pillow
python tools/project.py init
python tools/run_blender.py --find
```

Blender를 자동으로 찾지 못하면 `INSTALL.md`의 수동 경로 설정을 참고하세요.

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
python capture/naver_vr.py run --dongs 101 --fit-wall --angles 4
python capture/naver_vr.py make_refs --dir capture/out/<complex> --dongs 101 --prefix photos/ --debug
python tools/band_scan.py --refs photo_refs.json --name 101_p1_1 --fh 2.9 --out previews/paint_grid
```

`make_refs --report work/refs_report.json`을 돌리면 **어느 평면이 사진 없이 남았는지**, 사진이
부족한 이유, 평면별 해상도(px/m)를 한눈에 볼 수 있습니다. 창 폭을 읽으려면 20 px/m 이상이
필요하므로, 낮게 나오면 캡처 폭을 키워 재캡쳐해야 합니다(리샘플로 늘려도 정보는 안 늘어납니다).

`paint_include`와 `paint_exclude`로 나무·간판·그림자 등을 정규화된 벽 U/V 좌표로 제외할 수 있습니다. 창은 자동 마스크에서 제외하고, 미확정 셀은 임의 색으로 채우지 않고 `cell_id=-1`로 남겨 기본 벽 재질을 유지합니다. `_mask.png`와 refs 디버그 이미지를 반드시 확인하세요. 캡처 재개, camera 필드, 성능 선택지는 [네이버 VR 캡처와 도색 refs](docs/agent/NAVER_VR.md)에 정리했습니다.

### 사진 평면을 모델 벽에 붙이기

캡처 사진은 자기 평면(장면 미터)을, 모델은 자기 벽(모델 미터)을 알고 있어서 둘을 맞춰야 창 열을 놓을 수 있습니다.

```bash
python tools/photo_plane_map.py --project my-building \
  --meta photos/<dong>_meta.json --mass generic_spec.json --refs photo_refs.json
```

사진 평면마다 **덮는 모델 벽·미터 오프셋·좌우 반전 여부·실제 해상도(px/m)**를 알려줍니다. 해상도가 낮으면(창 폭 측정에 20 px/m 미만) 그 사진으로는 창 폭을 읽을 수 없으니 다시 캡쳐해야 합니다. 자세한 내용은 [사진 평면 → 모델 벽 매핑](docs/agent/PHOTO_PLANE_MAP.md)을 참고하세요.

## 3. OpenCode로 실행

OpenCode의 모델은 프로젝트 `opencode.jsonc` 또는 전역 `~/.config/opencode/opencode.json`의 `model`로 지정합니다.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ollama-cloud/deepseek-v4.1-flash:1017"
}
```

API 키는 `TASK.md`, README, 로그 등 프로젝트 파일에 저장하지 않습니다. 공급자 키는 OpenCode 설정이나 환경 변수로 관리합니다.

키트 루트에서 OpenCode를 열고 `AGENTS.md`를 따르게 합니다. 첫 환경 점검:

```bash
python tools/agent.py doctor --project my-apt --json
```

첫 요청 예시:

```text
AGENTS.md와 projects/my-apt/TASK.md를 읽고 프로젝트를 만들어줘.
tools/agent.py의 next_action을 따라 quick/visual/final 검증을 진행하고,
require-final이 PASS일 때만 완료 보고를 해줘.
```

작업별 추론 강도를 조회할 수 있습니다.

```bash
python tools/agent.py deepseek-policy --project my-apt --task data --json
python tools/agent.py deepseek-policy --project my-apt --task geometry --json
python tools/agent.py deepseek-policy --project my-apt --task vision --json
```

- `data`: non-thinking, 허용된 데이터만 수정
- `edit`: low, 오류 그룹 하나만 수정
- `geometry`, `vision`, `review`: high
- OpenCode에서는 같은 의도를 모델 variant로 지정할 수 있습니다: `provider/model#low`, `#high`, `#max`
- 긴 문서와 로그를 모두 넣지 말고 `--brief`와 `next_action`을 사용

모델을 작업별로 나누려면 OpenCode의 `agents`, `commands`, `subagent`를 사용합니다. 이 브랜치에는 복잡한 작업에서 강한 모델의 자문을 받는 `advisor` 도구(`.opencode/plugins/advisor/`)와 읽기 전용 `advisor` 서브에이전트(`.opencode/agents/advisor.md`)가 포함되어 있습니다.

모든 에이전트 명령은 `--project`를 명시합니다. `projects/.current`에 의존하지 않으므로 여러 세션에서도 작업 대상을 명확히 유지할 수 있습니다.

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
- [DeepSeek/Codex 연결 기록](docs/agent/DEEPSEEK.md) — 과거 실행기 참고용
- [전체 작업 절차](docs/agent/WORKFLOW.md)
- [도구와 API](TOOLS.md)
- [상세 모델링 지침](docs/agent/MODELING.md)
- [GLB 기반 매스 재구성](docs/agent/GLB_MASS.md)
- [GLB 없는 사진 증거 작업](docs/agent/PHOTO_ONLY.md)
- [상가·학교·비정형 볼륨](docs/agent/VOLUMES.md)
- [메모리 범위](docs/agent/MEMORY.md)

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임의 색·밝기와 다릅니다. 사진 지표는 나무·그림자·원근에 취약하며, `facade_read.py`와 `band_scan.py`는 실제 사진 확인이 필요한 v1입니다. FBX와 LOD는 Blender 없이 완료할 수 없습니다. 최종 크기, 창, 알파, 야간 조명, 정면, 입구, 시그니처 등록은 게임에서 확인하세요. 선택한 모델의 실제 작업 완료율·토큰·시간은 모델 연결 후 별도로 측정해야 합니다.
