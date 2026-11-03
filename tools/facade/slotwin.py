# stair-window heights inside a slot column of a scan elevation.
# usage: python slotwin.py img a0img sign ztop dz gf fh k0 k1 x0 x1
# prints per floor the dark runs (z relative to floor level lv(k)) and the median window (sill, head)
import sys
import numpy as np
from PIL import Image
f = sys.argv[1]
a0, sg, ztop, dz, gf, fh = [float(v) for v in sys.argv[2:8]]
k0, k1 = int(sys.argv[8]), int(sys.argv[9])
x0, x1 = float(sys.argv[10]), float(sys.argv[11])
im = np.asarray(Image.open(f).convert("L")).astype(float)
lv = lambda k: gf + (k - 2) * fh
c0, c1 = sorted(((sg * x0 - a0) * 20, (sg * x1 - a0) * 20))
w = c1 - c0
c0, c1 = int(c0 + 0.2 * w), int(c1 - 0.2 * w)
prof = im[:, c0:c1].mean(1)
Y = lambda zg: int(round((ztop - (zg + dz)) * 20))
zs_of = lambda y: ztop - y / 20 - dz
base = np.median(prof[Y(lv(k1)):Y(lv(k0))])
print("column median %.0f" % base)
res = []
for k in range(k0, k1 + 1):
    ya, yb = Y(lv(k + 1)), Y(lv(k))              # one floor: from its top down to its bottom
    seg = prof[ya:yb]
    thr = 0.78 * np.median(seg)
    dark = seg < thr
    runs, s = [], None
    for i, v in enumerate(list(dark) + [False]):
        if v and s is None:
            s = i
        if not v and s is not None:
            if i - s >= 6:
                runs.append((round(zs_of(ya + i) - lv(k), 2), round(zs_of(ya + s) - lv(k), 2)))
            s = None
    res.append(runs)
    if k in (k0, (k0 + k1) // 2, k1):
        print("k", k, runs)
# median over floors of the longest run
best = [max(r, key=lambda t: t[1] - t[0]) for r in res if r]
print("median window (sill, head) rel. floor: %.2f %.2f   n=%d" % (np.median([b[0] for b in best]), np.median([b[1] for b in best]), len(best)))
