# -*- coding: utf-8 -*-
"""
tile_compare.py - tile-by-tile comparison of the model with the reference photos (finds where the model is too SIMPLE).

    python tools/tile_compare.py output/<asset>                 all facades + satellite in photo_refs.json
    python tools/tile_compare.py output/<asset> --tile-m 8x6    tile size in metres (width x height; facade default 10x9, roof 15x15)
    python tools/tile_compare.py output/<asset> --top 8         list the 8 worst tiles per wall
    python tools/tile_compare.py output/<asset> --ppm 30        pixels per metre of the warped photo (default 30)

For every wall it warps the photo to the model's elevation (same corners as photo_check), renders the model with the same
extents, cuts both into tiles and measures edges:
    recall     share of PHOTO edges that have a MODEL edge nearby   -> low = the model is missing detail (too simple)
    precision  share of MODEL edges that have a PHOTO edge nearby   -> low = the model has lines the photo does not (wrong place)
Output
    previews/tiles/<side>_map.png            heat map of the wall (green = good, red = missing detail) with tile ids r<row>c<col>
    previews/tiles/<side>/r02c03.png         photo | model | overlay (blue = photo edges, red = model edges) for the worst tiles
    lines:  TILE front r2c3 x[20,30]m z[9,18]m recall 38% precision 61%  SIMPLIFIED
            DETAIL front recall 64% precision 72% worst r2c3 (38%)
Numbers are a guide: trees, shadows and perspective lower them on real photos. Open the worst tiles and LOOK at them.
Colour: per-tile median colour of photo vs model (overall exposure matched) -> COLOR lines with both hex values, tiles with
dE > 14 are COLOR_OFF; ZONES lines list paint bands by height (rows) and by width (cols) for photo and model.
Before modelling:  python tools/tile_compare.py --photo-zones front:60x45   (bands + colours of the photo wall only)
Scores are advisory; exit code 2 means a requested comparison could not run.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_texture import warp  # noqa: E402
from objio import load_asset  # noqa: E402
from photo_check import YAW, dilate, edges, extents, gray, save_image  # noqa: E402
from render import Tex  # noqa: E402

from proj import ROOT, KIT, NAME  # noqa: E402,F401  (project folder; chdir done)
COLOR_OFF = 14.0       # Lab distance above which a tile's paint colour is called wrong (relative to the whole wall)
RECALL_LOW = 0.50      # a tile whose photo edges are explained less than this is called SIMPLIFIED


def p(s):
    sys.stdout.write(s.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def model_crop(meshes, tex, yaw, pitch, size, box=None):
    from elevation_cache import model_crop as cached_crop
    return cached_crop(meshes, tex, yaw, pitch, size, box=box)


def near(mask, tol):
    return dilate(mask, tol)


def score(pe, me, tol):
    """recall: photo edges with a model edge nearby; precision: model edges with a photo edge nearby."""
    rec = float((pe & near(me, tol)).sum() / max(pe.sum(), 1))
    pre = float((me & near(pe, tol)).sum() / max(me.sum(), 1))
    return rec, pre


def colour(r):
    r = max(0.0, min(1.0, (r - 0.25) / 0.6))
    return (int(220 * (1 - r) + 40 * r), int(60 * (1 - r) + 180 * r), 60)


def to_lab(rgb):
    """sRGB 0..255 (...,3) -> CIE Lab (D65)."""
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = (c @ M.T) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def hexc(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(float(v))))) for v in c)


def zones(arr, ppm, axis, min_len_m, jump=9.0):
    """Colour bands along a wall. axis 'z': horizontal bands (paint stripes by height); 'x': vertical bands.
    Returns [(from_m, to_m, hex)] from the median colour of every row / column."""
    H, W = arr.shape[:2]
    prof = np.median(arr, axis=1) if axis == "z" else np.median(arr, axis=0)     # (n,3)
    n = len(prof)
    lab = to_lab(prof)
    w = max(2, int(0.4 * ppm))
    k = max(1, int(0.15 * ppm))
    lab = np.stack([np.convolve(lab[:, i], np.ones(k) / k, mode="same") for i in range(3)], 1)
    cut = [0]
    ml = int(min_len_m * ppm)
    # Colour step at every position from prefix sums (one pass) instead of two slice means per position.
    # It only nominates candidates (with a safety margin); each one is re-tested with the exact slice
    # means below, so the cuts are the same as a plain position-by-position scan.
    idx = np.arange(max(ml, 1), max(n - ml, max(ml, 1)))
    if len(idx):
        ps = np.concatenate((np.zeros((1, 3)), np.cumsum(lab, 0)))
        lo, hi = np.maximum(idx - w, 0), np.minimum(idx + w, n)
        step = np.linalg.norm((ps[idx] - ps[lo]) / (idx - lo)[:, None] - (ps[hi] - ps[idx]) / (hi - idx)[:, None], axis=1)
        cand = idx[step > jump - 1e-6]
    else:
        cand = idx
    i = ml
    while i < n - ml:
        k = int(np.searchsorted(cand, i))
        if k == len(cand):
            break
        i = int(cand[k])
        a, b = lab[max(0, i - w):i].mean(0), lab[i:i + w].mean(0)
        if np.linalg.norm(a - b) > jump and i - cut[-1] >= ml:
            # move to the strongest change within +-w/2
            j = i
            best = 0
            for q in range(max(cut[-1] + ml, i - w // 2), min(n - ml, i + w // 2) + 1):
                d = np.linalg.norm(lab[max(0, q - w // 2):q].mean(0) - lab[q:q + w // 2].mean(0))
                if d > best:
                    best, j = d, q
            cut.append(j)
            i = j + ml
        else:
            i += 1
    cut.append(n)
    out = []
    for s, e in zip(cut[:-1], cut[1:]):
        m = max(1, int((e - s) * 0.15))
        col = np.median(prof[s + m:max(s + m + 1, e - m)], axis=0)
        if axis == "z":
            out.append((round((n - e) / ppm, 1), round((n - s) / ppm, 1), hexc(col)))
        else:
            out.append((round(s / ppm, 1), round(e / ppm, 1), hexc(col)))
    if axis == "z":
        out.reverse()
    return out


def colour_sample(pa, ma, pe, box):
    x0, y0, x1, y1 = box
    ps = pa[y0:y1, x0:x1].reshape(-1, 3)
    ms = ma[y0:y1, x0:x1].reshape(-1, 3)
    pm = np.median(ps, 0)
    mm = np.median(ms, 0)
    vegetation = ((ps[:, 1] > ps[:, 0] * 1.08) & (ps[:, 1] > ps[:, 2] * 1.08)).mean()
    mixed = float(np.std(ps)) > 55.0 or vegetation > 0.20 or pe[y0:y1, x0:x1].mean() > 0.35
    return pm, mm, not mixed


def run_wall(name, photo, model, ppm, tile_m, top, outdir, wall_w_m, wall_h_m):
    gp, gm = gray(photo), gray(model)
    pe, me = edges(gp, 85), edges(gm, 85)
    tol = max(3, int(0.15 * ppm))                     # 15 cm
    tw, th = int(tile_m[0] * ppm), int(tile_m[1] * ppm)
    W, H = photo.size
    cols, rows = max(1, round(W / tw)), max(1, round(H / th))
    tw, th = W / cols, H / rows
    res = []
    for r in range(rows):
        for c in range(cols):
            x0, x1, y0, y1 = int(c * tw), int((c + 1) * tw), int(r * th), int((r + 1) * th)
            if pe[y0:y1, x0:x1].sum() < 30:
                res.append((r, c, None, None, (x0, y0, x1, y1))); continue
            rec, pre = score(pe[y0:y1, x0:x1], me[y0:y1, x0:x1], tol)
            res.append((r, c, rec, pre, (x0, y0, x1, y1)))
    good = [t for t in res if t[2] is not None]
    wr = float(np.mean([t[2] for t in good])) if good else 0.0
    wp = float(np.mean([t[3] for t in good])) if good else 0.0
    worst = sorted(good, key=lambda t: t[2])
    # heat map
    scale = 720 / max(W, H)
    hm = photo.resize((max(1, int(W * scale)), max(1, int(H * scale)))).convert("RGB")
    ov = Image.new("RGB", hm.size)
    d = ImageDraw.Draw(ov)
    for r, c, rec, pre, (x0, y0, x1, y1) in res:
        if rec is not None:
            d.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], fill=colour(rec))
    hm = Image.blend(hm, ov, 0.45)
    d = ImageDraw.Draw(hm)
    for r, c, rec, pre, (x0, y0, x1, y1) in res:
        d.rectangle([x0 * scale, y0 * scale, x1 * scale, y1 * scale], outline=(255, 255, 255))
        d.text((x0 * scale + 3, y0 * scale + 2), f"r{r}c{c}" + (f" {rec * 100:.0f}%" if rec is not None else ""), fill=(0, 0, 0))
    os.makedirs(outdir, exist_ok=True)
    save_image(hm, os.path.join(os.path.dirname(outdir), f"{name}_map.png"))
    # tile sheets for the worst ones
    for r, c, rec, pre, (x0, y0, x1, y1) in worst[:top]:
        a, b = photo.crop((x0, y0, x1, y1)), model.crop((x0, y0, x1, y1))
        o = np.asarray(a).copy()
        o[near(pe[y0:y1, x0:x1], 1)] = (0, 90, 255)
        o[me[y0:y1, x0:x1]] = (255, 0, 0)
        ims = [a, b, Image.fromarray(o)]
        k = 440 / max(a.size[1], 1)
        ims = [i.resize((max(1, int(i.size[0] * k)), 440), Image.LANCZOS) for i in ims]
        sheet = Image.new("RGB", (sum(i.size[0] for i in ims) + 20, 462), "white")
        x = 0
        for i, t in zip(ims, ("photo", "model", "blue=photo edges red=model edges")):
            sheet.paste(i, (x, 22)); ImageDraw.Draw(sheet).text((x + 3, 5), t, fill=(0, 0, 0)); x += i.size[0] + 10
        save_image(sheet, os.path.join(outdir, f"r{r:02d}c{c:02d}.png"))
    out = []
    for r, c, rec, pre, (x0, y0, x1, y1) in worst[:top]:
        xm0, xm1 = x0 / ppm, x1 / ppm
        zm0, zm1 = (H - y1) / ppm, (H - y0) / ppm
        tag = "  SIMPLIFIED" if rec < RECALL_LOW else ""
        axis = "x" if name != "satellite" else "x"
        vert = "z" if name != "satellite" else "y"
        out.append(f"TILE {name} r{r}c{c} {axis}[{xm0:.0f},{xm1:.0f}]m {vert}[{zm0:.0f},{zm1:.0f}]m recall {rec * 100:.0f}% precision {pre * 100:.0f}%{tag}")
    w = worst[0] if worst else None
    out.append(f"DETAIL {name} recall {wr * 100:.0f}% precision {wp * 100:.0f}%" +
               (f" worst r{w[0]}c{w[1]} ({w[2] * 100:.0f}%)" if w else "") +
               f" simplified_tiles {sum(1 for t in good if t[2] < RECALL_LOW)}/{len(good)}")

    # ---- colour (paint) comparison: per-tile median colour, photo vs model, after matching overall exposure/white balance
    pa, ma = np.asarray(photo, np.float32), np.asarray(model, np.float32)
    samples = []
    for r, c, rec, pre, box in res:
        pm, mm, trusted = colour_sample(pa, ma, pe, box)
        if trusted:
            samples.append((r, c, box, pm, mm))
    mixed_count = len(res) - len(samples)
    ratios = [mm / np.maximum(pm, 1.0) for _, _, _, pm, mm in samples]
    gain = np.median(np.array(ratios), 0) if ratios else np.ones(3)
    cres = []
    for r, c, (x0, y0, x1, y1), pm, mm in samples:
        de = float(np.linalg.norm(to_lab(np.clip(pm * gain, 0, 255)) - to_lab(mm)))
        cres.append((de, r, c, pm * gain, mm, (x0, y0, x1, y1)))
    cres.sort(key=lambda q: -q[0])
    off = sum(1 for q in cres if q[0] > COLOR_OFF)
    for de, r, c, pm, mm, (x0, y0, x1, y1) in cres[:min(top, 4)]:
        if de > COLOR_OFF * 0.6:
            tag = "  COLOR_OFF" if de > COLOR_OFF else ""
            out.append(f"COLOR {name} r{r}c{c} x[{x0 / ppm:.0f},{x1 / ppm:.0f}]m photo {hexc(pm)} model {hexc(mm)} dE {de:.0f}{tag} confidence=trusted")
    out.append(f"DETAIL_COLOR {name} tiles_off {off}/{len(cres)} (dE>{COLOR_OFF:.0f}; trusted tiles only)")
    out.append(f"INFO     {name} colour trusted {len(samples)}/{len(res)} mixed_or_occluded {mixed_count}")
    if name != "satellite":
        for lab_, ax, ml in (("rows z", "z", 1.2), ("cols x", "x", 2.0)):
            zp, zm_ = zones(pa, ppm, ax, ml), zones(ma, ppm, ax, ml)
            if len(zp) > 1 or len(zm_) > 1:
                f = lambda zz: " ".join(f"[{a:g},{b:g}]{h}" for a, b, h in zz)
                out.append(f"ZONES {name} {lab_} photo: {f(zp)}")
                out.append(f"ZONES {name} {lab_} model: {f(zm_)}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="")
    ap.add_argument("--photo-zones", default="", help="BEFORE modelling: <side>:<W>x<H> metres, e.g. front:60x45 -> paint bands + colours of that wall")
    ap.add_argument("--refs", default=os.path.join(ROOT, "photo_refs.json"))
    ap.add_argument("--tile-m", default="", help="WxH metres, e.g. 8x6")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--ppm", type=int, default=30)
    ap.add_argument("--render-size", type=int, default=2200)
    a = ap.parse_args()
    if not os.path.exists(a.refs):
        p("[tiles] no photo_refs.json - skipped")
        return
    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    base = os.path.dirname(os.path.abspath(a.refs))
    if a.photo_zones:
        side, sz = a.photo_zones.split(":")
        Wm, Hm = (float(v) for v in sz.lower().split("x"))
        ref = next((f for f in refs.get("facades", []) if f.get("side") == side), None)
        if ref is None:
            raise SystemExit(f"no facade '{side}' in {a.refs}")
        arr = np.asarray(warp(Image.open(os.path.join(base, ref["file"])).convert("RGB"), ref["corners"],
                              int(Wm * a.ppm), int(Hm * a.ppm)), np.float32)
        f = lambda zz: " ".join(f"[{x:g},{y:g}]{h}" for x, y, h in zz)
        p(f"   ZONES {side} rows z (height m, bottom first): {f(zones(arr, a.ppm, 'z', 1.2))}")
        p(f"   ZONES {side} cols x (width m, left to right): {f(zones(arr, a.ppm, 'x', 2.0))}")
        p("   (colours are the photo's median per band: shadows/white balance shift them - use as the starting paint colours, then check COLOR lines)")
        return
    if not a.path:
        raise SystemExit("give the asset folder, or use --photo-zones side:WxH")
    asset, meshes, texdir, _ = load_asset(a.path)
    tex = Tex(texdir, asset, False, "color")
    lines = []
    failed = []
    tiles_dir = os.path.join(ROOT, "previews", "tiles")
    jobs = []
    if refs.get("satellite"):
        jobs.append(("satellite", refs["satellite"]))
    for ref in refs.get("facades", []):
        jobs.append((ref.get("side", "front"), ref))
    for name, ref in jobs:
        try:
            img = Image.open(os.path.join(base, ref["file"])).convert("RGB")
            if name == "satellite":
                Wm, Hm = extents(meshes, "top")
                c = ref["corners"]
                w, h = int(Wm * a.ppm), int(Hm * a.ppm)
                photo = warp(img, [c[3], c[2], c[1], c[0]], w, h)
                model = model_crop(meshes, tex, 0, 90, a.render_size).resize((w, h))
                tm = (15, 15)
            else:
                Wm, Hm = extents(meshes, name)
                w, h = int(Wm * a.ppm), int(Hm * a.ppm)
                photo = warp(img, ref["corners"], w, h)
                model = model_crop(meshes, tex, YAW[name], 0, a.render_size).resize((w, h))
                tm = (10, 9)
            if a.tile_m:
                tm = tuple(float(t) for t in a.tile_m.lower().split("x"))
            lines += run_wall(name, photo, model, a.ppm, tm, a.top, os.path.join(tiles_dir, name), Wm, Hm)
        except Exception as e:  # noqa
            failed.append(name)
            lines.append(f"INFO tiles {name} failed: {e}")
    for l in lines:
        p("   " + l)
    p(f"[tiles] {len(failed)} failed check(s). Open only flagged maps and worst tiles in previews/tiles/")
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
