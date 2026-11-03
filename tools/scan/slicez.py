# 스캔을 높이 z 에서 잘라 선분 출력 (x>-22, y<36)
import numpy as np, sys
d = np.load(sys.argv[1]); V, T = d["V"], d["T"]
for zc in [float(s) for s in sys.argv[2].split(",")]:
    segs = []
    for t in T:
        P = V[t]; s = P[:, 2] - zc
        pts = []
        for i in range(3):
            a, b = P[i], P[(i+1) % 3]; sa, sb = s[i], s[(i+1) % 3]
            if (sa < 0) != (sb < 0):
                u = sa / (sa - sb); pts.append(a + u * (b - a))
        if len(pts) == 2 and np.linalg.norm(pts[0][:2]-pts[1][:2]) > 0.3:
            segs.append((pts[0][:2], pts[1][:2]))
    print("== z", zc, len(segs))
    for p, q in sorted(segs, key=lambda s: (round(min(s[0][1], s[1][1])), min(s[0][0], s[1][0]))):
        print("  (%6.2f,%6.2f)-(%6.2f,%6.2f) len %.1f" % (p[0], p[1], q[0], q[1], np.linalg.norm(p-q)))
