# CLAUDE.md — Claude Code adapter

모든 대화·진행 설명·보고는 한국어로 한다. 도구 출력과 코드의 영어 식별자는 그대로 둔다.

@AGENTS.md

## 모델 분담
- 파일 탐색과 검색은 Explore, `agent.py cycle`·검사·빌드 같은 긴 출력의 명령 실행은 runner 에 맡긴다. 결과는 결론과 `경로:줄번호`, 상태 줄만 받는다.
- 설계, 디버깅, 코드 편집, 사진·렌더 그림을 보고 하는 판단(형태, 좌표, 색, 창·도색 읽기, `photo_refs.json`, 최종 리뷰)은 메인에서 직접 한다. 서브에이전트에 맡기지 않는다.
- 빠짐없이 찾아야 하는 탐색(수정 전 전체 사용처 등)은 검색 결과 원문을 함께 받거나 메인에서 직접 확인한다.
- 서브에이전트 보고 가운데 결정의 근거로 쓰는 사실은 해당 파일을 직접 열어 한 번 확인한다. 특히 최종 보고의 PASS/FAIL 은 runner 보고만 믿지 말고 `work/agent_state.json` 이나 gate.json 으로 확인한다.
- `next_action` 이 가리키는 그림은 runner 가 열지 않는다. 메인이 직접 열어 보고 `agent.py review` 로 기록한다.

## 어드바이저
- 두 경우에만 부른다. 설계나 접근을 확정하기 직전(체크포인트 A 사진 분석 끝, 체크포인트 B 덩어리 끝, 사용자 승인이 필요한 수정을 제안하기 전), 같은 오류를 두 번 고쳐도 안 풀릴 때(AGENTS.md 의 반복 불일치 규칙과 같은 시점).
- 그 밖에는 부르지 않는다.

## Claude Code에서만 적용하는 규칙

- 파일은 Read/Write/Edit 도구로 다룬다. PowerShell here-string은 편집 도구가 없거나 반복 실패할 때만 `docs/agent/POWERSHELL.md`를 참고한다.
- 의미상 한 변경 단위면 편집 줄 수를 제한하지 않는다. 각 단계 후에는 `docs/agent/WORKFLOW.md`의 quick/visual/final gate를 선택한다.
- 사진은 Read로 직접 본다. 다만 모든 원본과 3x3 확대를 기본으로 읽지 않는다. `agent.py photos`의 연락판 페이지 → 대표 사진 → 불확실한 영역 확대 순서로 좁힌다.
- 사용자가 만든 `photo_refs.json`은 수정하지 않는다. 새로 만들 때는 대표 사진의 모서리를 읽고 visual 비교 시트로 정합을 확인한다.
- 자동 수치와 눈으로 본 결과가 다륩면 근거를 기록한다. 숫자가 맞아도 저층부 높이, 코어 위치, 발코니 깊이, 색 띠, 크라운이 다륩면 수정한다.
- 상세 입면·도색·GLB·웹 조사가 필요할 때만 `docs/agent/MODELING.md`를 읽는다. `complex_name`이 비어 있으면 웹 조사를 하지 않는다. GLB가 없으면 스캔 절차를 생략한다.
- 건축물별 색상·좌표·창 수열을 `memory/LESSONS.md`에 쓰지 않는다. 현재 프로젝트의 `agent.py observe`와 작업 메모에 기록한다. 전역 기억은 `docs/agent/MEMORY.md`의 범위 규칙을 따른다.

## 명령

- `/build [추가 요청]`: TASK 기반 전체 제작
- `/resume`: 저장된 상태와 `next_action`부터 재개
- `/photo-refs`: 연락판과 대표 사진으로 사진 좌표 생성·검증
- `/photo-observe`: 벽 사진 한 장을 확대·체크리스트로 읽고 교차 확인 후 `agent.py observe`로 기록
- `/fix <요청>`: 스냅샷 → 범위 수정 → final gate → outside-scope 비교 → 이미지 review

스킬은 공통 `tools/agent.py`를 호출한다. 스킬에 별도 검사기나 긴 모델링 규칙을 복사하지 않는다. 도구의 상세 명령은 `TOOLS_CLAUDE.md`를 필요할 때 읽는다.

## 완료 조건

최종 보고 전 `agent.py cycle --mode final`과 이미지 `agent.py review`까지 PASS여야 한다. 사진이 없으면 `NOT_APPLICABLE`와 없는 사진 비교를 구분하고, Blender나 LOD가 없으면 INCOMPLETE로 보고한다.

버전 관리된 Stop hook은 final/fix 단계에서 PASS가 아닌 채 종료하면 저장된 `next_action`을 알려 준다. 훅 대신 로그를 다시 읽지 말고 `work/agent_state.json`을 확인한다.
