# -*- coding: utf-8 -*-
"""
photo_check.py - compare the model with the reference photos (road view facades + satellite roof) and print numbers.

Needs `photo_refs.json` in the folder root (write it once; pixel coordinates are read with tools/sat_grid.py grid,
or in MS Paint - the bottom bar shows the pixel under the mouse):
{
  "satellite": {"file": "roof.png",
                "corners": [[x,y], [x,y], [x,y], [x,y]],      # building outline: front-left, front-right, back-right, back-left
                "m_per_px": 0.25},                            # optional (tools/sat_grid.py scale) -> absolute width/depth check
  "facades": [
    {"file": "front.jpg", "side": "front",                    # front | back | left | right (as the model faces: front = -Y)
     "corners": [[x,y], [x,y], [x,y], [x,y]]}                 # that whole wall: top-left, top-right, bottom-right, bottom-left
  ]                                                           # top = roof/parapet top, bottom = ground line
}

    python tools/photo_check.py output/<asset>              all refs in photo_refs.json
    python tools/photo_check.py output/<asset> --refs other.json

What it does
  satellite: warps the photo to a top view of the model footprint, compares width/depth ratio (and real size if m_per_px),
             overlays the model outline (red) on the photo.
  facade:    warps the photo wall to the model's elevation, measures the repeating floor pitch and window-bay pitch in the
             photo and in the model with the SAME method, and compares them (= floor count / bay count check).
Prints one line per check:  MATCH / MISMATCH / INFO.   Sheets: previews/photo_check/<name>.png  (photo | model | overlay)
Exit code 1 if any MISMATCH, 2 if a requested check could not run.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_texture import warp  # noqa: E402
from objio import load_asset  # noqa: E402
from render import Tex  # noqa: E402

from proj import ROOT, KIT, NAME  # noqa: E402,F401  (project folder; chdir done)
TOL_RATIO = 0.08      # 8 % size/ratio tolerance
TOL_FLOOR = 0.10      # 10 % floor pitch tolerance
TOL_BAY = 0.20        # 20 % bay pitch tolerance (info only, trees/balconies make it noisy)
PX_PER_M = 20
YAW = {"front": 0, "back": 180, "left": -90, "right": 90}


def p(s):
    sys.stdout.write(s.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def model_view(meshes, tex, yaw, pitch, box=None):
    from elevation_cache import model_crop
    return model_crop(meshes, tex, yaw, pitch, box=box), None


def extents(meshes, side):
    V = meshes["main"].verts
    w = V[:, 0].max() - V[:, 0].min()
    d = V[:, 1].max() - V[:, 1].min()
    h = V[:, 2].max()
    return (w if side in ("front", "back", "top") else d), (d if side == "top" else h)


def wall_measure(ref, meshes, side, manifest=None):
    wall_id = ref.get("wall_id")
    walls = ((manifest or {}).get("metadata") or {}).get("walls", {})
    wall = walls.get(wall_id, {}) if wall_id else {}
    if wall_id and not wall and not (ref.get("size_m") and ref.get("box")):
        raise KeyError(f"wall_id '{wall_id}' is absent from manifest.metadata.walls")
    if ref.get("size_m"):
        width, height = map(float, ref["size_m"])
    elif wall:
        width = float(wall.get("length_m", abs(wall.get("a1", 0) - wall.get("a0", 0))))
        height = float(wall.get("z1", 0) - wall.get("z0", 0))
    else:
        width, height = extents(meshes, side)
    box = ref.get("box") or wall.get("box")
    if box:
        box = list(map(float, box))
        shift = (manifest or {}).get("pivot_shift", [0.0, 0.0])
        box[0] += shift[0]; box[1] += shift[0]
        box[2] += shift[1]; box[3] += shift[1]
    return width, height, box


def wall_yaw(ref, side, manifest=None):
    if "yaw_deg" in ref:
        return float(ref["yaw_deg"])
    walls = ((manifest or {}).get("metadata") or {}).get("walls", {})
    wall = walls.get(ref.get("wall_id"), {})
    if "normal_deg" in wall:
        return 180.0 - float(wall["normal_deg"])
    return YAW[side]


def gray(im):
    return np.asarray(im.convert("L"), np.float32)


def edges(g, pct=85):
    """Strong edges after a light blur (ignores fine texture grain / photo noise)."""
    g = np.asarray(Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float32)
    gy, gx = np.gradient(g)
    m = np.hypot(gx, gy)
    return m > np.percentile(m, pct)


def period(profile, px_per_m, lo_m, hi_m):
    """Dominant repeat distance (m) of a 1-D profile via autocorrelation. None if no clear repeat."""
    x = profile - np.convolve(profile, np.ones(15) / 15, mode="same")
    x = x - x.mean()
    if np.std(x) < 1e-6:
        return None, 0.0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac /= ac[0]
    lo, hi = int(lo_m * px_per_m), min(len(ac) - 1, int(hi_m * px_per_m))
    if hi <= lo + 2:
        return None, 0.0
    seg = ac[lo:hi]
    k = int(np.argmax(seg))
    strength = float(seg[k])
    # prefer the shortest lag with a peak close to the best one (avoid picking 2x period)
    for j in range(1, len(seg) - 1):
        if seg[j] >= seg[j - 1] and seg[j] >= seg[j + 1] and seg[j] > 0.8 * strength:
            k = j
            break
    return (lo + k) / px_per_m, strength


def rows_profile(g):
    gy = np.abs(np.gradient(g, axis=0))
    c0, c1 = int(g.shape[1] * 0.1), int(g.shape[1] * 0.9)
    return gy[:, c0:c1].mean(1)


def cols_profile(g, z0=0.25, z1=0.9):
    gx = np.abs(np.gradient(g, axis=1))
    r0, r1 = int(g.shape[0] * (1 - z1)), int(g.shape[0] * (1 - z0))      # middle-upper part (skip ground floor, crown)
    return gx[r0:r1].mean(0)


def chamfer_score(model_edges, photo_edges, tol_px):
    """Share of model edge pixels that have a photo edge within tol_px."""
    if model_edges.sum() == 0:
        return 0.0
    pe = Image.fromarray((photo_edges * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * tol_px + 1))
    near = np.asarray(pe) > 0
    return float((near & model_edges).sum() / model_edges.sum())


def sheet(path, photo, model, overlay, lines):
    h = 420
    ims = [im.resize((max(1, int(im.size[0] * h / im.size[1])), h)) for im in (photo, model, overlay)]
    W = sum(i.size[0] for i in ims) + 20
    out = Image.new("RGB", (W, h + 22 + 16 * len(lines)), "white")
    x = 0
    for i, t in zip(ims, ("photo (warped)", "model", "overlay: red = model edges")):
        out.paste(i, (x, 22)); ImageDraw.Draw(out).text((x + 4, 4), t, fill=(0, 0, 0)); x += i.size[0] + 10
    for k, l in enumerate(lines):
        ImageDraw.Draw(out).text((6, h + 26 + 16 * k), l, fill=(160, 0, 0) if l.startswith("MISMATCH") else (0, 0, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path)


def overlay_img(photo, model_edge_mask):
    o = np.asarray(photo.convert("RGB")).copy()
    o[model_edge_mask] = (255, 0, 0)
    return Image.fromarray(o)


def verdict(name, a, b, tol, unit=""):
    if a is None or b is None:
        return f"INFO     {name}: photo {a} / model {b} (could not measure)"
    diff = (b - a) / a if a else 0
    tag = "MATCH   " if abs(diff) <= tol else "MISMATCH"
    return f"{tag} {name}: photo {a:.2f}{unit} / model {b:.2f}{unit} ({diff * 100:+.0f}%)"


def check_satellite(ref, meshes, tex, base, prepared=None):
    W, D = extents(meshes, "top")
    c = ref["corners"]
    if prepared is None:
        w, h = int(W * PX_PER_M), int(D * PX_PER_M)
        img = Image.open(os.path.join(base, ref["file"])).convert("RGB")
        photo = warp(img, [c[3], c[2], c[1], c[0]], w, h)        # back-left at top-left, front at the bottom
        model, _ = model_view(meshes, tex, 0, 90)
        model = model.resize((w, h))
    else:
        photo, model = prepared
    me = edges(gray(model), 88)
    pe = edges(gray(photo), 85)
    out = []
    side_px = lambda a, b: math.dist(c[a], c[b])
    pw, pd = (side_px(0, 1) + side_px(3, 2)) / 2, (side_px(0, 3) + side_px(1, 2)) / 2
    out.append(verdict("satellite width/depth ratio", pw / pd, W / D, TOL_RATIO))
    if ref.get("m_per_px"):
        mpp = float(ref["m_per_px"])
        out.append(verdict("satellite width", pw * mpp, W, TOL_RATIO, " m"))
        out.append(verdict("satellite depth", pd * mpp, D, TOL_RATIO, " m"))
    out.append(f"INFO     satellite outline/edge agreement {chamfer_score(me, pe, 6) * 100:.0f}% (higher = roof layout lines up)")
    sheet(os.path.join(ROOT, "previews", "photo_check", "satellite.png"), photo, model, overlay_img(photo, me), out)
    return out


def check_facade(ref, meshes, tex, base, prepared=None, manifest=None):
    side = ref.get("side", "front")
    Wm, Hm, box = wall_measure(ref, meshes, side, manifest)
    if prepared is None:
        w, h = int(Wm * PX_PER_M), int(Hm * PX_PER_M)
        img = Image.open(os.path.join(base, ref["file"])).convert("RGB")
        photo = warp(img, ref["corners"], w, h)
        model, _ = model_view(meshes, tex, wall_yaw(ref, side, manifest), 0, box=box)
        model = model.resize((w, h))
    else:
        photo, model = prepared
    gp, gm = gray(photo), gray(model)
    out = []
    fp, sp = period(rows_profile(gp), PX_PER_M, 1.2, 6.5)
    fm, sm = period(rows_profile(gm), PX_PER_M, 1.2, 6.5)
    line = verdict(f"{side} floor pitch", fp, fm, TOL_FLOOR, " m")
    if fp and fm:
        if abs(fm - fp) / fp > TOL_FLOOR:
            line += f"  -> photo shows ~{Hm / fp:.0f} floor bands over the wall height, model ~{Hm / fm:.0f}" + \
                    (" (model needs MORE floors or lower floor height)" if fp < fm else " (model needs FEWER floors or taller floors)")
        if min(sp, sm) < 0.15:
            line = line.replace("MISMATCH", "INFO    ") + " (weak pattern in photo or model - LOW_CONFIDENCE, check by eye)"
        if ref.get("confidence") == "low":
            line = line.replace("MISMATCH", "INFO    ") + " (low-confidence photo evidence - do not auto-change floors)"
    out.append(line)
    bp, sbp = period(cols_profile(gp), PX_PER_M, 1.5, 12.0)
    bm, _ = period(cols_profile(gm), PX_PER_M, 1.5, 12.0)
    l2 = verdict(f"{side} window bay pitch", bp, bm, TOL_BAY, " m")
    out.append(l2.replace("MISMATCH", "INFO    ") + ("  (bays differ - check window columns)" if "MISMATCH" in l2 else ""))
    me = edges(gm, 88)
    out.append(f"INFO     {side} edge agreement {chamfer_score(me, edges(gp, 85), 5) * 100:.0f}%")
    sheet(os.path.join(ROOT, "previews", "photo_check", f"facade_{side}.png"), photo, model, overlay_img(photo, me), out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--refs", default=os.path.join(ROOT, "photo_refs.json"))
    a = ap.parse_args()
    if not os.path.exists(a.refs):
        p(f"[photo] no {os.path.basename(a.refs)} - skipped (see tools/photo_check.py header to create it)")
        return
    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    total = int(bool(refs.get("satellite"))) + len(refs.get("facades", []))
    if total == 0:
        p("[photo] FAIL: photo_refs.json contains no satellite or facade checks")
        sys.exit(2)
    base = os.path.dirname(os.path.abspath(a.refs))
    asset, meshes, texdir, manifest = load_asset(a.path)
    tex = Tex(texdir, asset, False, "color")
    lines = []
    failed = []
    if refs.get("satellite"):
        try:
            lines += check_satellite(refs["satellite"], meshes, tex, base)
        except Exception as e:  # noqa
            failed.append("satellite")
            lines.append(f"INFO     satellite check failed: {e}")
    for ref in refs.get("facades", []):
        try:
            lines += check_facade(ref, meshes, tex, base, manifest=manifest)
        except Exception as e:  # noqa
            failed.append(str(ref.get("side")))
            lines.append(f"INFO     facade {ref.get('side')} check failed: {e}")
    for l in lines:
        p("   " + l)
    n = sum(l.startswith("MISMATCH") for l in lines)
    p(f"[photo] {n} mismatch(es), checks {total - len(failed)}/{total}, failed {len(failed)}. Sheets: previews/photo_check/")
    sys.exit(2 if failed else 1 if n else 0)


if __name__ == "__main__":
    main()
