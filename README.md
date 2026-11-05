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

`paint_include`와 `paint_exclude`로 나무·간판·그림자 등을 정규화된 벽 U/V 좌표로 제외할 수 있습니다. 창은 자동 마스크에서 제외하고, 미확정 셀은 임의 색으로 채우지 않고 `cell_id=-1`로 남겨 기본 벽 재질을 유지합니다. `_mask.png`와 refs 디버그 이미지를 반드시 확인하세요. 캡처 재개, camera 필드, 성능 선택지는 [네이버 VR 캡처와 도색 refs](docs/agent/NAVER_VR.md)에 정리했습니다.

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

### 상가·학교·비정형 건축물

`--template generic`은 아파트 전용 프리셋 대신 **여러 볼륨과 벽 단위 부품을 조합**합니다. `generic_spec.json`에 다음을 입력합니다.

- 임의의 단순 다각형 footprint, 볼륨별 높이와 시작 높이
- 벽별 `window_band`, `shopfront`, `louver_zone`, `railing_zone`
- `sign_slot`, `roof_equipment`, `covered_link`, `entrance_canopy`

`build_volume_spec`이 같은 데이터를 FULL/SIMPLIFY_TRIM/LOD_CULL로 생성하므로 LOD를 따로 설계하지 않아도 됩니다. LOD2에서도 여러 볼륨의 실루엣을 유지합니다.

생성된 벽은 ID, 길이, 높이, 법선, render box를 `manifest.metadata.walls`에 기록하므로 사진 검사에 그대로 연결할 수 있습니다. 임의 다각형 지붕은 삼각형으로 분할하고, OBJ는 삼각형과 사각형의 꼭짓점 UV를 모두 지원합니다.

`example_generic_cs2.py`와 `templates/generic_spec.example.json`은 본관과 각진 체육관을 조합한 합성 예제입니다. 이 예제의 quick, FBX, 사진, 타일, LOD, visual review를 모두 PASS로 확인했습니다. 곡면이나 매우 복잡한 접합은 여전히 custom generator가 필요합니다.

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
- [GLB 기반 매스 재구성](docs/agent/GLB_MASS.md)
- [GLB 없는 사진 증거 작업](docs/agent/PHOTO_ONLY.md)
- [상가·학교·비정형 볼륨](docs/agent/VOLUMES.md)
- [메모리 범위](docs/agent/MEMORY.md)

## 알려진 한계

미리보기는 단순 정사영 렌더라 게임의 색·밝기와 다릅니다. 사진 지표는 나무·그림자·원근에 취약하며, `facade_read.py`와 `band_scan.py`는 실제 사진 확인이 필요한 v1입니다. FBX와 LOD는 Blender 없이 완료할 수 없습니다. 최종 크기, 창, 알파, 야간 조명, 정면, 입구, 시그니처 등록은 게임에서 확인하세요.
