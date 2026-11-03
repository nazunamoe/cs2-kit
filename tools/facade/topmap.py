# 스캔 메시(npz: V<mesh>, F<mesh>)를 생성기 좌표로 옮겨 위에서 본 높이장(셀마다 최고 z)을 만든다.
# usage: python topmap.py <npz> <mesh> <yaw> <out_prefix> [cell=0.25] [dy=0]
# 생성기 좌표: -yaw 회전, x 중앙, 정면(최소 y) = -dy, 최저 z = 0. 출력: <out>.npz (H, x0, y0, cell), <out>.png (그림 + 5 m 격자)
import sys, numpy as np
from PIL import Image, ImageDraw
npz, m, yaw, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
cell = float(sys.argv[5]) if len(sys.argv) > 5 else 0.25
dy = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
d = np.load(npz); V = d["V" + m].copy(); F = d["F" + m]
r = np.radians(-yaw); c, s = np.cos(r), np.sin(r)
x, y = V[:, 0] * c - V[:, 1] * s, V[:, 0] * s + V[:, 1] * c
V[:, 0], V[:, 1] = x - (x.min() + x.max()) / 2, y - y.min() - dy
V[:, 2] -= V[:, 2].min()
x0, y0 = V[:, 0].min() - 1, V[:, 1].min() - 1
nx, ny = int((V[:, 0].max() - x0 + 1) / cell) + 1, int((V[:, 1].max() - y0 + 1) / cell) + 1
H = np.full((ny, nx), -1.0)
T = V[F]                                            # (n,3,3)
for k in range(T.shape[0]):                         # 삼각형을 칸 크기보다 촘촘히 표본
    a, b, cc = T[k]
    L = max(np.linalg.norm(b - a), np.linalg.norm(cc - a), np.linalg.norm(cc - b))
    n = max(2, int(L / (cell * 0.5)) + 1)
    u, v = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n)); msk = u + v <= 1
    u, v = u[msk], v[msk]
    P = a + np.outer(u, b - a) + np.outer(v, cc - a)
    ix = ((P[:, 0] - x0) / cell).astype(int); iy = ((P[:, 1] - y0) / cell).astype(int)
    np.maximum.at(H, (iy, ix), P[:, 2])
np.savez(out + ".npz", H=H, x0=x0, y0=y0, cell=cell)
print("x %.2f..%.2f  y %.2f..%.2f  zmax %.2f" % (V[:, 0].min(), V[:, 0].max(), V[:, 1].min(), V[:, 1].max(), V[:, 2].max()))
# 그림: 위가 +y(뒤), 정면(-y)이 아래
z = H.copy(); lo = 60.0; z[z < 0] = np.nan
g = np.clip((np.nan_to_num(z, nan=0) - lo) / (np.nanmax(z) - lo), 0, 1)
img = (np.stack([g, g * 0.8 + 0.2 * (z > 0), 1 - g], -1) * 255).astype(np.uint8)[::-1]
S = 6
im = Image.fromarray(img).resize((nx * S, ny * S), Image.NEAREST); dr = ImageDraw.Draw(im)
for gx in np.arange(np.ceil(x0 / 5) * 5, x0 + nx * cell, 5):
    px = (gx - x0) / cell * S; dr.line([(px, 0), (px, ny * S)], fill=(255, 255, 255) if gx % 10 == 0 else (120, 120, 120)); dr.text((px + 2, 2), "%g" % gx, fill=(255, 255, 0))
for gy in np.arange(np.ceil(y0 / 5) * 5, y0 + ny * cell, 5):
    py = (ny - (gy - y0) / cell) * S; dr.line([(0, py), (nx * S, py)], fill=(255, 255, 255) if gy % 10 == 0 else (120, 120, 120)); dr.text((2, py + 2), "%g" % gy, fill=(255, 255, 0))
im.save(out + ".png"); print(out + ".png", im.size)
