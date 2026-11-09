"""Photo pixel -> model: which face, which material, which coordinate does this pixel of a VR photo land on?

Casts a ray (Blender, tools/qa/probe_bl.py) through the given pixels of a photo into the asset .blend, using the same camera as
tools/qa/cmp_cam.py --frame. LOD meshes are removed first. Use it before editing: it says where in the generator a photo detail is.

  python tools/qa/probe.py --project P --shot 101_side5.png --frame work/frame_101.json --px 2342,1293 --px 2125,1293
  python tools/agent.py probe --project P --shot 104_side9.png --frame work/frame_104_gen.json --frac 0.5,0.4

Output per pixel: object (main or window), atlas region (material), normal, asset xyz, generator xyz, distance, face area.
  asset xyz     = generator xyz + pivot_shift (what Blender holds)
  generator xyz = coordinates as written in the generator for unrotated parts
Parts the generator rotates (e.g. 101 wing, NE corner; 104 block B and C) are NOT converted to their local coordinates: use the
normal and generator xyz and undo the part's rot/move by hand.

Options
  --shot NAME     photo file inside photos/ (e.g. 101_side5.png); the tower number is the part before the first underscore
  --frame FILE    scan frame json (yaw, ox, oy, oz), required: 104 needs work/frame_104_gen.json
  --px X,Y        pixel in the ORIGINAL photo (repeatable). --frac FX,FY gives it as fractions of the width and height instead
  --asset PATH    output/<asset> folder or .blend (default: the single output/*Tower<NN>_* folder)
  --meta FILE     VR meta json (default photos/<NN>_meta.json)
  --json          one JSON list instead of text lines
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> kit root
sys.path.insert(0, os.path.join(KIT, "tools"))
sys.path.insert(0, os.path.join(KIT, "tools", "qa"))
import proj  # noqa: E402,F401  (work folder = the project)
from PIL import Image  # noqa: E402
import cmp_cam  # noqa: E402


def find_blend(asset, dong):
    if asset:
        blend = asset if asset.endswith(".blend") else (glob.glob(os.path.join(asset, "*.blend")) or [None])[0]
    else:
        folders = [d for d in glob.glob(os.path.join("output", "*Tower%s_*" % dong)) if os.path.isdir(d)] if dong else []
        if len(folders) != 1:
            raise SystemExit("PROBE FAIL cannot pick the asset (found %d output folders for tower %s); pass --asset" % (len(folders), dong))
        blend = (glob.glob(os.path.join(folders[0], "*.blend")) or [None])[0]
    if not blend or not os.path.exists(blend):
        raise SystemExit("PROBE FAIL no .blend for the asset (build final first)")
    return blend


def probe_rows(shot_name, frame, pixels, asset="", meta=""):
    """Cast rays through original-photo pixels. Returns (rows, info) with info = dict(W, H, blend, asset)."""
    dong = shot_name.split("_")[0]
    photo = os.path.join("photos", shot_name)
    if not os.path.exists(photo):
        raise SystemExit("PROBE FAIL no photo %s" % photo)
    W, H = Image.open(photo).size
    meta_path = meta or os.path.join("photos", "%s_meta.json" % dong)
    meta_d = json.load(open(meta_path, encoding="utf-8"))
    shot = next((s for s in meta_d["shots"] if s["file"] == shot_name), None)
    if shot is None:
        raise SystemExit("PROBE FAIL shot %s not in %s" % (shot_name, meta_path))
    blend = find_blend(asset, dong)
    man = json.load(open(os.path.join(os.path.dirname(blend), "manifest.json"), encoding="utf-8"))
    C = cmp_cam.frame_camera(frame, blend, meta_d, shot, W, H)
    req = dict(pos=C["pos"], target=C["target"], lens=C["lens"], W=W, H=H, pixels=[list(p) for p in pixels], pivot=C["pivot"],
               cells=(man.get("atlas") or {}).get("cells", {}))
    with tempfile.TemporaryDirectory() as tmp:
        rq = os.path.join(tmp, "request.json")
        with open(rq, "w", encoding="utf-8") as f:
            json.dump(req, f)
        r = subprocess.run([cmp_cam.blender_exe(), "-b", blend, "-P", os.path.join(KIT, "tools", "qa", "probe_bl.py"), "--", rq],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows = [json.loads(l[6:]) for l in r.stdout.splitlines() if l.startswith("PROBE ")]
    if len(rows) != len(pixels):
        raise SystemExit("PROBE FAIL blender returned %d of %d results: %s" % (len(rows), len(pixels), (r.stdout + r.stderr)[-500:]))
    return rows, dict(W=W, H=H, blend=blend, asset=os.path.basename(os.path.dirname(blend)))


def main():
    ap = argparse.ArgumentParser(description="photo pixel -> model face, material and coordinate",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shot", required=True)
    ap.add_argument("--frame", required=True)
    ap.add_argument("--px", action="append", default=[])
    ap.add_argument("--frac", action="append", default=[])
    ap.add_argument("--asset", default="")
    ap.add_argument("--meta", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    photo = os.path.join("photos", a.shot)
    if not os.path.exists(photo):
        raise SystemExit("PROBE FAIL no photo %s" % photo)
    W, H = Image.open(photo).size
    pixels = [tuple(float(v) for v in s.split(",")) for s in a.px]
    pixels += [(float(s.split(",")[0]) * W, float(s.split(",")[1]) * H) for s in a.frac]
    if not pixels:
        raise SystemExit("PROBE FAIL give at least one --px or --frac")
    rows, info = probe_rows(a.shot, a.frame, pixels, a.asset, a.meta)
    if a.json:
        print(json.dumps(dict(status="OK", shot=a.shot, asset=info["asset"], results=rows), ensure_ascii=False))
        return
    print("PROBE %s %s (%dx%d)" % (a.shot, info["asset"], W, H))
    for row in rows:
        if not row["hit"]:
            print("  px %s: no hit" % (row["px"],))
            continue
        print("  px %s: %s %s | normal %s | asset %s | generator %s | %.1f m | face %.2f m2"
              % (row["px"], row["kind"], row["region"], row["normal"], row["asset_xyz"], row["generator_xyz"], row["distance"], row["face_area"]))


if __name__ == "__main__":
    main()
