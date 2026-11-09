# 문서 지도

이 폴더의 문서는 **현재 작업용**(`docs/agent/`)과 **역사 기록**(`docs/archive/`)으로 나뉩니다. 모든 경로는 키트 루트 기준입니다.

## 처음 시작

| 문서 | 언제 읽나 |
|---|---|
| [`README.md`](../README.md) | 설치, 첫 프로젝트, 전체 개요 |
| [`INSTALL.md`](../INSTALL.md) | 환경·Blender·선택 의존성 |
| [`agent/WORKFLOW.md`](agent/WORKFLOW.md) | 작업 시작, 재개, 게이트, 최종 보고 |
| [`agent/MEMORY.md`](agent/MEMORY.md) | 전역 기억의 범위와 조회 |

## 입력과 사진

| 문서 | 언제 읽나 |
|---|---|
| [`agent/NAVER_VR.md`](agent/NAVER_VR.md) | 네이버 VR URL 캡처, `photo_refs` |
| [`agent/XRX_MASS.md`](agent/XRX_MASS.md) | VR 메타만으로 매스 초안 |
| [`agent/PANORAMA_360.md`](agent/PANORAMA_360.md) | 360 사진을 원근 크롭 |
| [`agent/VIDEO_FRAMES.md`](agent/VIDEO_FRAMES.md) | 영상 답사에서 프레임 추출 |
| [`agent/IFC_TO_GLB.md`](agent/IFC_TO_GLB.md) | IFC·CAD를 GLB로 변환 |
| [`agent/PHOTO_ONLY.md`](agent/PHOTO_ONLY.md) | GLB 없이 사진 증거로 작업 |
| [`agent/POWERSHELL.md`](agent/POWERSHELL.md) | Edit 도구를 못 쓸 때의 편집 대체 |

## 모델링

| 문서 | 언제 읽나 |
|---|---|
| [`agent/MODELING.md`](agent/MODELING.md) | 입면 구성, 도색, 검토의 기본 |
| [`agent/FACADE_MEASURED.md`](agent/FACADE_MEASURED.md) | 측정 ref 기반의 창·도색·저층부 작업 |
| [`agent/FACADE_KNOWHOW.md`](agent/FACADE_KNOWHOW.md) | 반복해서 틀렸던 입면 실수와 교훈 |
| [`agent/VOLUMES.md`](agent/VOLUMES.md) | 상가·학교·비정형 볼륨 |
| [`agent/GLB_MASS.md`](agent/GLB_MASS.md) | GLB 단면에서 단순화 매스 만들기 |

입면 작업은 **`FACADE_MEASURED` → `FACADE_KNOWHOW` → `MODELING`** 순서로 읽는 것이 가장 빠릅니다. 앞 문서가 절차, 가운데가 함정, 뒤가 전체 구성입니다.

## 검증과 도구

| 문서 | 언제 읽나 |
|---|---|
| [`../TOOLS_CLAUDE.md`](../TOOLS_CLAUDE.md) | 도구 명령과 API |
| [`agent/WORKFLOW.md`](agent/WORKFLOW.md) | quick/visual/final 게이트의 의미 |
| [`../README.md`](../README.md) | 최종 보고와 게임 내 확인 항목 |

## 역사·제안

현재 명세가 아닙니다. 실행 전에는 `docs/agent/`와 `TOOLS_CLAUDE.md`를 기준으로 합니다.

| 문서 | 내용 |
|---|---|
| [`archive/PROPOSAL_pipeline_v2.md`](archive/PROPOSAL_pipeline_v2.md) | 2026-11-04 파이프라인 2차 개선안. 프리셋·소켓·읽기 도구는 이후 구현됨 |

## 문서를 추가할 때

1. 현재 작업에 쓰는 문서는 `docs/agent/`에 둡니다.
2. 끝난 제안·회고는 `docs/archive/`로 옮기고 머리말에 "역사 문서"를 표시합니다.
3. 특정 건물의 좌표·색·창 수는 문서가 아니라 해당 프로젝트의 `TASK.md`·`building_spec_*.yaml`에 둡니다.
4. 이 지도에 한 줄을 추가하고, 옮긴 문서를 참조하는 코드·문서 경로를 함께 고칩니다.
