"""cscan.py kind pi sec --rowa A --gapa A [--spans name:a0:a1,...] [--mode band|blue|light]
Rows are counted from the refuge row: window rows are dark minima in a column at plan position --rowa (a window that
exists on every floor, refuge included, e.g. S), the refuge row is the row where the column at --gapa (an L / M window)
is bright. floor = 29 + (rows above refuge). For every floor and span prints a score x100:
 band : brightest row in the zone below the window row (white band / white wall high, panel low)
 blue : median (b - r) at the window-row height minus the section white (blue paint high)
 light: median brightness at window-row height / white ref (white pier high)"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import argparse
import sys

import numpy as np
from PIL import Image

ROOT = ROOT
import photo_sections as P  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("kind"); ap.add_argument("pi", type=int); ap.add_argument("sec")
ap.add_argument("--rowa", required=True); ap.add_argument("--gapa", required=True)
ap.add_argument("--spans", required=True); ap.add_argument("--mode", default="band")
ap.add_argument("--a"); ap.add_argument("--px"); ap.add_argument("--hw", type=float, default=0.25)
ap.add_argument("--show", action="store_true"); ap.add_argument("--refy", type=float)
args = ap.parse_args()
ph = P.PHOTOS[args.kind][args.pi]
sec = dict([s for s in ph["secs"] if s["name"] == args.sec][0])
if args.a: sec["a"] = tuple(float(v) for v in args.a.split(","))
if args.px: sec["px"] = tuple(float(v) for v in args.px.split(","))
im = Image.open(P.os.path.join(ROOT, ph["file"])).convert("RGB")
rgb = np.asarray(im, np.float32); g = rgb.mean(2); br = rgb[..., 2] - rgb[..., 0]; H, W = g.shape
a_l, a_r = sec["a"]; p_l, p_r = sec["px"]
px = lambda a: p_l + (a - a_l) * (p_r - p_l) / (a_r - a_l)
mpp = abs(p_r - p_l) / abs(a_r - a_l)      # px per metre along the wall
tint = ((rgb[..., 2] - rgb[..., 0] > 85) & (rgb[..., 2] > 120)) | ((rgb[..., 0] - rgb[..., 1] > 25) & (rgb[..., 2] - rgb[..., 1] > 25))


def col(a):
    if str(a).startswith("px"):
        _, u, v = str(a).split(":"); return int(u), int(v)
    c = px(float(a)); h = max(2, args.hw * mpp)
    return int(c - h), int(c + h) + 1


xa, xb = col(args.rowa)
prof = np.convolve(g[:, xa:xb].mean(1), np.ones(5) / 5, "same")
pitch_guess = abs(sec["fl"][1][1] - sec["fl"][0][1]) / abs(sec["fl"][1][0] - sec["fl"][0][0])
w = int(pitch_guess * 0.35)
med = np.median(prof)
R = [i for i in range(w, H - w) if prof[i] == prof[i - w:i + w + 1].min() and prof[i] < 0.85 * med]
ga, gb = col(args.gapa)
gp = np.convolve(g[:, ga:gb].mean(1), np.ones(5) / 5, "same")
gv = [gp[y] for y in R]
d = np.diff(R)
pitch = float(np.median(d))
# refuge = row whose gap-column value is clearly brighter than its neighbours (within the regular run)
mg = np.median(gv)
cand = [k for k in range(1, len(R) - 1) if gv[k] > 1.8 * mg and gv[k - 1] < 1.4 * mg and gv[k + 1] < 1.4 * mg
        and 0.75 * pitch < d[k - 1] < 1.3 * pitch and tint[R[k] - 3:R[k] + 4, ga:gb].mean() < 0.2]
if args.refy:
    cand = [int(np.argmin([abs(r - args.refy) for r in R]))]
if args.show:
    print("rows", R); print("gap", [int(v) for v in gv]); print("cand", cand)
k0 = cand[-1] if cand else None
if k0 is None:
    sys.exit("refuge row not found")
# floors: walk up / down from the refuge row with the pitch (missing rows are filled)
fl = {29: R[k0]}
for direction in (-1, 1):
    y, f = R[k0], 29
    while True:
        y_pred = y + direction * pitch
        if y_pred < 0 or y_pred > H:
            break
        near = [r for r in R if abs(r - y_pred) < 0.3 * pitch]
        y = near[0] if near else y_pred
        f -= direction
        fl[f] = y
top = max(f for f in fl if any(abs(r - fl[f]) < 0.3 * pitch for r in R) and fl[f] > 0)
ref_prof = np.percentile(g[:, int(min(p_l, p_r)):int(max(p_l, p_r))], 95, axis=1)
k = int(pitch * 3)
ref = np.array([np.median(ref_prof[max(0, i - k):i + k + 1]) for i in range(H)])
sx0, sx1 = int(min(p_l, p_r)), int(max(p_l, p_r))
white_br = np.median(br[:, sx0:sx1][g[:, sx0:sx1] > 0.9 * ref[:, None]])
spans = [(s.split(":")[0], float(s.split(":")[1]), float(s.split(":")[2])) for s in args.spans.split(",")]
print("pitch %.1f  refuge y %d  top row floor %d" % (pitch, R[k0], top))
print("floor " + " ".join("%6s" % s[0] for s in spans))
for f in sorted(fl, reverse=True):
    y = fl[f]
    if f < 5 or f > top + 1:
        continue
    row = []
    for nm, a0, a1 in spans:
        x0, x1 = sorted((px(a0), px(a1))); x0, x1 = int(x0), int(x1) + 1
        if args.mode == "band":
            ya, yb = int(y + 0.2 * pitch), int(y + 0.8 * pitch)
        else:
            ya, yb = int(y - 0.25 * pitch), int(y + 0.25 * pitch)
        if ya < 0 or yb > H or x0 < 0 or x1 > W:
            row.append("     ."); continue
        if tint[ya:yb, x0:x1].mean() > 0.25:
            row.append("     -"); continue
        if args.mode == "band":
            v = (np.percentile(g[ya:yb, x0:x1], 60, axis=1) / np.maximum(ref[ya:yb], 1)).max() * 100
        elif args.mode == "blue":
            v = np.median(br[ya:yb, x0:x1]) - white_br
        else:
            v = np.median(g[ya:yb, x0:x1] / np.maximum(ref[ya:yb, None], 1)) * 100
        row.append("%6d" % v)
    print("%5d " % f + " ".join(row))
