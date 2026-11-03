# 대략 위치의 창 목록을 여러 층 중앙값으로 정밀 측정.
# usage: python wmeas.py <img> <a0> <sign> "g0,g1[,zmid];g0,g1;..." [k0=10] [k1=38]   (env GF FH DZ ZTOP)
# 각 창: 층마다 가로 밝기(창 가운데 높이)에서 어두운 구간의 좌우 끝, 세로 밝기에서 창대/창머리 (층 기준 높이)
import sys, os, numpy as np
from PIL import Image
f, a0, sg = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
items = [[float(v) for v in s.split(",")] for s in sys.argv[4].split(";") if s.strip()]
k0 = int(sys.argv[5]) if len(sys.argv) > 5 else 10
k1 = int(sys.argv[6]) if len(sys.argv) > 6 else 38
gf, fh, dz, ztop = (float(os.environ.get(k, d)) for k, d in (("GF", 5.3), ("FH", 2.856), ("DZ", 2.0), ("ZTOP", 132)))
L = np.asarray(Image.open(f).convert("L")).astype(float)
lv = lambda k: gf + (k - 2) * fh
Y = lambda zg: int(round((ztop - (zg + dz)) * 20))
X = lambda g: int(round((g * sg - a0) * 20))
for it in items:
    g0, g1 = sorted(it[:2]); zm = it[2] if len(it) > 2 else 1.4
    pad = 0.6
    xa, xb = sorted((X(g0 - pad), X(g1 + pad)))
    xa = max(xa, 0); xb = min(xb, L.shape[1])
    hp = np.median([L[Y(lv(k) + zm) - 1:Y(lv(k) + zm) + 2, xa:xb].mean(0) for k in range(k0, k1 + 1)], 0)
    ci0, ci1 = sorted((X(g0) - xa, X(g1) - xa))
    inner = hp[max(ci0 + 2, 0):max(ci1 - 1, ci0 + 3)].mean()
    outer = np.r_[hp[:max(ci0 - 3, 1)], hp[min(ci1 + 3, len(hp) - 1):]]
    wallv = np.median(outer) if len(outer) else hp.max()
    thr = (inner + wallv) / 2
    dark = hp < thr if inner < wallv else hp > thr
    c = (ci0 + ci1) // 2
    l = c
    while l > 0 and dark[l - 1]: l -= 1
    r = c
    while r < len(dark) - 1 and dark[r + 1]: r += 1
    ga, gb = sorted((sg * (a0 + (xa + l) / 20), sg * (a0 + (xa + r + 1) / 20)))
    cc0, cc1 = sorted((X(ga), X(gb)))
    cc0 += max(1, (cc1 - cc0) // 4); cc1 -= max(1, (cc1 - cc0) // 4)
    rs = np.arange(-0.2, 3.1, 0.05)
    vp = np.median([[L[Y(lv(k) + r), cc0:cc1].mean() for r in rs] for k in range(k0, k1 + 1)], 0)
    iz = int(round((zm + 0.2) / 0.05))
    ref = np.percentile(vp, 90) if inner < wallv else np.percentile(vp, 10)
    vthr = (vp[iz] + ref) / 2
    dk = vp < vthr if inner < wallv else vp > vthr
    lo = iz
    while lo > 0 and dk[lo - 1]: lo -= 1
    hi = iz
    while hi < len(dk) - 1 and dk[hi + 1]: hi += 1
    print("(%.2f, %.2f, (%.2f, %.2f)),   # in %d wall %d" % (ga, gb, rs[lo], rs[hi] + 0.05, inner, wallv))
