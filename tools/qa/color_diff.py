"""Photo colour vs model material: list the places where the photo shows a colour that the model does not paint there.

Finds photo pixels of one colour class (tan, white, dark, bluegrey), casts them into the asset with tools/qa/probe.py, and compares the
colour class of the material that is hit. The material colour is read from the asset's BaseColor atlas (median of each atlas cell),
so nothing is hard-coded per building. Mismatches are grouped by wall normal, position along the wall and material:

  python tools/qa/color_diff.py --project P --shot 103_side15.png --frame work/frame_103.json --color tan
  python tools/agent.py colordiff --project P --shot 103_side15.png --frame work/frame_103.json --color tan --json

Read the result as "photo shows COLOR at generator xyz / along-wall position, the model has MATERIAL there". Several shots of the same
wall (high and low) confirm each other; a group with 1-2 hits is usually shading or an edge, so --min-hits (default 3) hides it.
Rotated parts are reported in generator xyz with the wall normal, not in the part's local coordinates (see probe.py).
The model-has-colour-but-photo-does-not direction is not checked. Photo background (near white) is ignored.
tan is the class that was validated (brown piers/panels); dark and white are coarse (dark mostly finds window glass), use them with a high --min-hits.

Options
  --shot NAME     photo in photos/ (tower number = part before the first underscore)
  --frame FILE    scan frame json (104: work/frame_104_gen.json)
  --color NAME    tan | white | dark | bluegrey (default tan)
  --rows N        sample a pixel row every N px (default 50); --min-run W minimum run width in px (default 4)
  --min-hits K    hide mismatch groups with fewer hits (default 3)
  --asset PATH    output/<asset> folder or .blend; --meta FILE  VR meta json
  --json          machine-readable result
"""
import argparse
import glob
import json
import math
import os
import sys

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> kit root
sys.path.insert(0, os.path.join(KIT, "tools"))
sys.path.insert(0, os.path.join(KIT, "tools", "qa"))
import proj  # noqa: E402,F401  (work folder = the project)
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import probe  # noqa: E402


def _class_masks(r, g, b):
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    return {
        "tan": (r - b >= 20) & (r >= 100) & (r <= 210) & (r >= g) & (g >= b - 5),
        "white": (mn >= 185) & (mx - mn <= 22),
        "dark": mx <= 95,
        "bluegrey": (b >= r + 5) & (b >= g) & (mx >= 70) & (mx <= 200) & (mx - mn <= 60),
    }


def classify_rgb(rgb):
    """colour classes (set of names) that one RGB triple belongs to"""
    r, g, b = (np.array([float(c)]) for c in rgb)
    return {k for k, m in _class_masks(r, g, b).items() if bool(m[0])}


def region_classes(blend, cells):
    """atlas region name -> set of colour classes, from the median colour of the cell in the main BaseColor map"""
    adir = os.path.dirname(blend)
    maps = [f for f in glob.glob(os.path.join(adir, "*_BaseColor.png")) if "_LOD" not in os.path.basename(f)]
    if not maps:
        raise SystemExit("COLORDIFF FAIL no *_BaseColor.png next to the .blend (build final first)")
    atlas = np.array(Image.open(maps[0]).convert("RGB"))
    out = {}
    for name, c in cells.items():
        x, y, w, h = c["rect"]
        patch = atlas[y:y + h, x:x + w].reshape(-1, 3)
        out[name] = classify_rgb(np.median(patch, axis=0)) if len(patch) else set()
    return out


def sample_pixels(photo_path, color, rows, min_run):
    im = np.array(Image.open(photo_path).convert("RGB")).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    fg = ~((r >= 240) & (g >= 240) & (b >= 240))                 # photo background is near white
    mask = _class_masks(r, g, b)[color] & fg
    ys = np.nonzero(mask.any(axis=1))[0]
    if not len(ys):
        return []
    pts = []
    for y in range(int(ys.min()) + 20, int(ys.max()) - 20, rows):
        xs = np.nonzero(mask[y])[0]
        if not len(xs):
            continue
        brk = np.nonzero(np.diff(xs) > 2)[0]
        starts = np.concatenate([[xs[0]], xs[brk + 1]])
        ends = np.concatenate([xs[brk], [xs[-1]]])
        for s, e in zip(starts, ends):
            if e - s + 1 >= min_run:
                pts.append(((s + e) / 2.0, float(y)))
    return pts


