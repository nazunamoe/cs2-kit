# CS2 Korean building asset kit — Claude Code

사진과 건축 정보를 바탕으로 Cities: Skylines II 건축 에셋 생성기를 만드는 키트입니다. `cs2kit`가 형상·아틀라스·창·LOD·납출을 담당하고, Claude Code 스킬은 공통 `tools/agent.py`를 호출합니다.

## 구조

```text
CLAUDE.md                  Claude 전용 얇은 어댑터
AGENTS.md                  자동 로드되는 80줄 공통 규칙
.claude/skills/            /build /resume /photo-refs /fix
.claude/hooks/stop_gate.py final/fix 미완료 종료 확인
TOOLS_CLAUDE.md            필요할 때 읽는 도구/API 설명
docs/agent/WORKFLOW.md     빌드·검증·재개·부분 수정 절차
docs/agent/MODELING.md     상세 입면·사진·재질 규칙
projects/<name>/           TASK, STATUS, photos, generator, output, previews, work
memory/                    재사용 절차와 기본값 (건축물별 색상/좌표 금지)
tools/agent.py             공통 JSON 실행 엔진
tools/cycle.py             quick/visual/final 공통 게이트
```

## 설치와 시작

Python 3.9+, numpy, Pillow가 필요합니다. FBX와 LOD 검사에는 Blender 5.2가 필요합니다.

```bash
pip install numpy pillow
python tools/project.py init
python tools/run_blender.py --find
python tools/project.py new my-apt
# curtain wall: python tools/project.py new my-apt --template cw
```

`projects/my-apt/photos/`에 참고 사진과 선택적 GLB를 넣고 `TASK.md`를 채웁니다. 모르는 값은 비워 둡니다. 에셋 이름과 텍스처에는 실제 단지·브랜드 이름을 쓰지 않습니다.

키트 루트에서 Claude Code를 열고 다음을 실행합니다.

```text
/build
/build 옥상 물탱크 디테일 강조
```

`.claude/settings.json`은 한국어, `python tools/...` 실행 허용, Stop 훅을 설정합니다. 스킬과 훅은 버전 관리됩니다.

## 스킬

- `/build [추가 요청]`: 전체 제작
- `/resume`: 저장된 상태의 `next_action`부터 재개
- `/photo-refs`: 사진 모서리 생성·검증
- `/fix <요청>`: 스냅샷 → 범위 수정 → final gate → outside-scope 비교 → 이미지 review

스킬에는 별도 검사기나 긴 모델링 규칙이 없습니다. 모든 스킬이 같은 JSON gate와 상태를 사용하므로 터미널에서 직접 같은 명령을 실행할 수도 있습니다.

## 세 가지 검증 모드

| 모드 | 수행 내용 | 사용 시점 |
|---|---|---|
| `quick` | 일반 Python OBJ + 규격/형상 검사 | 문법·좌표·겹침 수정 반복 |
| `visual` | OBJ + 미리보기 + 사진 비교 | 매스·창·입면·재질 변경 후 |
| `final` | Blender FBX + 사진+타일+LOD+strict gate | 최종 보고·부분 수정 완료 전 |

```bash
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode quick --label mass --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode visual --label windows --json
python tools/agent.py cycle --project my-apt --generator my_apt_cs2.py --mode final --label final --json
```

- `PASS`: 요청한 검사가 모두 통과했습니다.
- `FAIL`: 실행된 검사가 실패했습니다.
- `INCOMPLETE`: 필수 검사나 이미지 확인이 아직 없습니다.
- `NOT_APPLICABLE`: `photo_refs.json`이 없어 사진 검사 대상이 아닙니다.
- `NOT_CHECKED`: 검증하지 않은 상태이며 PASS로 해석하면 안 됩니다.

visual/final 후에는 현재 미리보기와 표시된 비교 그림을 Read로 확인하고 기록합니다.

```bash
python tools/agent.py review --project my-apt --status PASS --note "reviewed final images" --json
```

Stop 훅은 final/fix 단계에서 PASS가 아닌 채 종료하면 저장된 다음 행동을 알려 줍니다. 반복 종료를 무한히 막지는 않으며, 실패 원인은 그대로 보고해야 합니다.

## 사진과 토큰 사용

모든 원본과 3x3 확대를 기본으로 읽지 않습니다. 연락판 페이지 → 대표 사진 → 불확실한 영역 확대 순서로 좁힙니다.

```bash
python tools/agent.py photos --project my-apt --page 0 --page-size 30 --json
python tools/agent.py observe --project my-apt --photo photos/front.jpg --side front --note "36 rows; left bays hidden" --json
```

관찰값은 `work/observations.json`, 사진 해시는 `work/photo_manifest.json`에 저장됩니다. 사용자가 작성한 `photo_refs.json`은 수정하지 않습니다.

## 재개와 부분 수정

`work/agent_state.json`에는 생성기 해시, 마지막 gate, 다음 행동, mismatch 재시도, visual review가 저장됩니다. `STATUS.md`는 짧은 인수인계 요약입니다.

```bash
python tools/agent.py resume --project my-apt --json
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --request "change only entrance railing" --box=-5,5,-1,1,0,6 --json
python tools/agent.py fix --project my-apt --generator my_apt_cs2.py --finish --json
```

`/fix`가 이 절차를 자동으로 안내합니다. final gate와 compare 중 하나라도 실패하면 PASS로 보고하지 않습니다.

## 생성기와 도구

1 unit = 1 m, 지면 z=0, 정면=-Y입니다. 생성기는 `import cs2kit as K`로 `Atlas`, `MeshBuilder`, `WindowSet`, `export_asset`을 사용합니다. LOD1은 main의 50% 미만, LOD2는 500 tris 이하입니다. main은 30k-60k를 목표로 하고 95k 초과는 경고입니다. 삼각형 수를 줄이기 위해 실제 층수·bay·창 위치를 바꾸지 않습니다.

- `check.py`: OBJ/PNG 규격·겹침·창·UV·LOD 검사
- `render.py`: Blender 없이 미리보기
- `photo_check.py`: 크기·비율·층간 비교
- `tile_compare.py`: 세부 선·색 비교, 점수는 참고용
- `sat_grid.py`, `extract_texture.py`: 사진 좌표·재질 추출
- `facade_paint.py`, `facade_read.py`, `band_scan.py`: 층·창·도색 보조 인식
- `glb_measure.py`, `glb_slices.py`: 스캔 측정 전용
- `compare.py`: 수정 전후 변경 범위 비교
- `tools/qa/verify.py`: 공통 gate + 선택적 same-camera 회귀 검사
- `tools/facade/`, `tools/scan/`: 추가 측정·비교 도구, 각 README 참조
- `tools/samhan_facade/`: 특정 기존 생성기 전용, 새 건축물에 그대로 사용 금지

자세한 API와 명령은 `TOOLS_CLAUDE.md`, 상세 모델링은 `docs/agent/MODELING.md`에 있습니다.

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임 색·밝기와 다릅니다. 창 가림은 세 지점을 표본 검사합니다. 사진 지표는 가림과 조명에 취약합니다. `facade_read.py`와 `band_scan.py`는 v1이며 실제 사진 확인이 필요합니다. FBX와 LOD는 Blender 없이 완료할 수 없고, 최종 크기·야간·알파·입구·시그니처 등록은 게임에서 확인해야 합니다.
