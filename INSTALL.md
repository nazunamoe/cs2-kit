# CS2 건물 키트 설치 (새 프로젝트에 넣기)

이 압축 파일 하나에 CS2 건물 생성 작업에 필요한 공통 도구가 모두 들어 있습니다.
**한 번만 풀어서 키트 루트로 두고**, 건물은 `projects/` 안에 만들어 쓰세요(폴더 구조 유지). 업데이트할 때는 새 압축을 같은 곳에 덮어 풀면 됩니다. `projects/` 와 `memory/` 는 압축에 들어 있지 않아 지워지지 않습니다.

## 들어 있는 것
| 경로 | 내용 |
|---|---|
| `cs2kit.py` | 생성기 공통 라이브러리 (아틀라스, 메시, 창, 내보내기) |
| `example_building_cs2.py` | 생성기 시작 틀 (복사해서 `<이름>_cs2.py` 로) |
| `example_curtainwall_cs2.py` | 커튼월·커튼월룩 건물 시작 틀 (`K.curtainwall` 사용) |
| `tools/` | 만들기·검사·미리보기·사진 비교·재질 추출·스캔 측정·Blender 실행 (`cycle.py` 등) |
| `facade_tools/` | (삼한골든뷰 전용; 범용은 `tools/facade_paint.py`) 상세 사진에서 층 번호·도색 구간·창 위치를 읽는 보조 도구 (사용법 `facade_tools/README.md`). 특정 생성기 구조를 전제로 하므로 새 건물에서는 README 의 "생성기 조건"을 확인 |
| `CLAUDE.md`, `AGENTS.md` | 작업 규칙 (Claude Code / Codex). CLAUDE.md 에는 한국어 응답, 정밀 분석·타일 비교, 도색·재질, 웹 조사, 개구부·난간 규칙과 이전 작업의 교훈(층 세기·사각형 도색·창 목록)이 들어 있음 |
| `TOOLS_CLAUDE.md`, `README.md` | 도구 설명서 |
| `.claude/` | Claude Code 설정(허용 명령)과 스킬 `/build` `/resume` `/fix` `/photo-refs` |
| `templates/` | 빈 `TASK.md`(루버·난간·발코니·커튼월 종류, 조사용 단지 정보, 특징 층 칸 포함), `photo_refs.example.json`, memory 초기 파일 |
| `tools/project.py` | 프로젝트 만들기·전환·이전, memory 초기화 |

## 순서
1. 키트 폴더에 압축을 풉니다(처음 한 번). `python tools/project.py init` 으로 `memory/` 를 만듭니다.
2. 건물마다 `python tools/project.py new <이름>` (커튼월이면 `--template cw`) → `projects/<이름>/` 가 생깁니다.
3. 그 폴더의 `photos/` 에 사진(과 있으면 스캔 `.glb`)을 넣고 `TASK.md` 를 채웁니다.
4. Claude Code 를 **키트 루트**에서 열고 `/build` 를 실행합니다.
- 예전 방식으로 작업하던 폴더라면: 새 압축을 덮어 푼 뒤 `python tools/project.py migrate <이름> --apply` 로 기존 작업을 `projects/<이름>/` 로 옮깁니다(삼한골든뷰처럼 `facade_tools/` 가 한 건물 전용이면 `--facade-tools` 도).

## 참고
- `tools/blender_path.txt` 에 이 컴퓨터의 Blender 경로가 들어 있습니다. 다른 컴퓨터라면
  `python tools/run_blender.py --set "<blender.exe 경로>"` 로 다시 지정합니다.
- 필요한 Python 패키지: numpy, Pillow.
- 건물별 파일(생성기, 사진, output/, previews/, backup/, 조사 메모)은 들어 있지 않습니다.
