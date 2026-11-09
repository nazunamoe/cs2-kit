# -*- coding: utf-8 -*-
"""Generate LOD1/LOD2 candidates from the main mesh of an exported .blend, then check holes.

  python tools/lod_auto.py --project P --asset output/<asset> --check --json

The source .blend is not modified. The candidate is written to
output/<asset>/_lod_auto/<asset>_lod_auto.blend with objects
<asset>_lod_auto, <asset>_lod_auto_LOD1, <asset>_lod_auto_LOD2.
Use the result as a candidate for the generator; verify it with lod_check and in game.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402  (consumes --project and chdirs to the project)


BLENDER_SCRIPT = r'''import bpy, bmesh, json, os, sys

def arg(i):
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    return rest[i]

src, out, name, cand, lod1_ratio, lod2_tris, cap_bottom = (
    arg(0), arg(1), arg(2), arg(3), float(arg(4)), int(arg(5)), arg(6) == "1")
bpy.ops.wm.open_mainfile(filepath=src)

def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)

main = bpy.data.objects.get(name)
if main is None or main.type != "MESH":
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no mesh objects in " + src)
    main = max(meshes, key=tri_count)
for old_name in (name + "_LOD1", name + "_LOD2", cand + "_LOD1", cand + "_LOD2"):
    old = bpy.data.objects.get(old_name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
old_main = bpy.data.objects.get(cand)
if old_main and old_main is not main:
    bpy.data.objects.remove(old_main, do_unlink=True)
main.name = cand
main.data.name = cand

# keep the window meshes under the candidate name so lod_check does not pick a stale _Win as the base
for suffix in ("", "_LOD1", "_LOD2"):
    old = bpy.data.objects.get(name + suffix + "_Win")
    if old is None:
        continue
    win = old.copy()
    win.data = old.data.copy()
    win.name = cand + suffix + "_Win"
    win.data.name = cand + suffix + "_Win"
    for coll in old.users_collection:
        coll.objects.link(win)
    bpy.data.objects.remove(old, do_unlink=True)

main_tris = tri_count(main)
if main_tris < 3:
    raise SystemExit("main mesh has too few triangles")

capped = 0
if cap_bottom:
    bm = bmesh.new()
    bm.from_mesh(main.data)
    zmin = min(v.co.z for v in bm.verts)
    edges = [e for e in bm.edges if e.is_boundary and all(abs(v.co.z - zmin) < 1e-3 for v in e.verts)]
    if edges:
        capped = len(edges)
        bmesh.ops.holes_fill(bm, edges=edges, sides=0)
        bm.to_mesh(main.data)
        main.data.update()
    bm.free()
main_tris = tri_count(main)

def make_lod(suffix, ratio):
    dup = main.copy()
    dup.data = main.data.copy()
    dup.name = cand + suffix
    dup.data.name = cand + suffix
    for coll in main.users_collection:
        coll.objects.link(dup)
    bpy.ops.object.select_all(action="DESELECT")
    dup.select_set(True)
    bpy.context.view_layer.objects.active = dup
    mod = dup.modifiers.new("LOD", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = max(0.001, min(1.0, ratio))
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return dup

lod1 = make_lod("_LOD1", lod1_ratio)
lod2 = make_lod("_LOD2", min(1.0, (lod2_tris * 0.95) / float(main_tris)))
os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
result = {"main_tris": main_tris, "lod1_tris": tri_count(lod1), "lod2_tris": tri_count(lod2),
          "lod1_ratio": lod1_ratio, "lod2_target": lod2_tris, "out": out,
          "capped_edges": capped,
          "objects": [cand, cand + "_LOD1", cand + "_LOD2"]}
print("LOD_AUTO_DONE " + json.dumps(result))
'''


def display_path(path):
    try:
        return os.path.relpath(path, proj.ROOT).replace(os.sep, "/")
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")


def find_blender(explicit=""):
    if explicit:
        p = os.path.abspath(explicit)
        if os.path.isfile(p):
            return p
        raise SystemExit(f"--blender is not a file: {explicit}")
    saved = os.path.join(HERE, "blender_path.txt")
    try:
        with open(saved, encoding="utf-8") as f:
            p = f.read().strip()
        if p and os.path.isfile(p):
            return p
    except OSError:
        pass
    try:
        import run_blender
        p = run_blender.find_blender(verbose=False)
        if p:
            return p
    except Exception:
        pass
    return None


def resolve_asset(asset):
    path = asset if os.path.isabs(asset) else os.path.join(proj.ROOT, asset)
    if os.path.isdir(path):
        name = os.path.basename(os.path.normpath(path))
        preferred = os.path.join(path, name + ".blend")
        if os.path.isfile(preferred):
            return preferred
        blends = sorted(p for p in os.listdir(path) if p.lower().endswith(".blend"))
        if not blends:
            raise SystemExit(f"no .blend in {path} (run the generator with Blender first)")
        return os.path.join(path, blends[0])
    if not os.path.isfile(path):
        raise SystemExit(f"no such asset: {asset}")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asset", required=True, help="output/<asset> folder or .blend")
    ap.add_argument("--out", help="candidate folder (default: <asset folder>/_lod_auto)")
    ap.add_argument("--lod1-ratio", type=float, default=0.35, help="LOD1 triangle ratio (< 0.5)")
    ap.add_argument("--lod2-tris", type=int, default=500, help="LOD2 target triangle count")
    ap.add_argument("--blender", default="", help="Blender executable")
    ap.add_argument("--check", action="store_true", help="run lod_check --quick on the candidate")
    ap.add_argument("--check-full", action="store_true", help="run the full 64-view lod_check")
    ap.add_argument("--no-cap-bottom", action="store_true", help="do not fill open bottom boundary loops")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not (0.01 <= a.lod1_ratio < 0.5):
        raise SystemExit("--lod1-ratio must be between 0.01 and 0.5")
    if a.lod2_tris < 50:
        raise SystemExit("--lod2-tris must be at least 50")
    src = resolve_asset(a.asset)
    name = os.path.splitext(os.path.basename(src))[0]
    cand = name + "_lod_auto"
    out_dir = a.out or os.path.join(os.path.dirname(src), "_lod_auto")
    out_blend = os.path.join(out_dir, cand + ".blend")
    if os.path.abspath(out_blend) == os.path.abspath(src):
        raise SystemExit("candidate output would overwrite the source blend")

    blender = find_blender(a.blender)
    if not blender:
        raise SystemExit("Blender not found - run tools/run_blender.py --find or pass --blender")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(BLENDER_SCRIPT)
        script = f.name
    try:
        cmd = [blender, "--background", "--factory-startup", "--python", script, "--",
               src, out_blend, name, cand, str(a.lod1_ratio), str(a.lod2_tris),
               "0" if a.no_cap_bottom else "1"]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        try:
            os.remove(script)
        except OSError:
            pass
    marker = [line for line in (run.stdout or "").splitlines() if line.startswith("LOD_AUTO_DONE ")]
    if run.returncode != 0 or not marker:
        tail = "\n".join(((run.stdout or "") + (run.stderr or "")).splitlines()[-8:])
        raise SystemExit("Blender LOD build failed:\n" + tail)
    result = json.loads(marker[-1][len("LOD_AUTO_DONE "):])
    result.update({"status": "OK", "source": display_path(src),
                   "candidate": display_path(out_blend),
                   "blender": blender, "cap_bottom": not a.no_cap_bottom})
    if result["lod1_tris"] >= result["main_tris"] * 0.5:
        result["status"] = "WARN"
        result["warning"] = "LOD1 is not below 50% of main"
    if result["lod2_tris"] > 500:
        result["status"] = "WARN"
        result.setdefault("warning", "")
        result["warning"] = (result["warning"] + "; " if result["warning"] else "") + "LOD2 is above 500 tris"

    if a.check or a.check_full:
        check = [sys.executable, os.path.join(HERE, "qa", "lod_check.py"), out_blend]
        if a.check and not a.check_full:
            check.append("--quick")
        r = subprocess.run(check, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [line for line in (r.stdout or "").splitlines() if "LODCHECK" in line]
        result["check"] = {"line": lines[-1] if lines else None, "returncode": r.returncode}
        if a.check_full and "LODCHECK PASS" not in (lines[-1] if lines else ""):
            result["status"] = "WARN"
        if a.check and not a.check_full and "ok" not in (lines[-1] if lines else "").lower():
            result["status"] = "WARN"

    if a.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"[lod_auto] {result['candidate']}")
        print(f"  main {result['main_tris']}  LOD1 {result['lod1_tris']}  LOD2 {result['lod2_tris']}")
        if result.get("check"):
            print(f"  check: {result['check']['line']}")
        if result.get("warning"):
            print(f"  WARN {result['warning']}")
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
