"""_gen.py - 활성 프로젝트(projects/<이름>/)의 생성기 파일 경로 (rail_*.py 가 씀).
순서: 환경변수 FACADE_GEN (절대 경로, 또는 프로젝트 폴더 기준 파일 이름) > 프로젝트 폴더의 *_cs2.py 가 하나일 때 그 파일
(backup*, example* 은 제외). import 하면 작업 폴더가 활성 프로젝트로 바뀐다(tools/proj.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import proj  # noqa: E402


def gen_path():
    g = os.environ.get("FACADE_GEN")
    if g:
        return g if os.path.isabs(g) else os.path.join(proj.ROOT, g)
    c = sorted(f for f in os.listdir(proj.ROOT) if f.endswith("_cs2.py") and not f.startswith(("backup", "example")))
    if len(c) != 1:
        raise SystemExit("generator not unique in %s: %s -> set FACADE_GEN" % (proj.ROOT, c))
    return os.path.join(proj.ROOT, c[0])