def main():
    ap = argparse.ArgumentParser(description="photo colour vs model material mismatches", formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shot", required=True)
    ap.add_argument("--frame", required=True)
    ap.add_argument("--color", default="tan", choices=("tan", "white", "dark", "bluegrey"))
    ap.add_argument("--rows", type=int, default=50)
    ap.add_argument("--min-run", type=int, default=4)
    ap.add_argument("--min-hits", type=int, default=3)
    ap.add_argument("--asset", default="")
    ap.add_argument("--meta", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    photo = os.path.join("photos", a.shot)
    if not os.path.exists(photo):
        raise SystemExit("COLORDIFF FAIL no photo %s" % photo)
    pts = sample_pixels(photo, a.color, a.rows, a.min_run)
    if not pts:
        raise SystemExit("COLORDIFF FAIL no %s pixels found in %s" % (a.color, a.shot))
    rows, info = probe.probe_rows(a.shot, a.frame, pts, a.asset, a.meta)
    man = json.load(open(os.path.join(os.path.dirname(info["blend"]), "manifest.json"), encoding="utf-8"))
    classes = region_classes(info["blend"], (man.get("atlas") or {}).get("cells", {}))
    total = match = nohit = glass = 0
    groups = {}
    for row in rows:
        total += 1
        if not row["hit"]:
            nohit += 1
            continue
        if row["kind"] == "window":
            glass += 1
            continue
        if a.color in classes.get(row["region"], set()):
            match += 1
            continue
        n = row["normal"]
        nl = math.hypot(n[0], n[1]) or 1.0
        gx, gy, gz = row["generator_xyz"]
        along = (gx * (-n[1]) + gy * n[0]) / nl                    # position along the wall (tangent = (-ny, nx))
        key = (round(n[0], 1), round(n[1], 1), round(round(along * 4) / 4, 2), row["region"])
        g = groups.setdefault(key, dict(hits=0, z=[], gen=[]))
        g["hits"] += 1
        g["z"].append(gz)
        g["gen"].append((gx, gy))
    shown = []
    for (nx, ny, along, region), g in sorted(groups.items(), key=lambda kv: (-kv[1]["hits"], kv[0])):
        if g["hits"] < a.min_hits:
            continue
        gx = float(np.mean([p[0] for p in g["gen"]]))
        gy = float(np.mean([p[1] for p in g["gen"]]))
        shown.append(dict(normal=[nx, ny], along=along, model_region=region, model_classes=sorted(classes.get(region, set())),
                          hits=g["hits"], generator_xy=[round(gx, 2), round(gy, 2)], z_range=[round(min(g["z"]), 1), round(max(g["z"]), 1)]))
    result = dict(status="OK", shot=a.shot, asset=info["asset"], color=a.color, samples=total, matched=match, no_hit=nohit,
                  window_hits=glass, mismatch_hits=sum(g["hits"] for g in groups.values()), groups=shown)
    if a.json:
        print(json.dumps(result, ensure_ascii=False))
        return
    print("COLORDIFF %s %s color=%s: %d samples, %d match, %d mismatch, %d window, %d no hit"
          % (a.shot, info["asset"], a.color, total, match, result["mismatch_hits"], glass, nohit))
    if not shown:
        print("  no mismatch group with >= %d hits" % a.min_hits)
    for g in shown:
        print("  photo %s, model %s %s | wall normal %s along %.2f | generator xy (%.2f, %.2f) z %s..%s | %d hits"
              % (a.color, g["model_region"], g["model_classes"] or "?", tuple(g["normal"]), g["along"], g["generator_xy"][0],
                 g["generator_xy"][1], g["z_range"][0], g["z_range"][1], g["hits"]))


if __name__ == "__main__":
    main()
