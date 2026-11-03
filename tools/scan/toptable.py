# 높이장 표 (칸 step m, 값 = 칸 중앙값 - base, 0.1 m 단위 정수). usage: python toptable.py <top.npz> x0 x1 y0 y1 [step=1] [base=100]
import sys, numpy as np
d = np.load(sys.argv[1]); H = d["H"]; X0 = float(d["x0"]); Y0 = float(d["y0"]); c = float(d["cell"])
x0, x1, y0, y1 = [float(v) for v in sys.argv[2:6]]
st = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
base = float(sys.argv[7]) if len(sys.argv) > 7 else 100.0
xs = np.arange(x0, x1 + 1e-6, st); ys = np.arange(y1, y0 - 1e-6, -st)
k = max(1, int(st / c))
print("      " + "".join("%5.0f" % x if abs(x - round(x)) < 1e-6 else "%5.1f" % x for x in xs))
for y in ys:
    row = []
    for x in xs:
        i, j = int((y - Y0) / c), int((x - X0) / c)
        b = H[max(i, 0):i + k, max(j, 0):j + k]
        v = np.median(b) if b.size else -1
        row.append("    ." if v < 1 else "%5d" % round((v - base) * 10))
    print("%5.1f " % y + "".join(row))
