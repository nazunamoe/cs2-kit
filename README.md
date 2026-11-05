# CS2 건축 에셋 키트 — Claude Code

사진과 건축 정보로 Cities: Skylines II 건축 에셋을 만드는 키트입니다. 이 브랜치는 **Claude Code 전용 스킬과 훅**을 제공하며, 모든 작업이 같은 검증 엔진과 상태 파일을 공유합니다.

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

## 3. Claude Code로 실행

키트 루트에서 Claude Code를 열고 실행합니다.

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
- `/fix <요청>`: 범위 수정, 최종 검증, 변경 범위 비교

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
- [전체 작업 절차](docs/agent/WORKFLOW.md)
- [도구와 API](TOOLS_CLAUDE.md)
- [상세 모델링 지침](docs/agent/MODELING.md)
- [메모리 범위](docs/agent/MEMORY.md)

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임의 색·밝기와 다릅니다. 사진 지표는 나무·그림자·원근에 취약하며, `facade_read.py`와 `band_scan.py`는 실제 사진 확인이 필요한 v1입니다. FBX와 LOD는 Blender 없이 완료할 수 없습니다. 최종 크기, 창, 알파, 야간 조명, 정면, 입구, 시그니처 등록은 게임에서 확인하세요.
