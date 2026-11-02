# -*- coding: utf-8 -*-
"""
facade_paint.py - generic: read floors, windows and PAINT (colour blocks) of a wall from a photo. No generator needed.

Works on one wall (or one section of a wall) that is described in photo_refs.json like a normal facade entry:
    {"file": "front.jpg", "side": "front", "name": "front_head",              # name optional (use it when one side has several photos)
     "corners": [[x,y],[x,y],[x,y],[x,y]],                                   # top-left, top-right, bottom-right, bottom-left of that wall part
     "size_m": [60, 45],                                                     # real size of that part (width, height). or x_m/z_m below
     "x_m": [0, 60], "z_m": [0, 45]}                                         # optional: where the part lies on the wall (default 0..width, 0..height)
If the entry has no size, give --wall-size WxH (metres).

    python tools/facade_paint.py all  --name front --fh 3.0 --feature-floor 29
    python tools/facade_paint.py floors   ...     only the floor rows + numbered picture (do this first, check the numbers by eye!)
    python tools/facade_paint.py windows  ...     + window list per wall (x, width, sill, head), special floors
    python tools/facade_paint.py paint    ...     + paint rectangles (pier / spandrel) per floor range, repeat rules, fit check
options
    --refs photo_refs.json   --name <name|side>   --wall-size WxH   --ppm 30 (px per m of the straightened photo)
    --fh 3.0                 floor height in m (hint for the floor search; default: found from the photo)
    --feature-floor N        the floor where the window pattern differs most (refuge floor, mechanical floor...) is floor N.
                             Floors are then numbered from it - this is the most reliable way, photo labels are often +-1 off.
    --first-floor N          number of the lowest floor row found (manual shift)
    --window-mode auto|dark|color:#hex[,#hex]   how windows are recognised (auto picks a colour cluster, see the printed table)
    --cell 0.25              paint grid cell width (m)       --list N  how many rules / rects to print (default 40)

Outputs (previews/facade/):  <name>_floors_N.png (photo + floor lines + numbers + window mask), <name>_paint_N.png
(photo | flat colour rectangles | difference), <name>.json (everything, for the generator tables).
Rules of thumb (learned the hard way): count floors from a feature floor, paint = a few LARGE rectangles + floor rules
(never per-cell colours), windows = one list per wall, the same on every floor except the feature floors.
Numbers help, eyes decide: open the pictures.
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from proj import ROOT, KIT, NAME  # noqa: E402,F401  (project folder; chdir done)
OUT = os.path.join(ROOT, "previews", "facade")


def p(s=""):
    sys.stdout.write(str(s).encode("ascii", "backslashreplace").decode("ascii") + "\n")


# ------------------------------------------------------------------ colour helpers
def to_lab(rgb):
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = (c @ M.T) / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def from_lab(lab):
    lab = np.asarray(lab, np.float64)
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    M = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = xyz @ M.T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(c * 255, 0, 255)


def hexc(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(float(v))))) for v in c)


def unhex(h):
    h = h.strip().lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


# ------------------------------------------------------------------ loading
def load_wall(a):
    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    items = refs.get("facades", [])
    pick = [e for e in items if a.name in (e.get("name"), e.get("side"))] if a.name else items
    if not pick:
        raise SystemExit(f"no facade '{a.name}' in {a.refs}")
    if len(pick) > 1:
        raise SystemExit("several entries match - use --name with the entry's own \"name\": " +
                         ", ".join(str(e.get("name") or e.get("side")) for e in pick))
    e = pick[0]
    x_m, z_m = e.get("x_m"), e.get("z_m")
    if e.get("size_m"):
        w, h = e["size_m"]
    elif a.wall_size:
        w, h = (float(t) for t in a.wall_size.lower().split("x"))
    elif x_m and z_m:
        w, h = x_m[1] - x_m[0], z_m[1] - z_m[0]
    else:
        raise SystemExit("size of the wall part unknown: add \"size_m\": [w, h] to the entry or use --wall-size WxH")
    x_m = x_m or [0.0, w]
    z_m = z_m or [0.0, h]
    ppm = float(a.ppm)
    ppm = min(ppm, math.sqrt(14e6 / (w * h)))
    W, H = int(round(w * ppm)), int(round(h * ppm))
    img = Image.open(os.path.join(os.path.dirname(os.path.abspath(a.refs)), e["file"])).convert("RGB")
    arr = np.asarray(warp(img, [tuple(c) for c in e["corners"]], W, H), np.float32)
    name = str(e.get("name") or e.get("side") or "wall")
    return dict(name=name, arr=arr, ppm=ppm, W=W, H=H, w=w, h=h, x0=float(x_m[0]), z1=float(z_m[1]), z0=float(z_m[0]), entry=e)


def row_z(wall, r):
    return wall["z1"] - (r + 0.5) / wall["ppm"]


def col_x(wall, c):
    return wall["x0"] + (c + 0.5) / wall["ppm"]


# ------------------------------------------------------------------ floors
def autocorr_period(prof, ppm, lo_m, hi_m):
    k = max(3, int(ppm * 0.6)) | 1
    x = prof - np.convolve(prof, np.ones(k) / k, mode="same")
    x = x - x.mean()
    if np.std(x) < 1e-9:
        return None, 0.0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac /= ac[0]
    lo, hi = int(lo_m * ppm), min(len(ac) - 2, int(hi_m * ppm))
    if hi <= lo + 2:
        return None, 0.0
    seg = ac[lo:hi]
    best = float(seg.max())
    j0 = int(np.argmax(seg))
    for j in range(1, len(seg) - 1):                       # shortest strong peak (avoid 2x period)
        if seg[j] >= seg[j - 1] and seg[j] >= seg[j + 1] and seg[j] > 0.85 * best:
            j0 = j
            break
    k0 = lo + j0
    y0, y1, y2 = ac[k0 - 1], ac[k0], ac[k0 + 1]
    d = y0 - 2 * y1 + y2
    if d != 0:
        k0 = k0 + 0.5 * (y0 - y2) / d
    return k0 / ppm, best


def find_floors(wall, fh_hint):
    arr, ppm, H, W = wall["arr"], wall["ppm"], wall["H"], wall["W"]
    g = arr.mean(2)
    c0, c1 = int(W * 0.05), int(W * 0.95)
    ref = np.percentile(g[:, c0:c1], 85, axis=1, keepdims=True)
    dark = np.maximum(ref - g[:, c0:c1], 0).mean(1) / 255.0
    grad = np.abs(np.gradient(g[:, c0:c1], axis=0)).mean(1) / 255.0
    lo, hi = (fh_hint * 0.75, fh_hint * 1.3) if fh_hint else (2.2, 4.6)
    cands = []
    for nm, prof in (("dark", dark), ("grad", grad)):
        per, st = autocorr_period(prof, ppm, lo, hi)
        if per:
            cands.append((st, per, nm, prof))
    if not cands:
        raise SystemExit("no repeating floor pattern found - check the corners in photo_refs.json (whole wall part, top to bottom)")
    st, pitch_m, nm, prof = max(cands, key=lambda t: t[0])
    pitch = pitch_m * ppm
    sm = np.convolve(dark, np.ones(max(3, int(ppm * 0.15))) / max(3, int(ppm * 0.15)), mode="same")
    # comb fit: phase maximising the sum of the dark profile at k*pitch + phase
    best_ph, best_s = 0.0, -1
    for ph in np.arange(0, pitch, 1.0):
        idx = np.round(ph + np.arange(0, (H - ph) // pitch + 1) * pitch).astype(int)
        idx = idx[idx < H]
        s = sm[idx].mean() if len(idx) else -1
        if s > best_s:
            best_s, best_ph = s, ph
    centres = []
    y = best_ph
    while y < H:
        a0, a1 = int(max(0, y - 0.22 * pitch)), int(min(H, y + 0.22 * pitch))
        if a1 - a0 > 3:
            loc = a0 + int(np.argmax(sm[a0:a1]))
            found = sm[loc] > 0.5 * np.median(sm[np.round(np.arange(best_ph, H, pitch)).astype(int).clip(0, H - 1)])
            centres.append((float(loc if found else y), bool(found)))
        y += pitch
    # keep floors fully inside the part
    centres = [(c, f) for c, f in centres if 0 <= c <= H]       # 1st pass: keep partly cut floors, 2nd pass (refine_floors) trims
    centres.sort(key=lambda t: -t[0])                       # bottom (large row) first
    return dict(pitch_m=pitch_m, pitch_px=pitch, strength=st, source=nm, centres=centres)


# ------------------------------------------------------------------ band stack + windows
NY = 60


def band_stack(wall, fl):
    """(K, NY, W, 3): every floor's band resampled to NY rows (top of band first)."""
    arr, H = wall["arr"], wall["H"]
    pitch = fl["pitch_px"]
    out = []
    for c, _ in fl["centres"]:
        ys = np.linspace(c - pitch / 2, c + pitch / 2, NY, endpoint=False)
        ys = np.clip(ys, 0, H - 1)
        y0 = np.floor(ys).astype(int)
        y1 = np.clip(y0 + 1, 0, H - 1)
        t = (ys - y0)[:, None, None]
        out.append(arr[y0] * (1 - t) + arr[y1] * t)
    return np.stack(out)


