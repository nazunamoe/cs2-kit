"""bandscan.py kind pi sec walls f0,f1 [--span w:u0:u1,...] [--a --px]
per floor and wall span: brightest row (60th pct across the span) within z -0.35..0.85 m of the floor line / white ref.
Prints x100. High (>~75) = white band at the floor line (stripe floor or white wall), low = solid panel."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import argparse, sys
import numpy as np
from PIL import Image
ROOT = ROOT
import photo_sections as P
T = gen()
ap = argparse.ArgumentParser()
ap.add_argument("kind"); ap.add_argument("pi", type=int); ap.add_argument("sec"); ap.add_argument("spans"); ap.add_argument("f")
ap.add_argument("--a"); ap.add_argument("--px"); ap.add_argument("--shift", type=int, default=0)
args = ap.parse_args()
T.MIRROR = False
ph = P.PHOTOS[args.kind][args.pi]
sec = dict([s for s in ph["secs"] if s["name"] == args.sec][0])
if args.a: sec["a"] = tuple(float(v) for v in args.a.split(","))
if args.px: sec["px"] = tuple(float(v) for v in args.px.split(","))
im = Image.open(P.os.path.join(ROOT, ph["file"])).convert("RGB")
rgb = np.asarray(im, np.float32); g = rgb.mean(2); H, W = g.shape
x0, x1 = sorted(sec["px"])
yc, pitch = P.fit_rows(g, sec, int(x0), int(x1), np.zeros(g.shape, bool))
tint = ((rgb[..., 2] - rgb[..., 0] > 85) & (rgb[..., 2] > 120)) | ((rgb[..., 0] - rgb[..., 1] > 25) & (rgb[..., 2] - rgb[..., 1] > 25))
a_l, a_r = sec["a"]; p_l, p_r = sec["px"]
px = lambda a: p_l + (a - a_l) * (p_r - p_l) / (a_r - a_l)
prof = np.percentile(g[:, int(x0):int(x1)], 95, axis=1); k = int(abs(pitch) * 3)
ref = np.array([np.median(prof[max(0, i - k):i + k + 1]) for i in range(H)])
spans = []
for s in args.spans.split(","):
    if ":" in s:
        nm, a0, a1 = s.split(":"); spans.append((nm, float(a0), float(a1)))
    else:
        e = T.edges_of(T.full_poly(T.HALF, False))[int(s)]; spans.append((s, e["a0"] + 0.3, e["a1"] - 0.3))
f0, f1 = (int(v) for v in args.f.split(","))
print("floor " + " ".join("%6s" % s[0] for s in spans))
for f in range(f1, f0 - 1, -1):
    pp = abs(yc(f + 0.5) - yc(f - 0.5)); yl = yc(f) + P.rowh(sec) * pp
    row = []
    for nm, a0, a1 in spans:
        xa, xb = sorted((px(a0), px(a1))); xa, xb = int(xa), int(xb)
        ya, yb = int(yl - 0.85 / T.FH * pp), int(yl + 0.35 / T.FH * pp) + 1
        if ya < 0 or yb > H or xa < 0 or xb > W or xb - xa < 2:
            row.append("     ."); continue
        if tint[ya:yb, xa:xb].mean() > 0.25:
            row.append("     -"); continue
        r = np.percentile(g[ya:yb, xa:xb], 60, axis=1) / np.maximum(ref[ya:yb], 1)
        row.append("%6d" % int(100 * r.max()))
    print("%5d " % (f + args.shift) + " ".join(row))
