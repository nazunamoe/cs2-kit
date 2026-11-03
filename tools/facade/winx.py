# window list from a textured scan elevation (20 px/m): median over many floors, per-window sill/head.
# args: img a0 sign(+1: gen = a, -1: gen = -a) ztop dz(scan - gen) gf fh k0 k1 [thr]
import sys
from PIL import Image
import numpy as np
f, a0, sg, ztop, dz, gf, fh, k0, k1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7]), int(sys.argv[8]), int(sys.argv[9])
thr = float(sys.argv[10]) if len(sys.argv) > 10 else 90
im = np.asarray(Image.open(f).convert("RGB")).astype(float); L = im.mean(2)
lv = lambda k: gf + (k - 2) * fh
Y = lambda zg: int(round((ztop - (zg + dz)) * 20))
ks = range(k0, k1 + 1)
prof = lambda r: np.median([L[Y(lv(k) + r) - 1:Y(lv(k) + r) + 2].mean(0) for k in ks], 0)
hi = prof(float(__import__("os").environ.get("ROW","2.1")))
wall = prof(2.62)                                  # wall band between window rows
median_filter = lambda a, size, mode: np.array([np.median(a[max(0, i - size // 2):i + size // 2 + 1]) for i in range(len(a))])
loc = median_filter(wall, size=121, mode="nearest")
import os
lim = np.minimum(thr, 0.68 * loc) if os.environ.get("ADAPT") else np.full(len(hi), thr)
d = hi < lim
runs = []; s = None
for x, v in enumerate(list(d) + [False]):
    if v and s is None: s = x
    if not v and s is not None:
        runs.append([s, x]); s = None
m = []
for r in runs:                                   # merge gaps < 0.25 m
    if m and r[0] - m[-1][1] < 5: m[-1][1] = r[1]
    else: m.append(r)
m = [r for r in m if r[1] - r[0] >= 8]
out = []
for s, e in m:
    c0, c1 = s + (e - s) // 4, e - (e - s) // 4
    vs = []
    for k in ks:                                 # vertical profile around this floor
        ys = range(Y(lv(k) + 3.0), Y(lv(k) + 3.0) + 62)
        vs.append([L[y, c0:c1].mean() for y in ys])
    v = np.median(np.array(vs), 0)               # index 0 = floor + 3.0 (top)
    dk = np.where(v < lim[c0:c1].mean())[0]
    if len(dk) == 0: continue
    # largest contiguous dark run
    best, cur = (0, 0), [dk[0], dk[0]]
    for i in dk[1:]:
        if i == cur[1] + 1: cur[1] = i
        else:
            best = max(best, tuple(cur), key=lambda t: t[1] - t[0]); cur = [i, i]
    best = max(best, tuple(cur), key=lambda t: t[1] - t[0])
    head, sill = 3.0 - best[0] / 20, 3.0 - (best[1] + 1) / 20
    g0, g1 = sorted((sg * (a0 + s / 20), sg * (a0 + e / 20)))
    out.append((round(g0, 2), round(g1, 2), round(sill, 2), round(head, 2)))
for o in sorted(out): print("(%.2f, %.2f, (%.2f, %.2f))," % o)
wb = prof(2.62); _, = [0]
segs = []; s = 0
cl = lambda p: "K" if p < 75 else ("G" if p < 150 else "W")
k = [cl(p) for p in wb]
col = np.median([im[Y(lv(kk) + 2.62)] for kk in ks], 0)
for x in range(1, len(k) + 1):
    if x == len(k) or k[x] != k[s]:
        if x - s >= 6:
            g0, g1 = sorted((sg * (a0 + s / 20), sg * (a0 + x / 20)))
            segs.append("%s %.2f..%.2f #%02x%02x%02x" % ((k[s], g0, g1) + tuple(int(q) for q in col[s:x].mean(0))))
        s = x
print("WALL:", " | ".join(segs))