def colprofile(mask_k, lo=0.25, hi=0.75):
    return mask_k[int(NY * lo):int(NY * hi)].mean(0)


def runs_of(b, min_len):
    out, k = [], 0
    while k < len(b):
        if b[k]:
            j = k
            while j < len(b) and b[j]:
                j += 1
            if j - k >= min_len:
                out.append((k, j))
            k = j
        else:
            k += 1
    return out


def kmeans_lab(lab, k, seed=1, iters=14, restarts=3):
    best, best_in = None, 1e30
    for r in range(restarts):
        rng = np.random.default_rng(seed + r)
        cen = lab[rng.choice(len(lab), size=k, replace=False)].copy()
        for _ in range(iters):
            d = ((lab[:, None, :] - cen[None]) ** 2).sum(-1)
            la = d.argmin(1)
            for j in range(k):
                if (la == j).any():
                    cen[j] = lab[la == j].mean(0)
        inertia = float(((lab - cen[la]) ** 2).sum())
        if inertia < best_in:
            best, best_in = cen, inertia
    return best


def mask_score(m, K, W):
    """how window-like is a bool mask (K, NY, W): repeats on every floor, several runs, fair coverage, COMPACT rectangles
    (narrower than the wall part, shorter than the floor band -> piers and spandrels do not count)"""
    cov = float(m.mean())
    prof = np.stack([colprofile(m[k]) for k in range(K)])
    nruns = float(np.mean([len(runs_of(prof[k] > 0.5, 2)) for k in range(K)]))
    if K > 1:
        cc = [np.corrcoef(prof[k], prof[k + 1])[0, 1] for k in range(K - 1) if prof[k].std() > 1e-6 and prof[k + 1].std() > 1e-6]
        cons = float(np.nanmean(cc)) if cc else 0.0
    else:
        cons = 0.5
    ok = 1.0 if 0.06 <= cov <= 0.6 else 0.3
    cf = m.mean(1)
    comp_k = []
    for k in range(K):
        tot = cf[k].sum()
        if tot <= 0:
            continue
        good = 0.0
        for a0, a1 in runs_of(cf[k] > 0.15, 2):
            ext = float(np.percentile(cf[k][a0:a1], 90))
            if (a1 - a0) < 0.35 * W and 0.12 < ext < 0.78:
                good += cf[k][a0:a1].sum()
        comp_k.append(good / tot)
    comp = float(np.mean(comp_k)) if comp_k else 0.0
    score = max(0.0, cons) * min(1.0, nruns / 3.0) * ok * comp
    return score, cov, nruns, cons, comp


