# 정사영에서 층 범위를 확대 + 생성기 좌표 눈금. usage: python fcrop.py <img> <a0> <sign> <g0> <g1> <k0> <k1> <out> [zoom=2] [gf fh dz ztop]
# a0: 그림 왼쪽 끝의 a, sign: gen = sign*a. g0..g1 = 생성기 좌표 범위. 층 k0..k1(포함) 보임. 층 바닥선(초록)과 +1 m 눈금
import sys
from PIL import Image, ImageDraw
f, a0, sg, g0, g1, k0, k1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), sys.argv[8]
zm = float(sys.argv[9]) if len(sys.argv) > 9 else 2
gf, fh, dz, ztop = [float(v) for v in sys.argv[10:14]] if len(sys.argv) > 13 else (5.3, 2.856, 2.0, 132.0)
lv = lambda k: 0.0 if k == 1 else gf + (k - 2) * fh
im = Image.open(f).convert("RGB")
a_l, a_r = sorted((g0 * sg, g1 * sg))
z_lo, z_hi = lv(k0) - 0.3, lv(k1 + 1) + 0.3
box = (int((a_l - a0) * 20), int((ztop - (z_hi + dz)) * 20), int((a_r - a0) * 20), int((ztop - (z_lo + dz)) * 20))
c = im.crop(box).resize((int((box[2] - box[0]) * zm), int((box[3] - box[1]) * zm)), Image.LANCZOS)
pad = 34
S = Image.new("RGB", (c.width + pad, c.height + pad), "white"); S.paste(c, (pad, 0)); d = ImageDraw.Draw(S)
pxm = 20 * zm
for k in range(k0, k1 + 2):
    y = (z_hi - lv(k)) * pxm
    d.line([(pad - 6, y), (S.width, y)], fill=(0, 220, 0)); d.text((1, y - 6), "F%d" % k, fill=(0, 120, 0))
    for r in (1.0, 2.0):
        yy = (z_hi - lv(k) - r) * pxm; d.line([(pad - 4, yy), (pad, yy)], fill=(0, 0, 0))
import math
g = math.ceil(min(g0, g1) * 4) / 4
while g <= max(g0, g1):
    a = g * sg; x = pad + (a - a_l) * pxm
    big = abs(g - round(g)) < 1e-6
    d.line([(x, c.height), (x, c.height + (10 if big else 4))], fill=(255, 0, 0))
    if big:
        d.line([(x, 0), (x, c.height)], fill=(255, 80, 80)); d.text((x + 2, c.height + 12), "%d" % round(g), fill=(200, 0, 0))
    g += 0.25
S.save(out); print(out, S.size)
