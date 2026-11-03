import sys, numpy as np
from PIL import Image
f, a0, c0, c1, H = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
im = np.asarray(Image.open(f).convert("L")).astype(float)
x0, x1 = int((c0 - a0) * 20), int((c1 - a0) * 20)
prof = im[:, x0:x1].mean(1)             # row mean
# window rows are darker: find local minima centres
z = lambda y: H - y / 20
def find_peaks_simple(v, dist, prom):
    idx=[]
    for i in range(dist, len(v)-dist):
        w=v[i-dist:i+dist+1]
        if v[i]==w.min() and (w.max()-v[i])>=prom: idx.append(i)
    out=[]
    for i in idx:
        if not out or i-out[-1]>=dist: out.append(i)
    return out
p = find_peaks_simple(-(-prof), 25, 8)
zs = [z(y) for y in p]
print("n minima", len(zs))
print(" ".join("%.2f" % v for v in sorted(zs)))
d = np.diff(sorted(zs)); print("diffs median %.3f" % np.median(d)); print(" ".join("%.2f" % v for v in d))
