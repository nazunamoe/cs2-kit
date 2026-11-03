# 단면 선분을 축 정렬 벽으로 합쳐 출력. usage: python secseg.py <npz> <mesh> <yaw> <z> [dy=0] [minlen=0.3]
import sys, numpy as np
npz, m, yaw, zc = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
dy = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
ml = float(sys.argv[6]) if len(sys.argv) > 6 else 0.3
d = np.load(npz); V = d["V" + m].copy(); F = d["F" + m]
r = np.radians(-yaw); c, s = np.cos(r), np.sin(r)
x, y = V[:, 0] * c - V[:, 1] * s, V[:, 0] * s + V[:, 1] * c
V[:, 0], V[:, 1] = x - (x.min() + x.max()) / 2, y - y.min() - dy
V[:, 2] -= V[:, 2].min()
T = V[F]; sz = T[:, :, 2] - zc
segs = []
for i in np.where(~((sz > 0).all(1) | (sz < 0).all(1)))[0]:
    sg = sz[i]; pts = []
    for a_, b_ in ((0, 1), (1, 2), (2, 0)):
        if (sg[a_] < 0) != (sg[b_] < 0):
            u = sg[a_] / (sg[a_] - sg[b_]); pts.append(T[i, a_] + u * (T[i, b_] - T[i, a_]))
    if len(pts) == 2:
        segs.append((pts[0][:2], pts[1][:2]))
# 축 정렬 벽 모으기: 방향별로 좌표(반올림 0.05) -> 구간 합치기
walls = {}
for p, q in segs:
    dx, dy_ = abs(p[0] - q[0]), abs(p[1] - q[1])
    if dx < 0.08 * max(dy_, 1e-3) and dy_ > 0.02:
        k = ("x", round((p[0] + q[0]) / 2 / 0.05) * 0.05); a0, a1 = sorted((p[1], q[1]))
    elif dy_ < 0.08 * max(dx, 1e-3) and dx > 0.02:
        k = ("y", round((p[1] + q[1]) / 2 / 0.05) * 0.05); a0, a1 = sorted((p[0], q[0]))
    else:
        print("  diag (%.2f,%.2f)-(%.2f,%.2f)" % (p[0], p[1], q[0], q[1])); continue
    walls.setdefault(k, []).append((a0, a1))
out = []
for k, iv in walls.items():
    iv.sort(); cur = list(iv[0])
    for a0, a1 in iv[1:]:
        if a0 <= cur[1] + 0.15:
            cur[1] = max(cur[1], a1)
        else:
            out.append((k, cur)); cur = [a0, a1]
    out.append((k, cur))
for (ax, cc), (a0, a1) in sorted(out, key=lambda t: (t[0][0], t[0][1], t[1][0])):
    if a1 - a0 >= ml:
        print("%s=%7.2f  %7.2f .. %7.2f  (%.2f)" % (ax, cc, a0, a1, a1 - a0))
