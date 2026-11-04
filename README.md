# CS2 건축 에셋 키트 — Codex / Kimi Code

사진과 건축 정보로 Cities: Skylines II 건축 에셋을 만드는 키트입니다. 이 브랜치는 **Codex와 Kimi Code가 공통으로 사용하는 `AGENTS.md`와 JSON 실행 엔진**을 제공합니다.

## 1. 준비

필요한 환경:

- Python 3.9 이상
- `numpy`, `Pillow`
- Blender 5.2 — FBX 생성과 최종 LOD 검사에 필요

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
```

이제 `projects/my-apt/`에서 다음을 준비합니다.

1. `photos/`에 참고 사진과 선택적 GLB를 넣습니다.
2. `TASK.md`에 아는 정보를 적고, 모르는 값은 비워 둡니다.
3. 실제 단지 이름·브랜드·로고는 에셋 이름과 텍스처에 사용하지 않습니다.

## 3. Codex / Kimi Code로 실행

키트 루트에서 Codex 또는 Kimi Code를 엽니다. `AGENTS.md`의 작업 규칙을 따르게 하고, 첫 환경 점검을 실행합니다.

```bash
python tools/agent.py doctor --project my-apt --json
```

첫 요청 예시:

```text
AGENTS.md와 projects/my-apt/TASK.md를 읽고 프로젝트를 만들어줘.
tools/agent.py의 next_action을 따라 quick/visual/final 검증을 진행하고,
최종 gate와 이미지 review가 PASS일 때만 완료 보고를 해줘.
```

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

JSON의 `next_action`을 따르고, 상세 로그는 지정된 파일이 필요할 때만 읽습니다. visual/final 후에는 현재 미리보기와 표시된 비교 이미지를 확인하고 결과를 기록합니다.

```bash
python tools/agent.py review --project my-apt --status PASS --note "reviewed final images" --json
```

이미지 입력이 없는 모델은 본 것처럼 기록하지 않고, 제공된 `photo_refs.json`과 수치 데이터를 사용합니다.

## 5. 사진, 결과, 재개

사진은 연락판 페이지 → 대표 사진 → 필요한 영역 확대 순서로 확인합니다. 관찰한 사진은 해시로 기록해 같은 이미지를 반복해서 읽지 않습니다.

```bash
python tools/agent.py photos --project my-apt --page 0 --page-size 30 --json
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

부분 수정 완료 시 final gate와 outside-scope 비교를 함께 실행합니다. 하나라도 실패하면 PASS로 보고하지 않습니다.

## 6. 생성과 편집 규칙

- 1 unit = 1 m, 지면 `z=0`, 정면은 `-Y`입니다.
- 생성기는 `import cs2kit as K`로 `Atlas`, `MeshBuilder`, `WindowSet`, `export_asset`을 사용합니다.
- LOD1은 main의 50% 미만, LOD2는 500 tris 이하입니다.
- main은 30k–60k tris를 목표로 하며 95k 초과는 경고입니다.
- 삼각형 수를 줄이기 위해 실제 층수, bay, 창 위치를 바꾸지 않습니다.
- 네이티브 Edit/apply_patch를 우선 사용하고, 셸 문자열로 소스를 조합하지 않습니다.
- 코드·YAML 키·도구 출력·파일 이름은 ASCII를 사용합니다.

Windows에서는 PowerShell 7과 UTF-8을 권장합니다. 네이티브 편집이 반복해서 실패할 때만 [PowerShell 편집 fallback](docs/agent/POWERSHELL.md)을 사용합니다.

## 7. 더 보기

- [설치와 업그레이드](INSTALL.md)
- [전체 작업 절차](docs/agent/WORKFLOW.md)
- [도구와 API](TOOLS.md)
- [상세 모델링 지침](docs/agent/MODELING.md)
- [메모리 범위](docs/agent/MEMORY.md)

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임의 색·밝기와 다릅니다. 사진 지표는 나무·그림자·원근에 취약하며, `facade_read.py`와 `band_scan.py`는 실제 사진 확인이 필요한 v1입니다. FBX와 LOD는 Blender 없이 완료할 수 없습니다. 최종 크기, 창, 알파, 야간 조명, 정면, 입구, 시그니처 등록은 게임에서 확인하세요.
