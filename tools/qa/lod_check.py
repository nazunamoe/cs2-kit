"""LOD 투명(구멍) 검사 - 게임처럼 뒷면을 그리지 않을 때 메인/LOD1/LOD2 에서 건물 안쪽 뒷면이 비치는 곳
(앞면이 빠졌거나 뒤집힌 곳 = 게임에서 "투명해 보이는" 곳)을 여러 각도에서 잰다. LOD 는 메인도 막혀 있는 자리만 센다.

검증 도구(tools/qa/). cycle.py 다음에, 보고 전에 매번 돌린다.
Blender 앱이 있으면 앱으로(빠름), 없으면 bpy 모듈로 돈다(`LOD_ENGINE=exe|py` 로 고정).
  python tools/qa/lod_check.py output/<asset>                # 활성 프로젝트 기준 경로
  python tools/qa/lod_check.py output/<asset> --az 16 --elev -10,5,25,50 --res 512
  python tools/qa/lod_check.py --self-test                  # closed cube PASS + open-front cube FAIL baseline

출력: previews/lod_check/<asset>/  (구멍이 보인 각도마다 그림: 회색 = 메인만, 흰색 = LOD 도 있음, 빨강 = 구멍)
마지막 줄: LODCHECK PASS|FAIL lod1 max X% (az, el) lod2 max Y% ...   기준: 각 각도 구멍 0.05% 이하 = PASS

--quick : 반복 중 빠른 확인용 (방위 8 x 올려다봄/내려다봄 2 = 16시점, 해상도 256). 얇은 틈은 놓칠 수 있다 ->
          마지막 줄이 `LODCHECK QUICK ok|bad` 로 나오며 **보고용이 아니다**. 보고 전에는 --quick 없이 전체(64시점)를 돌린다.
"""
import argparse, json, os, subprocess, sys, glob

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> 키트 루트
LIMIT = 0.05
MARGIN = 0.03
_BPY = []                                   # [경로] 또는 [None] - 한 번만 탐색


def bpy_python():
    """bpy 모듈이 설치된 Python. 없으면 None. (Blender 앱 없이 LOD 검사)"""
    if _BPY:
        return _BPY[0]
    cands = []
    if os.environ.get("BLENDER_PY"):
        cands.append(os.environ["BLENDER_PY"].strip().strip('"'))
    p = os.path.join(KIT, "tools", "blender_py.txt")
    if os.path.exists(p):
        cands.append(open(p, encoding="utf-8").read().strip().strip('"'))
    cands += [os.path.join(KIT, ".venv-bpy", "Scripts", "python.exe"),
              os.path.join(KIT, ".venv-bpy", "bin", "python")]
    found = None
    for c in cands:
        if c and os.path.isfile(c):
            r = subprocess.run([c, "-c", "import bpy"], capture_output=True)
            if r.returncode == 0:
                found = c
                break
    _BPY.append(found)
    return found


