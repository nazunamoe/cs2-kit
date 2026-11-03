# 스캔 메시 수평 단면 그림 (생성기 좌표). usage: python secimg.py <npz> <mesh> <yaw> <z1,z2,..> <out.png> [ppm=12] [dy=0]
import sys, numpy as np
from PIL import Image, ImageDraw
npz, m, yaw, zs, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), [float(v) for v in sys.argv[4].split(",")], sys.argv[5]
ppm = float(sys.argv[6]) if len(sys.argv) > 6 else 12
dy = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0
d = np.load(npz); V = d["V" + m].copy(); F = d["F" + m]
r = np.radians(-yaw); c, s = np.cos(r), np.sin(r)
x, y = V[:, 0] * c - V[:, 1] * s, V[:, 0] * s + V[:, 1] * c
V[:, 0], V[:, 1] = x - (x.min() + x.max()) / 2, y - y.min() - dy
V[:, 2] -= V[:, 2].min()
X0, X1, Y0, Y1 = V[:, 0].min() - 2, V[:, 0].max() + 2, V[:, 1].min() - 2, V[:, 1].max() + 2
W, H = int((X1 - X0) * ppm), int((Y1 - Y0) * ppm)
T = V[F]
cols = [(255, 0, 0), (0, 160, 0), (0, 0, 255), (200, 0, 200), (0, 170, 170), (230, 120, 0), (0, 0, 0), (120, 120, 0)]
P = lambda px, py: ((px - X0) * ppm, (Y1 - py) * ppm)
tiles = []
for k, zc in enumerate(zs):
    im = Image.new("RGB", (W, H + 16), "white"); dr = ImageDraw.Draw(im)
    for gx in range(int(np.ceil(X0)), int(X1) + 1):
        if gx % 5 == 0:
            dr.line([P(gx, Y0), P(gx, Y1)], fill=(170, 170, 170) if gx % 10 else (110, 110, 110)); dr.text((P(gx, Y1)[0] + 2, H + 2), str(gx), fill=(0, 0, 0))
    for gy in range(int(np.ceil(Y0)), int(Y1) + 1):
        if gy % 5 == 0:
            dr.line([P(X0, gy), P(X1, gy)], fill=(170, 170, 170) if gy % 10 else (110, 110, 110)); dr.text((2, P(X0, gy)[1] + 2), str(gy), fill=(0, 0, 0))
    sz = T[:, :, 2] - zc
    for i in range(T.shape[0]):
        sg = sz[i]
        if (sg > 0).all() or (sg < 0).all():
            continue
        pts = []
        for a_, b_ in ((0, 1), (1, 2), (2, 0)):
            if (sg[a_] < 0) != (sg[b_] < 0):
                u = sg[a_] / (sg[a_] - sg[b_]); pts.append(T[i, a_] + u * (T[i, b_] - T[i, a_]))
        if len(pts) == 2:
            dr.line([P(*pts[0][:2]), P(*pts[1][:2])], fill=cols[k % len(cols)], width=2)
    dr.text((W - 70, 4), "z %.1f" % zc, fill=(0, 0, 0))
    tiles.append(im)
n = len(tiles); cc = 2 if n > 1 else 1; rr = (n + cc - 1) // cc
S = Image.new("RGB", (cc * W + 8, rr * (H + 24)), "white")
for k, im in enumerate(tiles):
    S.paste(im, ((k % cc) * (W + 8), (k // cc) * (H + 24)))
S.save(out); print(out, S.size)
