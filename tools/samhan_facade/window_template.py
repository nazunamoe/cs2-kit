import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import sys
import numpy as np
from PIL import Image, ImageDraw
import photo_sections as P
# wintpl.py kind photo sec f0 f1 [a_l a_r px_l px_r]
# average floor template (floors f0..f1, refuge 29 skipped) -> dark runs per wall in metres along the wall + heights
kind, pi, sname, f0, f1 = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
ph = P.PHOTOS[kind][pi]
sec = dict([s for s in ph["secs"] if s["name"] == sname][0])
if len(sys.argv) > 6:
    sec["a"] = (float(sys.argv[6]), float(sys.argv[7])); sec["px"] = (float(sys.argv[8]), float(sys.argv[9]))
im = Image.open(P.os.path.join(P.ROOT, ph["file"])).convert("RGB")
g = np.asarray(im.convert("L"), np.float32)
x0, x1 = sorted(sec["px"])
yc, p = P.fit_rows(g, sec, int(x0), int(x1), np.zeros(g.shape, bool))
a_l, a_r = sec["a"]; p_l, p_r = sec["px"]
px = lambda a: p_l + (a - a_l) * (p_r - p_l) / (a_r - a_l)
NY, X0, X1 = 40, int(x0) - 3, int(x1) + 3
acc, n = np.zeros((NY, X1 - X0)), 0
for f in range(f0, f1 + 1):
    if f == 29 and f0 != 29:
        continue
    pp = abs(yc(f + 0.5) - yc(f - 0.5)); yb = yc(f) + 0.62 * pp; yt = yb - pp
    if yt < 0 or yb > g.shape[0]:
        continue
    rows = np.linspace(yt, yb, NY).astype(int)
    blk = g[rows][:, X0:X1]
    ref = np.percentile(blk, 92)
    acc += (blk < 0.5 * ref); n += 1
acc /= max(n, 1)
# image of the template (top = slab above, bottom = floor line)
t = Image.fromarray((255 - acc * 255).astype(np.uint8)).resize(((X1 - X0) * 3, NY * 6), Image.NEAREST).convert("RGB")
d = ImageDraw.Draw(t)
E = P.edges()
for i in sec["walls"]:
    for a in (E[i]["a0"], E[i]["a1"]):
        x = (px(a) - X0) * 3; d.line([(x, 0), (x, t.size[1])], fill=(255, 0, 255), width=1)
t.save(os.path.join(ROOT, r"previews\wtpl_%s%d_%s_%d.png") % (kind, pi, sname, f0))
# dark runs: columns where the window band (0.25..0.75 of the floor) is mostly dark
band = acc[int(NY * 0.2):int(NY * 0.8)].mean(0)
dark = band > 0.45
runs, k = [], 0
while k < len(dark):
    if dark[k]:
        j = k
        while j < len(dark) and dark[j]:
            j += 1
        if j - k >= 2:
            col = acc[:, k:j].mean(1) > 0.5
            ys = np.where(col)[0]
            top, bot = (1 - ys[0] / NY, 1 - ys[-1] / NY) if len(ys) else (0, 0)
            runs.append((k + X0, j + X0, top, bot))
        k = j
    else:
        k += 1
FH = 3.12
print("floors used", n, "pitch px", round(abs(p), 1))
for xa, xb, top, bot in runs:
    a = [a_l + (x - p_l) * (a_r - a_l) / (p_r - p_l) for x in (xa, xb)]
    lo, hi = min(a), max(a)
    walls = [i for i in sec["walls"] if E[i]["a0"] - 0.3 < (lo + hi) / 2 < E[i]["a1"] + 0.3] if True else []
    print("px %4d-%4d  a %6.2f..%6.2f  w %.2f m  z %.2f..%.2f m  walls %s" % (xa, xb, lo, hi, hi - lo, bot * FH, top * FH, walls))
