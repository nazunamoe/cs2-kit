# 높이장 npz 의 높이별 영역(연결 성분) 목록. usage: python toplevels.py <top.npz> "lo-hi,lo-hi,..." [minn=30]
import sys, numpy as np
d = np.load(sys.argv[1]); H = d["H"]; x0 = float(d["x0"]); y0 = float(d["y0"]); c = float(d["cell"])
mn = int(sys.argv[3]) if len(sys.argv) > 3 else 30
v = H[H > 20]; h, e = np.histogram(v, bins=np.arange(20, H.max() + 0.5, 0.25))
print("top heights:", " ".join("%.2f:%d" % (e[i], h[i]) for i in np.argsort(-h)[:14]))
def label(m):
    lab = np.zeros(m.shape, int); n = 0
    for (i, j) in zip(*np.where(m)):
        if lab[i, j]: continue
        n += 1; st = [(i, j)]; lab[i, j] = n
        while st:
            a, b = st.pop()
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p, q = a + da, b + db
                if 0 <= p < m.shape[0] and 0 <= q < m.shape[1] and m[p, q] and not lab[p, q]:
                    lab[p, q] = n; st.append((p, q))
    return lab, n
for rg in sys.argv[2].split(","):
    lo, hi = [float(t) for t in rg.split("-")]
    lab, n = label((H > lo) & (H < hi))
    for i in range(1, n + 1):
        ys, xs = np.where(lab == i)
        if len(xs) < mn: continue
        print("z %5.1f-%5.1f: x %6.2f..%6.2f y %6.2f..%6.2f zmed %.2f n %d" % (lo, hi, x0 + xs.min() * c, x0 + (xs.max() + 1) * c,
              y0 + ys.min() * c, y0 + (ys.max() + 1) * c, np.median(H[lab == i]), len(xs)))
