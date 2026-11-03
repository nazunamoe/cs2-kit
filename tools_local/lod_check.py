"""LOD 투명(구멍) 검사 — 게임처럼 뒷면을 그리지 않을 때 메인/LOD1/LOD2 에서 건물 안쪽 뒷면이 비치는 곳
(앞면이 빠졌거나 뒤집힌 곳 = 게임에서 "투명해 보이는" 곳)을 여러 각도에서 잰다. LOD 는 메인도 막혀 있는 자리만 센다.

키트 밖 도구(tools_local/). cycle.py 다음에, 보고 전에 매번 돌린다.
  python tools_local/lod_check.py output/<asset>                # 활성 프로젝트 기준 경로
  python tools_local/lod_check.py output/<asset> --az 16 --elev -10,5,25,50 --res 512

출력: previews/lod_check/<asset>/  (구멍이 보인 각도마다 그림: 회색 = 메인만, 흰색 = LOD 도 있음, 빨강 = 구멍)
마지막 줄: LODCHECK PASS|FAIL lod1 max X% (az, el) lod2 max Y% ...   기준: 각 각도 구멍 0.05% 이하 = PASS
"""
import argparse, json, os, subprocess, sys, glob

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 0.05


def blender_exe():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    p = os.path.join(KIT, "tools", "blender_path.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return "blender"


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("asset", help="output/<asset> (폴더) 또는 .blend")
    ap.add_argument("--az", type=int, default=16, help="방위각 개수 (기본 16 = 22.5도 간격)")
    ap.add_argument("--elev", default="-10,5,25,50", help="올려다봄(-)·내려다봄(+) 각도들")
    ap.add_argument("--res", type=int, default=512)
    a = ap.parse_args()

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
    cmd = [blender_exe(), "-b", path, "-P", os.path.join(KIT, "tools_local", "lod_check_bl.py"), "--",
           out, str(a.res), str(a.az), a.elev]
    for _ in range(2):                                 # once more on a one-off Blender failure (file still being written)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if "LODCHECK_DONE" in r.stdout:
            break
    if "LODCHECK_DONE" not in r.stdout:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit("[lod_check] Blender run failed")
    rows = json.load(open(os.path.join(out, "lod_check.json"), encoding="utf-8"))["rows"]
    man = os.path.join(os.path.dirname(path), "manifest.json")
    shift = (0.0, 0.0)
    if os.path.exists(man):                            # kit 이 피벗을 바닥 가운데로 옮긴 양
        shift = tuple(json.load(open(man, encoding="utf-8")).get("pivot_shift", (0.0, 0.0)))
    ok = True
    summary = []
    for g in ("main", "lod1", "lod2"):
        rs = [x for x in rows if x["lod"] == g]
        if not rs:
            continue
        worst = max(rs, key=lambda x: x["hole_pct"])
        bad = [x for x in rs if x["hole_pct"] > LIMIT]
        ok &= not bad
        summary.append(f"{g} max {worst['hole_pct']:.3f}% (az {worst['az']:.0f}, el {worst['el']:+.0f}) bad_views {len(bad)}/{len(rs)}")
        for x in sorted(bad, key=lambda x: -x["hole_pct"])[:6]:
            print(f"  HOLE {g} az {x['az']:5.1f} el {x['el']:+5.1f}  {x['hole_pct']:.3f}%  ({x['hole_px']} px)")
            for p in x.get("where", []):
                # 비쳐 보이는 뒷면의 위치: 내보낸 좌표(xyz)와 생성기 좌표(gen = xyz - pivot_shift), 그 면의 법선
                gx = [p["xyz"][0] - shift[0], p["xyz"][1] - shift[1], p["xyz"][2]]
                print(f"      at gen ({gx[0]:.2f}, {gx[1]:.2f}, {gx[2]:.2f})  normal {tuple(p['normal'])}  {p['px']} px  [{p['obj']}]")
    # 텍스처: 게임은 메시 이름으로 <메시>_<맵>.png 를 찾는다. LOD 에 자기 이름의 맵이 없으면 유리처럼(투명) 그려진다
    # (2026-10-31, photos/trans.png: 키트가 LOD1 맵을 안 만들어 중간 거리에서 벽이 비침)
    adir = os.path.dirname(path)
    for mesh in (name, name + "_LOD1", name + "_LOD2"):
        if not os.path.exists(os.path.join(adir, mesh + ".fbx")):
            continue
        miss = [k for k in ("BaseColor", "ControlMask", "MaskMap", "Normal", "Emissive")
                if not os.path.exists(os.path.join(adir, f"{mesh}_{k}.png"))]
        if miss:
            ok = False
            print(f"  NO_TEXTURE {mesh}: {', '.join(miss)} missing (copy the main maps under this name)")
    print(f"LODCHECK {'PASS' if ok else 'FAIL'} " + " | ".join(summary) + f"  -> {os.path.relpath(out, proj)}")


if __name__ == "__main__":
    main()