def blender_exe():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"].strip().strip('"')
    p = os.path.join(KIT, "tools", "blender_path.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return "blender"


def _blender_ok(exe):
    import shutil
    return bool(exe) and (os.path.isfile(exe) or bool(shutil.which(exe)))


def lod_engine():
    """LOD 검사 엔진. LOD_ENGINE=exe|py 로 고정할 수 있다.
    기본: Blender 앱이 있으면 앱(렌더가 훨씬 빠름), 없으면 bpy 모듈.
    (FBX 쪽은 run_blender.py 가 bpy 를 먼저 쓴다 - 결과는 같고 기동이 가볍다)"""
    kind = (os.environ.get("LOD_ENGINE") or "").strip().lower()
    exe = blender_exe()
    if kind in ("exe", "blender", "app"):
        return ("exe", exe) if _blender_ok(exe) else None
    py = bpy_python()
    if kind in ("py", "bpy"):
        return ("py", py) if py else None
    if _blender_ok(exe):
        return ("exe", exe)
    return ("py", py) if py else None


def run_bl(py_file, args, blend=None):
    """lod_check_bl.py / 기준 생성 스크립트를 Blender 앱 또는 bpy 모듈로 실행."""
    eng = lod_engine()
    if not eng:
        kind = (os.environ.get("LOD_ENGINE") or "").strip().lower()
        if kind in ("exe", "blender", "app"):
            sys.exit(f"[lod_check] LOD_ENGINE={kind} but no Blender app found ({blender_exe()})")
        if kind in ("py", "bpy"):
            sys.exit("[lod_check] LOD_ENGINE=bpy but no python with the bpy module was found "
                     "(run `python tools/run_blender.py --set-py <python.exe>`)")
        sys.exit("[lod_check] no Blender app and no bpy module - run `python tools/run_blender.py --find`")
    kind, exe = eng
    if kind == "py":
        return subprocess.run([exe, py_file, "--"] + args, capture_output=True, text=True)
    cmd = [exe, "-b"] + ([blend] if blend else []) + ["--python-exit-code", "1", "-P", py_file, "--"] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def active_project():
    try:
        out = subprocess.run([sys.executable, os.path.join(KIT, "tools", "project.py"), "where"],
                             capture_output=True, text=True, cwd=KIT).stdout.strip().splitlines()
        for line in out:
            if os.path.isdir(line.strip()):
                return line.strip()
    except Exception:
        pass
    return os.getcwd()


def baseline_self_test():
    proj = active_project()
    work = os.path.join(proj, "work", "lod_baseline")
    os.makedirs(work, exist_ok=True)
    maker = os.path.join(work, "make_baseline.py")
    source = r'''import bpy, bmesh, os, sys
out = sys.argv[sys.argv.index("--") + 1]
for name, missing in (("BaselineClosed", False), ("BaselineOpen", True)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    obj = bpy.context.active_object
    obj.name = name
    if missing:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        faces = [f for f in bm.faces if f.normal.y < -0.5]
        bmesh.ops.delete(bm, geom=faces, context="FACES_ONLY")
        bm.to_mesh(obj.data)
        bm.free()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, name + ".blend"))
'''
    with open(maker, "w", encoding="utf-8") as f:
        f.write(source)
    made = run_bl(maker, [work])
    if made.returncode:
        print(made.stdout[-2000:], made.stderr[-2000:])
        print("LODBASELINE FAIL: could not create baseline assets")
        sys.exit(1)
    passed = True
    for name, expected in (("BaselineClosed", "PASS"), ("BaselineOpen", "FAIL")):
        path = os.path.join(work, name + ".blend")
        result = subprocess.run([sys.executable, os.path.abspath(__file__), path, "--az", "4", "--elev", "5", "--res", "128"],
                                capture_output=True, text=True)
        lines = [line for line in result.stdout.splitlines() if line.startswith("LODCHECK")]
        actual = lines[-1].split()[1] if lines else "ERROR"
        ok = actual == expected
        passed &= ok
        print(f"LODBASELINE {name} expected={expected} actual={actual} {'PASS' if ok else 'FAIL'}")
    print(f"LODBASELINE {'PASS' if passed else 'FAIL'} closed=PASS open=FAIL")
    sys.exit(0 if passed else 1)


def print_where(p, shift):
    """One hole spot: the BACK face seen through the hole (gen = exported xyz - pivot_shift), then the nearest front faces around the
    hole = candidates for the missing wall. gap = screen distance (m) from the hole to that face's outline; two faces with a tiny gap
    on both sides mean a seam, one face ending beside the hole means a ray slipped past its end."""
    gx = [p["xyz"][0] - shift[0], p["xyz"][1] - shift[1], p["xyz"][2]]
    side = " (back face: the ray entered through an opening or a seam)" if p.get("back_face") else ""
    print(f"      at gen ({gx[0]:.2f}, {gx[1]:.2f}, {gx[2]:.2f})  normal {tuple(p['normal'])}  {p['px']} px  [{p['obj']}]{side}")
    for q in p.get("near", []):
        lo = (q["lo"][0] - shift[0], q["lo"][1] - shift[1], q["lo"][2])
        hi = (q["hi"][0] - shift[0], q["hi"][1] - shift[1], q["hi"][2])
        print(f"        near front face normal {tuple(q['normal'])} gap {q['gap']:.2f} m  gen ({lo[0]:.2f},{lo[1]:.2f},{lo[2]:.2f})..({hi[0]:.2f},{hi[1]:.2f},{hi[2]:.2f})  {q['tris']} tris")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("asset", nargs="?", help="output/<asset> (폴더) 또는 .blend")
    ap.add_argument("--self-test", action="store_true", help="closed cube PASS and open-front cube FAIL baseline")
    ap.add_argument("--az", type=int, default=16, help="방위각 개수 (기본 16 = 22.5도 간격)")
    ap.add_argument("--elev", default="-10,5,25,50", help="올려다봄(-)·내려다봄(+) 각도들")
    ap.add_argument("--res", type=int, default=512)
    ap.add_argument("--quick", action="store_true", help="16시점·해상도 256 (반복용; 보고용 아님, 결과 줄이 LODCHECK QUICK)")
    a = ap.parse_args()
    if a.self_test:
        baseline_self_test()
    if not a.asset:
        ap.error("asset is required unless --self-test is used")
    if a.quick:
        a.az, a.elev, a.res = 8, "5,50", 256

    proj = active_project()
    path = a.asset if os.path.isabs(a.asset) else os.path.join(proj, a.asset)
    if os.path.isdir(path):
        bl = [f for f in glob.glob(os.path.join(path, "*.blend"))]
        if not bl:
            sys.exit(f"[lod_check] no .blend in {path} (FBX/blend 이 안 만들어졌으면 검사 불가)")
        path = bl[0]
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(proj, "previews", "lod_check", name)
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*.png")):
        os.remove(f)
    bl = os.path.join(KIT, "tools", "qa", "lod_check_bl.py")
    eng = lod_engine()
    if eng:
        print(f"[lod_check] engine: {'Blender app' if eng[0] == 'exe' else 'bpy module'}  {eng[1]}")
    for _ in range(2):                                 # once more on a one-off failure (file still being written)
        r = run_bl(bl, [path, out, str(a.res), str(a.az), a.elev], blend=path)
        if "LODCHECK_DONE" in r.stdout:
            break
    if "LODCHECK_DONE" not in r.stdout:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit("[lod_check] Blender/bpy run failed")
    rows = json.load(open(os.path.join(out, "lod_check.json"), encoding="utf-8"))["rows"]
    man = os.path.join(os.path.dirname(path), "manifest.json")
    shift = (0.0, 0.0)
    if os.path.exists(man):                            # kit 이 피벗을 바닥 가운데로 옮긴 양
        shift = tuple(json.load(open(man, encoding="utf-8")).get("pivot_shift", (0.0, 0.0)))
    ok = True
    marginal = False
    summary = []
    for g in ("main", "lod1", "lod2"):
        rs = [x for x in rows if x["lod"] == g]
        if not rs:
            continue
        worst = max(rs, key=lambda x: x["hole_pct"])
        bad = [x for x in rs if x["hole_pct"] > LIMIT]
        small = [x for x in rs if 0 < x["hole_pct"] <= LIMIT]
        ok &= not bad
        if worst["hole_pct"] > MARGIN:
            marginal = True
        summary.append(f"{g} max {worst['hole_pct']:.3f}% (az {worst['az']:.0f}, el {worst['el']:+.0f}) bad_views {len(bad)}/{len(rs)}")
        for x in sorted(bad, key=lambda x: -x["hole_pct"])[:6]:
            print(f"  HOLE {g} az {x['az']:5.1f} el {x['el']:+5.1f}  {x['hole_pct']:.3f}%  ({x['hole_px']} px)")
            for p in x.get("where", []):
                print_where(p, shift)
        for x in sorted(small, key=lambda x: -x["hole_pct"])[:3]:
            print(f"  HOLE_SMALL {g} az {x['az']:5.1f} el {x['el']:+5.1f}  {x['hole_pct']:.3f}%  ({x['hole_px']} px)")
            for p in x.get("where", []):
                print_where(p, shift)
    # 텍스처: 게임은 메시 이름으로 <메시>_<맵>.png 를 찾는다. LOD 에 자기 이름의 맵이 없으면 유리처럼(투명) 그려진다
    # (사용자 확인: 키트가 LOD1 맵을 안 만들어 중간 거리에서 벽이 비친 적이 있음)
    adir = os.path.dirname(path)
    for mesh in (name, name + "_LOD1", name + "_LOD2"):
        if not os.path.exists(os.path.join(adir, mesh + ".fbx")):
            continue
        miss = [k for k in ("BaseColor", "ControlMask", "MaskMap", "Normal", "Emissive")
                if not os.path.exists(os.path.join(adir, f"{mesh}_{k}.png"))]
        if miss:
            ok = False
            print(f"  NO_TEXTURE {mesh}: {', '.join(miss)} missing (copy the main maps under this name)")
    verdict = ("QUICK " + ("ok" if ok else "bad")) if a.quick else ("PASS" if ok else "FAIL")
    if marginal and not a.quick:
        print(f"  WARN LOD main/LOD margin is above {MARGIN:.2f}% but below the {LIMIT:.2f}% limit")
    print(f"LODCHECK {verdict} " + " | ".join(summary)
          + (" marginal=1" if marginal and not a.quick else "")
          + f"  -> {os.path.relpath(out, proj)}")


if __name__ == "__main__":
    main()