def dark_mask(L, K):
    ref = np.percentile(L.reshape(K, -1), 85, axis=1)[:, None, None]
    return L < 0.62 * ref


def window_mask(S, wall, mode, quiet=False):
    """-> bool (K, NY, W), info string"""
    K, _, W, _ = S.shape
    L = S.mean(3)
    if mode == "dark":
        return (dark_mask(L, K)), "dark: luminance < 62% of the floor's bright wall"
    if mode.startswith("color:"):
        cols = [unhex(h) for h in mode[6:].split(",")]
        lab = to_lab(S)
        m = np.zeros(L.shape, bool)
        for c in cols:
            m |= np.linalg.norm(lab - to_lab(c), axis=-1) < 14
        return (m), "colour: " + mode[6:]
    # auto: candidates = colour clusters (single and greedy unions) and the 'dark' rule; the most window-like mask wins
    sub = S.reshape(-1, 3)
    rng = np.random.default_rng(2)
    sub = sub[rng.choice(len(sub), size=min(40000, len(sub)), replace=False)]
    cen = kmeans_lab(to_lab(sub), 10)
    labS = to_lab(S)
    d = np.linalg.norm(labS[..., None, :] - cen[None, None, None], axis=-1)
    lbl = d.argmin(-1)
    rows = []
    for j in range(len(cen)):
        sc, cov, nr, cons, comp = mask_score((lbl == j), K, W)
        rows.append((sc, j, cov, nr, cons, comp))
    rows.sort(reverse=True)
    if not quiet:
        p("   window colour clusters (score = repeats on every floor x several runs x fair coverage x compact rectangles):")
        for sc, j, cov, nr, cons, comp in rows:
            p(f"     {hexc(from_lab(cen[j]))}  coverage {cov * 100:4.0f}%  runs/floor {nr:3.1f}  floor-to-floor {cons:4.2f}  compact {comp:4.2f}  score {sc:4.2f}")
    # greedy union: glass with a gradient / reflections falls into several clusters
    use = [rows[0][1]]
    cur = rows[0][0]
    for sc, j, cov, nr, cons, comp in rows[1:]:
        if comp < 0.4:
            continue
        s2 = mask_score((np.isin(lbl, use + [j])), K, W)[0]
        if s2 > cur * 1.02:
            use.append(j)
            cur = s2
    cands = [("clusters " + ",".join(hexc(from_lab(cen[j])) for j in use), (np.isin(lbl, use)), cur)]
    dm = (dark_mask(L, K))
    cands.append(("dark rule (luminance < 62% of the bright wall)", dm, mask_score(dm, K, W)[0]))
    cands.sort(key=lambda c: -c[2])
    name, m, sc = cands[0]
    if not quiet:
        p("   candidates: " + " | ".join(f"{n.split(' (')[0][:34]} {s:.2f}" for n, _, s in cands))
        if sc < 0.3:
            p("   WARN window colour not clear - pass --window-mode dark  or  --window-mode color:#hex  (hex from the table above)")
    return m, "auto: " + name


def _dil(m, r=2):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def _tol_iou(m, T):
    """overlap tolerant to a few cells of shift/blur (real photos): matched share of both masks"""
    a = (m & _dil(T)).sum() / max(m.sum(), 1)
    b = (T & _dil(m)).sum() / max(T.sum(), 1)
    return float(2 * a * b / max(a + b, 1e-6))


def build_windows(M):
    """template, similarity per floor, special floors (relative: clearly less similar than the typical floor)"""
    K = M.shape[0]
    T = np.median(M.astype(np.float32), axis=0) > 0.5
    iou = np.array([_tol_iou(M[k], T) for k in range(K)])

    def pick(iou):
        thr = min(0.6, float(np.median(iou)) - 0.2)
        return [k for k in range(K) if iou[k] < thr]
    special = pick(iou)
    if special and len(special) < K:
        T = np.median(M[[k for k in range(K) if k not in special]].astype(np.float32), axis=0) > 0.5
        iou = np.array([_tol_iou(M[k], T) for k in range(K)])
        special = pick(iou)
    return T, iou, special


def list_windows(T, wall, fl, n_ref_floor_z0):
    """rectangles of a template (NY, W) -> list of dict (metres)"""
    ppm, pm = wall["ppm"], fl["pitch_m"]
    prof = T[int(NY * 0.15):int(NY * 0.85)].mean(0)
    out = []
    for c0, c1 in runs_of(prof > 0.5, max(2, int(0.25 * ppm))):
        rows = np.where(T[:, c0:c1].mean(1) > 0.5)[0]
        if not len(rows):
            continue
        r0, r1 = rows[0], rows[-1] + 1
        # row -> height above the band bottom; band spans pitch_m
        top_z = (NY - r0) / NY * pm
        bot_z = (NY - r1) / NY * pm
        out.append(dict(x0=round(col_x(wall, c0 - 0.5), 2), x1=round(col_x(wall, c1 - 0.5), 2), w=round((c1 - c0) / ppm, 2),
                        band_bottom=round(bot_z, 2), band_top=round(top_z, 2), h=round(top_z - bot_z, 2)))
    return out



def mask_to_full(wall, fl, M):
    Mfull = np.zeros((wall["H"], wall["W"]), bool)
    for k, (c, _) in enumerate(fl["centres"]):
        ys = np.clip((c - fl["pitch_px"] / 2 + (np.arange(NY) + 0.5) / NY * fl["pitch_px"]).astype(int), 0, wall["H"] - 1)
        Mfull[ys] |= M[k]
    return Mfull


