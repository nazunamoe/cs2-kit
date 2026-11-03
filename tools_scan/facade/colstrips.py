# 대표 주기 중앙값 그림에서 "세로로 끝까지 이어진" 흰 띠·갈색 띠 열 구간을 찾는다(기둥·세로 띠 도색용).
# 사용: python scripts/colstrips.py <ortho> <ia0> <frame> <A0> <A1> <f0> <f1> <period> [flip] [wthr=135] [bthr=9]
#   A0/A1 = 생성기 x 범위 (flip=1 이면 그림에서 -x 로 찾아 읽음). 출력: white=[(a0,a1)...] brown=[...] + 줄 높이(가로 흰 띠)
import sys, json
import numpy as np
from PIL import Image
img, ia0, frame = sys.argv[1], float(sys.argv[2]), sys.argv[3]
A0, A1, f0, f1, P = float(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
flip = len(sys.argv) > 9 and sys.argv[9] == "1"
wthr = float(sys.argv[10]) if len(sys.argv) > 10 else 135
bthr = float(sys.argv[11]) if len(sys.argv) > 11 else 9
import os
PPM, ZTOP = float(os.environ.get("FACADE_PPM", "20")), float(os.environ.get("FACADE_ZTOP", "97"))   # ortho scale (px/m) and z of the image top
lv = json.load(open(frame))["levels"]; fh = lv[2] - lv[1]
im = np.asarray(Image.open(img).convert("RGB"), dtype=np.float32)
xs = np.arange(A0, A1, 0.05)
H = int(round(P * fh * PPM)); stack = []
cols = np.array([int(round(((-x if flip else x) - ia0) * PPM)) for x in xs])
for f in range(f0, f1 + 1, P):
    r1 = (ZTOP - lv[f - 1]) * PPM
    rows = np.clip(np.round(r1 - np.arange(H)[::-1] - 0.5).astype(int), 0, im.shape[0] - 1)
    stack.append(im[rows][:, cols])
med = np.median(np.stack(stack), axis=0)          # (H, nx, 3), top row = top of period
L = med.mean(2); hue = med[..., 0] - med[..., 2]
inner = slice(int(0.06 * H), int(0.94 * H))     # ignore the floor-line rows (bands)
wf = (L[inner] > wthr).mean(0)
bf = ((hue[inner] > bthr) & (L[inner] <= wthr)).mean(0)
def runs(mask, minw=0.15):
    out, s = [], None
    for x, v in zip(list(xs) + [xs[-1] + 0.05], list(mask) + [False]):
        if v and s is None: s = x
        if not v and s is not None:
            if x - s >= minw - 1e-6: out.append((round(float(s), 2), round(float(x), 2)))
            s = None
    return out
white = runs(wf > 0.85); brown = runs((bf > 0.55) & ~(wf > 0.85))
print("white =", white)
print("brown =", brown)
# horizontal white bands: rows where most columns (outside brown zones) are white
rowfrac = (L > wthr).mean(1)
bands, s = [], None
for y, v in enumerate(list(rowfrac > 0.45) + [False]):
    if v and s is None: s = y
    if not v and s is not None:
        bands.append((round((H - y) / PPM, 2), round((H - s) / PPM, 2))); s = None
print("bands (dz in period) =", bands)
