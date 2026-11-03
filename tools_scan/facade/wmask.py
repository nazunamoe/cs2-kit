# 스캔 정사영에서 "대표 주기"의 흰 틀 무늬를 사각형 목록으로 (여러 주기 중앙값 -> 흰 마스크 -> 사각형).
# 사용: python scripts/wmask.py <ortho.png> <img_a0> <frame.json> <A0> <A1> <f0> <f1> <period> [thr] [tag]
#   img_a0 = 그림 왼쪽 끝의 a(m), 그림 위 끝 z = 97 (elev.py 를 -1..97 로 렌더), 20 px/m
#   f0..f1 = 주기 시작 층 범위(1 = 1층), period = 반복 층 수. thr 생략 = Otsu
# 출력: 사각형 (a0, a1, dz0, dz1) — dz 는 주기 시작 층 바닥에서의 높이. work/wmask_<tag>.png (중앙값 | 마스크 | 사각형)
import sys, json
import numpy as np
from PIL import Image, ImageDraw
img, ia0, frame = sys.argv[1], float(sys.argv[2]), sys.argv[3]
A0, A1 = float(sys.argv[4]), float(sys.argv[5]); f0, f1, P = int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
thr = float(sys.argv[9]) if len(sys.argv) > 9 and sys.argv[9] != "auto" else None
tag = sys.argv[10] if len(sys.argv) > 10 else "x"
import os
PPM, ZTOP = float(os.environ.get("FACADE_PPM", "20")), float(os.environ.get("FACADE_ZTOP", "97"))   # ortho scale (px/m) and z of the image top
lv = json.load(open(frame))["levels"]                     # floor bottoms, lv[0] = 1F
fh = lv[2] - lv[1]
im = np.asarray(Image.open(img).convert("L"), dtype=np.float32)
c0, c1 = int(round((A0 - ia0) * PPM)), int(round((A1 - ia0) * PPM))
H = int(round(P * fh * PPM))
stack = []
for f in range(f0, f1 + 1, P):
    zb = lv[f - 1]
    r1 = (ZTOP - zb) * PPM                                 # image row of the floor bottom
    rows = np.clip(np.round(r1 - np.arange(H)[::-1] - 0.5).astype(int), 0, im.shape[0] - 1)
    stack.append(im[rows, c0:c1])
med = np.median(np.stack(stack), axis=0)                   # top row = top of the period
if thr is None:                                            # Otsu
    h, e = np.histogram(med, bins=64); best, thr = -1, 128
    for i in range(1, 64):
        w0, w1 = h[:i].sum(), h[i:].sum()
        if w0 == 0 or w1 == 0: continue
        m0 = (h[:i] * e[:i]).sum() / w0; m1 = (h[i:] * e[i:-1]).sum() / w1
        v = w0 * w1 * (m0 - m1) ** 2
        if v > best: best, thr = v, e[i]
mask = (med < thr) if tag.startswith("dark") else (med > thr)   # tag dark*: dark parts (window glass)
# 작은 잡티 정리: 3x3 다수결
from numpy.lib.stride_tricks import sliding_window_view
pad = np.pad(mask, 1, mode="edge"); mask = sliding_window_view(pad, (3, 3)).sum(axis=(2, 3)) >= 5
# 사각형: 행마다 흰 구간 -> 같은 구간이 이어지는 행끼리 합침
def runs(row):
    r, out, s = list(row), [], None
    for i, v in enumerate(r + [False]):
        if v and s is None: s = i
        if not v and s is not None:
            if i - s >= 3: out.append((s, i))
            s = None
    return out
open_ = {}; rects = []
for y in range(H):
    cur = runs(mask[y]); nxt = {}
    for s, e in cur:
        key = next((k for k in open_ if abs(k[0] - s) <= 1 and abs(k[1] - e) <= 1), None)
        nxt[(s, e)] = open_.pop(key) if key else y
    for (s, e), y0 in open_.items(): rects.append((s, e, y0, y))
    open_ = nxt
for (s, e), y0 in open_.items(): rects.append((s, e, y0, H))
out = []
for s, e, y0, y1 in rects:
    if (y1 - y0) < 4 or (e - s) < 4: continue          # < 0.2 m: noise (light sill panels, window frames)
    a0, a1 = A0 + s / PPM, A0 + e / PPM
    dz1, dz0 = (H - y0) / PPM, (H - y1) / PPM                # rows count from the top
    out.append((round(a0, 2), round(a1, 2), round(dz0, 2), round(dz1, 2)))
out.sort(key=lambda r: (r[2], r[0]))
print(f"# {img} A {A0}..{A1} floors {f0}..{f1} period {P} ({len(stack)} samples) thr {thr:.0f}  {len(out)} rects")
import os
if os.environ.get("FLIP"):                                # back / west views: generator coordinate = -a
    print("# FLIP: generator x = -a")
    for r in sorted(out, key=lambda r: (r[2], -r[1])): print("    (%.2f, %.2f, %.2f, %.2f)," % (-r[1], -r[0], r[2], r[3]))
else:
    for r in out: print("    (%.2f, %.2f, %.2f, %.2f)," % r)
k = 3
g = Image.fromarray(med.astype(np.uint8)).convert("RGB").resize((mask.shape[1] * k, H * k))
mk = Image.fromarray((mask * 255).astype(np.uint8)).convert("RGB").resize(g.size)
rc = g.copy(); d = ImageDraw.Draw(rc)
for a0, a1, dz0, dz1 in out:
    d.rectangle([(a0 - A0) * PPM * k, (H - dz1 * PPM) * k, (a1 - A0) * PPM * k, (H - dz0 * PPM) * k], outline=(255, 0, 0))
sheet = Image.new("RGB", (g.width, g.height * 3 + 8), "white")
sheet.paste(g, (0, 0)); sheet.paste(mk, (0, g.height + 4)); sheet.paste(rc, (0, 2 * g.height + 8))
sheet.save(f"work/wmask_{tag}.png")
# 눈금 그림: 중앙값 x4, 세로선 0.5 m (1 m 마다 숫자), 가로선 0.25 m (0.5 m 마다 숫자)
k = 4
G = Image.fromarray(med.astype(np.uint8)).convert("RGB").resize((mask.shape[1] * k, H * k), Image.BICUBIC)
d = ImageDraw.Draw(G)
import math
a = math.ceil(A0 * 2) / 2
while a <= A1:
    x = (a - A0) * PPM * k
    d.line([(x, 0), (x, G.height)], fill=(255, 60, 60) if abs(a - round(a)) < 1e-6 else (255, 190, 190), width=1)
    if abs(a - round(a)) < 1e-6: d.text((x + 2, 2), str(int(round(a))), fill=(255, 255, 0))
    a += 0.5
dz = 0.0
while dz <= H / PPM:
    y = (H - dz * PPM) * k
    d.line([(0, y), (G.width, y)], fill=(60, 160, 255) if abs(dz * 2 - round(dz * 2)) < 1e-6 else (170, 210, 255), width=1)
    if abs(dz * 2 - round(dz * 2)) < 1e-6: d.text((2, y - 12), f"{dz:.1f}", fill=(0, 255, 255))
    dz += 0.25
G.save(f"work/wgrid_{tag}.png")