def refine_floors(wall, fl, Mfull):
    """2nd pass: floor rows from the WINDOW MASK (works on dark painted walls too, where the darkness profile is flat)."""
    ppm, H = wall["ppm"], wall["H"]
    pitch = fl["pitch_px"]
    prof = Mfull.mean(1)
    k = max(3, int(ppm * 0.2))
    sm = np.convolve(prof, np.ones(k) / k, mode="same")
    best_ph, best_s = 0.0, -1.0
    for ph in np.arange(0, pitch, 1.0):
        idx = np.round(ph + np.arange(0, (H - ph) // pitch + 1) * pitch).astype(int)
        idx = idx[idx < H]
        s = sm[idx].mean() if len(idx) else -1
        if s > best_s:
            best_s, best_ph = s, ph
    peaks = sm[np.round(np.arange(best_ph, H, pitch)).astype(int).clip(0, H - 1)]
    med = float(np.median(peaks)) if len(peaks) else 0.0
    centres = []
    y = best_ph
    while y < H:
        a0, a1 = int(max(0, y - 0.25 * pitch)), int(min(H, y + 0.25 * pitch))
        if a1 - a0 > 3:
            loc = a0 + int(np.argmax(sm[a0:a1]))
            b0, b1 = int(max(0, loc - 0.3 * pitch)), int(min(H, loc + 0.3 * pitch))
            w = prof[b0:b1]
            cen = (b0 + float((np.arange(b0, b1) * w).sum() / w.sum())) - 0 if w.sum() > 0 else float(loc)
            if w.sum() > 0:
                cen = float((np.arange(b0, b1) * w).sum() / w.sum())
            found = sm[loc] > 0.35 * med
            centres.append((cen if found else float(y), bool(found)))
        y += pitch
    centres = [(c, f) for c, f in centres if c - 0.4 * pitch >= -1 and c + 0.4 * pitch <= H + 1]
    centres.sort(key=lambda t: -t[0])
    out = dict(fl)
    out["centres"] = centres
    return out

# ------------------------------------------------------------------ paint
def cell_colors(S, M, T, wall, fl, cell_m):
    """per floor: pier cells (window rows, window-free columns) and spandrel cells (all other rows, all columns)"""
    K, _, W, _ = S.shape
    ppm = wall["ppm"]
    cw = max(2, int(round(cell_m * ppm)))
    nC = W // cw
    labS = to_lab(S)
    veg = (labS[..., 1] < -8) & (labS[..., 2] > 8)             # green = trees / bushes in front of the wall -> unknown, not paint
    win_rows = np.where(T[:, :].mean(1) > 0.25)[0]
    if len(win_rows):
        wr0, wr1 = win_rows[0], win_rows[-1] + 1
    else:
        wr0, wr1 = int(NY * 0.3), int(NY * 0.7)
    zone_rows = {"pier": (wr0, wr1), "spandrel": None}
    res = {"pier": np.full((K, nC, 3), np.nan), "spandrel": np.full((K, nC, 3), np.nan)}
    for k in range(K):
        valid = ~M[k]
        valid &= S[k].mean(2) > 30                              # skip black gaps / deep shadows
        valid &= ~veg[k]
        for ci in range(nC):
            sl = slice(ci * cw, (ci + 1) * cw)
            # pier: window rows, only if this cell has (almost) no window pixels there
            blk = valid[wr0:wr1, sl]
            if M[k, wr0:wr1, sl].mean() < 0.15 and blk.mean() > 0.6:
                res["pier"][k, ci] = np.median(labS[k, wr0:wr1, sl][blk], axis=0)
            sp = np.ones((NY,), bool)
            sp[wr0:wr1] = False
            v2 = valid[sp][:, sl]
            if v2.size and v2.mean() > 0.5:
                res["spandrel"][k, ci] = np.median(labS[k][sp][:, sl][v2], axis=0)
    return res, cw, nC



def fix_light(cells, wall, cw):
    """Remove a slow brightness gradient along the wall (sun/shade). Reference = median lightness of every column over all
    floors, smoothed over ~1/3 of the wall; changes only L (not hue), only if the gradient is larger than 4 %."""
    sp = cells["spandrel"]
    K, nC, _ = sp.shape
    L = np.nanmedian(sp[..., 0], axis=0)
    ok = ~np.isnan(L)
    if ok.sum() < 6:
        return None
    x = np.arange(nC)
    Li = np.interp(x, x[ok], L[ok])
    w = max(3, nC // 3)
    tr = np.convolve(np.pad(Li, (w, w), mode="edge"), np.ones(w) / w, mode="same")[w:-w]
    gain = tr / np.mean(tr)
    if gain.max() - gain.min() < 0.04:
        return None
    for z in cells:
        c = cells[z]
        c[..., 0] = c[..., 0] / gain[None, :]
    return (float((gain[0] - 1) * 100), float((gain[-1] - 1) * 100))

def make_palette(cells, de=9.0, max_n=8):
    flat = np.concatenate([c.reshape(-1, 3) for c in cells.values()])
    flat = flat[~np.isnan(flat[:, 0])]
    if not len(flat):
        return np.zeros((0, 3))
    q = np.round(flat / 4.0)
    keys, counts = np.unique(q, axis=0, return_counts=True)
    order = np.argsort(-counts)
    cen = []
    for i in order:
        v = keys[i] * 4.0
        for c in cen:
            if np.linalg.norm(c[0] - v) < de:
                c[1].append((v, counts[i]))
                c[0] = np.average([t[0] for t in c[1]], axis=0, weights=[t[1] for t in c[1]])
                break
        else:
            cen.append([v, [(v, counts[i])]])
    pal = [(c[0], sum(t[1] for t in c[1])) for c in cen]
    pal.sort(key=lambda t: -t[1])
    while len(pal) > max_n:
        small = pal.pop()
        j = int(np.argmin([np.linalg.norm(t[0] - small[0]) for t in pal]))
        pal[j] = (pal[j][0], pal[j][1] + small[1])
    return np.array([t[0] for t in pal])


def label_cells(cells, pal):
    out = {}
    for z, c in cells.items():
        lbl = np.full(c.shape[:2], -1, int)
        ok = ~np.isnan(c[..., 0])
        if ok.any() and len(pal):
            d = np.linalg.norm(c[ok][:, None, :] - pal[None], axis=-1)
            lbl[ok] = d.argmin(1)
        out[z] = lbl
    return out


def smooth_floors(lbl):
    """a single floor whose label differs from both neighbours (which agree) takes the neighbours' label; unknown cells take the nearest known floor"""
    K, nC = lbl.shape
    out = lbl.copy()
    for ci in range(nC):
        col = out[:, ci]
        for k in range(1, K - 1):
            if col[k] != col[k - 1] and col[k - 1] == col[k + 1] and col[k - 1] >= 0:
                col[k] = col[k - 1]
        known = np.where(col >= 0)[0]
        if len(known) and len(known) < K:
            for k in range(K):
                if col[k] < 0:
                    col[k] = col[known[np.argmin(np.abs(known - k))]]
    return out


def segments_x(row, min_cells):
    segs, k = [], 0
    while k < len(row):
        j = k
        while j < len(row) and row[j] == row[k]:
            j += 1
        segs.append([k, j, int(row[k])])
        k = j
    changed = True
    while changed and len(segs) > 1:                       # absorb tiny segments into the longer neighbour
        changed = False
        for i, (a, b, l) in enumerate(segs):
            if b - a < min_cells and len(segs) > 1:
                left = segs[i - 1] if i > 0 else None
                right = segs[i + 1] if i + 1 < len(segs) else None
                tgt = max([s for s in (left, right) if s is not None], key=lambda s: s[1] - s[0])
                if tgt is left:
                    left[1] = b
                else:
                    right[0] = a
                segs.pop(i)
                changed = True
                break
    merged = []
    for s in segs:
        if merged and merged[-1][2] == s[2]:
            merged[-1][1] = s[1]
        else:
            merged.append(list(s))
    return merged


def rects_from(lbl, min_cells):
    """lbl (K, nC) floors bottom-first -> rectangles (f0, f1, c0, c1, label), merged over consecutive floors"""
    K = lbl.shape[0]
    rects, open_ = [], {}
    for k in range(K):
        segs = segments_x(lbl[k], min_cells)
        cur = {}
        for a, b, l in segs:
            key = None
            for (oa, ob, ol), (f0, _) in open_.items():
                if ol == l and abs(oa - a) <= 1 and abs(ob - b) <= 1:
                    key = (oa, ob, ol)
                    break
            if key is not None:
                cur[key] = open_[key]
            else:
                cur[(a, b, l)] = (k, k)
        for key, (f0, _) in open_.items():
            if key not in cur:
                rects.append((f0, k - 1, key[0], key[1], key[2]))
        open_ = {key: (v[0], k) for key, v in cur.items()}
    for key, (f0, _) in open_.items():
        rects.append((f0, K - 1, key[0], key[1], key[2]))
    return rects



def rects_from_masked(lbl, min_cells):
    """like rects_from, but cells < 0 are 'nothing' (not listed); only runs >= min_cells wide are kept"""
    K, nC = lbl.shape
    out = []
    # treat every label value >= 0 separately: build a mask per label, merge over floors by identical x-run
    labels = sorted({int(v) for v in np.unique(lbl) if v >= 0})
    for l in labels:
        open_ = {}
        for k in range(K):
            row = lbl[k] == l
            cur = {}
            for a0, a1 in runs_of(row, min_cells):
                key = None
                for (oa, ob), (f0, _) in open_.items():
                    if abs(oa - a0) <= 1 and abs(ob - a1) <= 1:
                        key = (oa, ob)
                        break
                cur[key or (a0, a1)] = open_[key] if key else (k, k)
            for key, (f0, _) in open_.items():
                if key not in cur:
                    out.append((f0, k - 1, key[0], key[1], l))
            open_ = {key: (v[0], k) for key, v in cur.items()}
        for key, (f0, _) in open_.items():
            out.append((f0, K - 1, key[0], key[1], l))
    return out


def compress_repeats(rects):
    """group same-colour same-width rectangles on the same floors that repeat at an even spacing -> one line"""
    groups = {}
    for r in rects:
        groups.setdefault((r["zone"], r["f0"], r["f1"], r["color"], round(r["x1"] - r["x0"], 1)), []).append(r)
    out, used = [], set()
    for key, lst in groups.items():
        lst.sort(key=lambda r: r["x0"])
        if len(lst) >= 3:
            sp = np.diff([r["x0"] for r in lst])
            if sp.std() < 0.35:
                out.append(dict(zone=key[0], f0=key[1], f1=key[2], color=key[3], width=key[4], first_x0=lst[0]["x0"],
                                spacing=round(float(sp.mean()), 2), count=len(lst)))
                used.update(id(r) for r in lst)
    rest = [r for r in rects if id(r) not in used]
    return out, rest

def find_period(seq, max_p=14):
    seq = np.asarray(seq)
    n = len(seq)
    if n < 6 or len(set(seq.tolist())) < 2:
        return None
    for P in range(2, min(max_p, n // 2) + 1):
        agree = float((seq[:-P] == seq[P:]).mean())
        if agree >= 0.92:
            return P
    return None


# ------------------------------------------------------------------ pictures
def save_floor_pictures(wall, fl, nums, M_full, special_nums, base):
    arr = wall["arr"].copy()
    H, W = wall["H"], wall["W"]
    if M_full is not None:
        arr[M_full] = arr[M_full] * 0.55 + np.array([0, 120, 160], np.float32) * 0.45
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    pitch = fl["pitch_px"]
    for (c, found), n in zip(fl["centres"], nums):
        col = (255, 0, 0) if n in special_nums else (255, 255, 0)
        d.line([(0, c), (W, c)], fill=col, width=1)
        for y in (c - pitch / 2, c + pitch / 2):
            d.line([(0, y), (W, y)], fill=(255, 0, 255), width=1)
        d.text((4, c - 12), f"F{n}" + ("*" if n in special_nums else "") + ("" if found else "?"), fill=col)
    # vertical chunks (<= 1500 px tall) so the numbers stay readable
    os.makedirs(OUT, exist_ok=True)
    nch = max(1, math.ceil(H / 1500))
    paths = []
    for i in range(nch):
        y0, y1 = int(i * H / nch), int((i + 1) * H / nch)
        pth = os.path.join(OUT, f"{base}_floors_{i + 1}.png")
        im.crop((0, y0, W, y1)).save(pth)
        paths.append(pth)
    return paths


def save_paint_pictures(wall, fl, nums, rects_px, base, fit):
    arr = wall["arr"]
    H, W = wall["H"], wall["W"]
    flat = np.zeros_like(arr) + 128
    pitch = fl["pitch_px"]
    for r in rects_px:
        y0 = int(max(0, r["y0"])); y1 = int(min(H, r["y1"]))
        flat[y0:y1, int(r["px0"]):int(r["px1"])] = r["rgb"]
    diff = np.clip(np.abs(arr - flat).mean(2) * 3, 0, 255)
    nch = max(1, math.ceil(H / 1500))
    paths = []
    for i in range(nch):
        y0, y1 = int(i * H / nch), int((i + 1) * H / nch)
        a = Image.fromarray(arr[y0:y1].astype(np.uint8))
        b = Image.fromarray(flat[y0:y1].astype(np.uint8))
        c = Image.fromarray(diff[y0:y1].astype(np.uint8)).convert("RGB")
        out = Image.new("RGB", (W * 3 + 20, y1 - y0 + 18), "white")
        for j, (im, t) in enumerate(((a, "photo (straightened)"), (b, "paint rectangles"), (c, "difference x3"))):
            out.paste(im, (j * (W + 10), 18))
            ImageDraw.Draw(out).text((j * (W + 10) + 4, 3), t, fill=(0, 0, 0))
        pth = os.path.join(OUT, f"{base}_paint_{i + 1}.png")
        out.save(pth)
        paths.append(pth)
    return paths


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["floors", "windows", "paint", "all"])
    ap.add_argument("--refs", default=os.path.join(ROOT, "photo_refs.json"))
    ap.add_argument("--name", default="")
    ap.add_argument("--wall-size", default="")
    ap.add_argument("--ppm", type=float, default=30)
    ap.add_argument("--fh", type=float, default=0)
    ap.add_argument("--feature-floor", type=int, default=0)
    ap.add_argument("--first-floor", type=int, default=0)
    ap.add_argument("--window-mode", default="auto")
    ap.add_argument("--cell", type=float, default=0.25)
    ap.add_argument("--list", type=int, default=40)
    a = ap.parse_args()

    wall = load_wall(a)
    base = wall["name"]
    p(f"[facade] {base}: part {wall['w']:.1f} x {wall['h']:.1f} m, x from {wall['x0']:g} m, z {wall['z0']:g}..{wall['z1']:g} m, {wall['ppm']:.0f} px/m")
    fl = find_floors(wall, a.fh)
    K = len(fl["centres"])
    p(f"[floors] pitch {fl['pitch_m']:.2f} m (strength {fl['strength']:.2f}, from {fl['source']} profile), {K} floor rows in this part")
    if a.fh and abs(fl["pitch_m"] - a.fh) / a.fh > 0.08:
        p(f"   WARN found pitch {fl['pitch_m']:.2f} m differs from --fh {a.fh:g} m by more than 8 % - wrong floor height or wrong corners/size")

    S = band_stack(wall, fl)
    mode = a.window_mode
    M, info = window_mask(S, wall, mode)
    fl = refine_floors(wall, fl, mask_to_full(wall, fl, M))          # floor rows from the window mask (2nd pass)
    K = len(fl["centres"])
    S = band_stack(wall, fl)
    _quiet = True
    M, info = window_mask(S, wall, mode, quiet=True)
    p(f"[floors] after refinement: {K} floor rows (window rows used)")
    p(f"[windows] mode: {info}")
    T, iou, special = build_windows(M)
    # ---- floor numbers
    pm = fl["pitch_m"]
    z_nums = []
    for c, _ in fl["centres"]:
        z = row_z(wall, c)
        z_nums.append(int(math.floor(z / pm)) + 1)
    if a.first_floor:
        nums = [a.first_floor + k for k in range(K)]
        how = f"--first-floor {a.first_floor}"
    elif a.feature_floor and special:
        k_f = min(special, key=lambda k: iou[k])
        nums = [a.feature_floor + (k - k_f) for k in range(K)]
        how = f"counted from the feature floor (row {k_f + 1} from the bottom = floor {a.feature_floor})"
        if z_nums[k_f] != a.feature_floor:
            p(f"   NOTE numbering by height would call that row floor {z_nums[k_f]} (z {row_z(wall, fl['centres'][k_f][0]):.1f} m / pitch {pm:.2f}); using floor {a.feature_floor} as told")
    else:
        nums = z_nums
        how = "by height z / pitch (+1)"
        if a.feature_floor:
            p("   WARN --feature-floor given but no clearly different floor found: numbers come from height. Check the picture, or use --first-floor N")
    special_nums = [nums[k] for k in special]
    p(f"[floors] numbering: {how}; floors {nums[0]}..{nums[-1]}" + (f"; special floors (pattern differs): {special_nums}" if special_nums else ""))
    # ---- picture
    Mfull = mask_to_full(wall, fl, M)
    pics = save_floor_pictures(wall, fl, nums, Mfull, special_nums, base)
    p("[picture] " + "  ".join(os.path.relpath(x, ROOT) for x in pics) + "   (yellow = floor centre, magenta = band edges, red/* = special floor, cyan = window mask)")
    result = dict(name=base, pitch_m=round(pm, 3), floors=[dict(n=n, z_center=round(row_z(wall, c), 2), found=f, special=(n in special_nums))
                                                          for (c, f), n in zip(fl["centres"], nums)])
    if a.cmd == "floors":
        p("   -> check the floor numbers in the picture against the photo before going on (windows / paint)")
        save_json(base, result)
        return
    # ---- windows
    ppm = wall["ppm"]
    wins = list_windows(T, wall, fl, 0)
    # floor level: z of the floor's bottom = (n - 1) * pitch (+ part offset handled by numbering)
    for w in wins:
        k_ref = next((k for k in range(K) if k not in special), 0)
        zc = row_z(wall, fl["centres"][k_ref][0])
        band_bot = zc - pm / 2
        floor_level = (nums[k_ref] - 1) * pm
        w["sill"] = round(band_bot + w["band_bottom"] - floor_level, 2)
        w["head"] = round(band_bot + w["band_top"] - floor_level, 2)
    kinds = []
    for w in wins:
        for i, kd in enumerate(kinds):
            if abs(kd["w"] - w["w"]) < 0.12 and abs(kd["h"] - w["h"]) < 0.12:
                w["kind"] = i
                break
        else:
            w["kind"] = len(kinds)
            kinds.append(dict(w=w["w"], h=w["h"]))
    p(f"[windows] template from {K - len(special)} regular floors: {len(wins)} windows, {len(kinds)} size kinds")
    for w in wins[:a.list]:
        p(f"   WIN x[{w['x0']:.2f},{w['x1']:.2f}]m  w {w['w']:.2f}  sill {w['sill']:.2f}  head {w['head']:.2f}  h {w['h']:.2f}  kind {w['kind']}")
    if len(wins) >= 3:                                         # curtain wall / module summary (for the generator: module_w, spandrel_h, mullion)
        x0s = [w["x0"] for w in wins]
        pit = float(np.median(np.diff(x0s)))
        gaps = [wins[i + 1]["x0"] - wins[i]["x1"] for i in range(len(wins) - 1)]
        gap = float(np.median(gaps))
        sill = float(np.median([w["sill"] for w in wins]))
        head = float(np.median([w["head"] for w in wins]))
        p(f"   MODULE pitch {pit:.2f} m (window x spacing), gap between windows {gap:.2f} m (pier / mullion), sill {sill:.2f} m above the floor line, "
          f"band above the window {pm - head:.2f} m of the {pm:.2f} m floor")
        if gap < 0.25 and 0.9 <= pit <= 3.0:
            p("   NOTE gap < 0.25 m and pitch 0.9~3 m: looks like a curtain wall. In the generator use K.curtainwall(module_w=%.2f, spandrel_h=%.2f); "
              "measure mullion width on a close-up photo or take it from TASK.md" % (pit, sill))
    sp_out = {}
    for k in special:
        Tk = M[k]
        ws = list_windows(Tk, wall, fl, 0)
        sp_out[nums[k]] = [dict(x0=w["x0"], x1=w["x1"], w=w["w"]) for w in ws]
        p(f"   SPECIAL floor {nums[k]} (match with regular template {iou[k] * 100:.0f}%): {len(ws)} windows " +
          " ".join(f"[{w['x0']:.1f},{w['x1']:.1f}]" for w in ws[:12]))
    result.update(windows=wins, window_kinds=kinds, special_floor_windows=sp_out, window_mode=info)
    if a.cmd == "windows":
        save_json(base, result)
        return
    # ---- paint
    cells, cw, nC = cell_colors(S, M, T, wall, fl, a.cell)
    light = fix_light(cells, wall, cw)
    if light is not None:
        p(f"[paint] light gradient along the wall removed (brightness {light[0]:+.0f}% at the left edge .. {light[1]:+.0f}% at the right edge)")
    pal = make_palette(cells)
    lbls = label_cells(cells, pal)
    min_cells = max(2, int(round(0.5 / a.cell)))
    p(f"[paint] palette ({len(pal)}): " + "  ".join(hexc(from_lab(c)) for c in pal))
    rects_out, rects_px, rules = [], [], []
    lbls["pier"] = np.where(lbls["pier"] == lbls["spandrel"], -3, lbls["pier"])      # same colour as the spandrel there -> nothing to list
    for zone in ("spandrel", "pier"):
        lb = smooth_floors(lbls[zone]) if zone == "spandrel" else lbls[zone]
        if zone == "pier":
            rc = rects_from_masked(lb, min_cells)
        else:
            rc = None
        if rc is None:
            rc = rects_from(lb, min_cells)
        rc.sort(key=lambda r: (r[0], r[2]))
        for f0, f1, c0, c1, l in rc:
            col = from_lab(pal[l])
            rects_out.append(dict(zone=zone, f0=nums[f0], f1=nums[f1], x0=round(col_x(wall, c0 * cw - 0.5), 2),
                                  x1=round(col_x(wall, c1 * cw - 0.5), 2), color=hexc(col)))
            # picture rectangle in px: floor band rows (spandrel = whole band, pier overpaints the window rows)
            ya = math.floor(fl["centres"][f1][0] - fl["pitch_px"] / 2) - 1
            yb = math.ceil(fl["centres"][f0][0] + fl["pitch_px"] / 2) + 1
            rects_px.append(dict(y0=ya, y1=yb, px0=c0 * cw, px1=c1 * cw, rgb=col, zone=zone))
        # periodic floor rules per distinct x segment, one line per distinct pattern (x ranges merged)
        pats = {}
        for (c0, c1) in sorted({(r[2], r[3]) for r in rc}):
            seq = lb[:, (c0 + c1) // 2]
            P = find_period(seq)
            if P:
                key = (P, tuple(int(v) for v in seq[:P]))
                pats.setdefault(key, []).append((c0, c1))
        for (P, pat), spans in sorted(pats.items(), key=lambda kv: -sum(b - a for a, b in kv[1]))[:4]:
            xs = ", ".join(f"[{col_x(wall, a * cw - 0.5):.1f},{col_x(wall, b * cw - 0.5):.1f}]" for a, b in spans[:4]) + (" ..." if len(spans) > 4 else "")
            rules.append(f"RULE {zone} x{xs}m: repeats every {P} floors; one period from floor {nums[0]}: " +
                         " ".join(f"{nums[k]}:{hexc(from_lab(pal[pat[k]]))}" for k in range(P)))
    # draw spandrels first, then piers (piers only occupy window rows) - restrict pier rects to the window rows in the picture
    wr = np.where(T.mean(1) > 0.25)[0]
    if len(wr):
        for r in rects_px:
            if r["zone"] == "pier":
                pass
    result.update(palette=[hexc(from_lab(c)) for c in pal], paint_rects=rects_out, rules=rules, cell_m=a.cell)
    groups, rest = compress_repeats(rects_out)
    result["paint_repeat_groups"] = groups
    lines = []
    for r in rest:
        lines.append((r["f0"], 0, f"PAINT {r['zone']:8s} floors {r['f0']}-{r['f1']}  x[{r['x0']:.2f},{r['x1']:.2f}]m  {r['color']}"))
    for g in groups:
        lines.append((g["f0"], 1, f"PAINT {g['zone']:8s} floors {g['f0']}-{g['f1']}  REPEAT {g['count']}x  width {g['width']:.2f} m  every {g['spacing']:.2f} m from x {g['first_x0']:.2f}  {g['color']}"))
    lines.sort()
    for _, _, s in lines[:a.list]:
        p("   " + s)
    if len(lines) > a.list:
        p(f"   ... {len(lines) - a.list} more lines (full list in previews/facade/{base}.json)")
    for r in rules[:a.list]:
        p("   " + r)
    # fit: reconstruct and compare on wall (non-window) pixels
    flat = np.zeros_like(wall["arr"])
    have = np.zeros(wall["arr"].shape[:2], bool)
    for r in rects_px:
        if r["zone"] == "spandrel":
            y0, y1 = int(max(0, r["y0"])), int(min(wall["H"], r["y1"]))
            flat[y0:y1, int(r["px0"]):int(r["px1"])] = r["rgb"]
            have[y0:y1, int(r["px0"]):int(r["px1"])] = True
    # pier rects override in the window-row part of each floor
    wr0 = int(np.where(T.mean(1) > 0.25)[0][0]) if (T.mean(1) > 0.25).any() else int(NY * 0.3)
    wr1 = int(np.where(T.mean(1) > 0.25)[0][-1]) + 1 if (T.mean(1) > 0.25).any() else int(NY * 0.7)
    for r in rects_px:
        if r["zone"] == "pier":
            for k, (c, _) in enumerate(fl["centres"]):
                if r["y0"] - 1 <= c <= r["y1"] + 1:
                    ya = int(c - fl["pitch_px"] / 2 + wr0 / NY * fl["pitch_px"])
                    yb = int(c - fl["pitch_px"] / 2 + wr1 / NY * fl["pitch_px"])
                    flat[max(0, ya):min(wall["H"], yb), int(r["px0"]):int(r["px1"])] = r["rgb"]
    ok = have & ~Mfull
    if ok.any():
        de = np.linalg.norm(to_lab(wall["arr"][ok]) - to_lab(flat[ok]), axis=-1)
        fit = float(np.median(de))
        p(f"[paint] FIT median colour difference photo vs rectangles: dE {fit:.1f} (< 8 good; > 14 = rectangles miss something, look at the picture)")
        result["fit_dE_median"] = round(fit, 1)
    # picture
    flat_pic = flat.copy()
    pics = []
    nch = max(1, math.ceil(wall["H"] / 1500))
    arr = wall["arr"]
    diff = np.clip(np.linalg.norm(arr - flat, axis=-1) * 2, 0, 255)
    for i in range(nch):
        y0, y1 = int(i * wall["H"] / nch), int((i + 1) * wall["H"] / nch)
        W = wall["W"]
        out = Image.new("RGB", (W * 3 + 20, y1 - y0 + 18), "white")
        for j, (im, t) in enumerate(((arr[y0:y1], "photo (straightened)"), (flat_pic[y0:y1], "paint rectangles (windows left black)"),
                                      (np.stack([diff[y0:y1]] * 3, -1), "difference x2"))):
            out.paste(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)), (j * (W + 10), 18))
            ImageDraw.Draw(out).text((j * (W + 10) + 4, 3), t, fill=(0, 0, 0))
        pth = os.path.join(OUT, f"{base}_paint_{i + 1}.png")
        out.save(pth)
        pics.append(os.path.relpath(pth, ROOT))
    p("[picture] " + "  ".join(pics))
    save_json(base, result)


def save_json(base, result):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, base + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    p(f"[json] {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
