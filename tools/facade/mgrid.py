# mgrid.py img h0 z1 ppm x0 x1 z0 zz1 zoom out [step] : crop in metres + metre grid (labels in m)
import sys
from PIL import Image, ImageDraw
f, h0, z1, ppm, x0, x1, z0, zz1, zoom, out = sys.argv[1], *map(float, sys.argv[2:10]), sys.argv[10]
step = float(sys.argv[11]) if len(sys.argv) > 11 else 1.0
im = Image.open(f).convert("RGB")
c = im.crop((int((x0 - h0) * ppm), int((z1 - zz1) * ppm), int((x1 - h0) * ppm), int((z1 - z0) * ppm)))
c = c.resize((int(c.width * zoom), int(c.height * zoom)), Image.NEAREST)
d = ImageDraw.Draw(c); s = ppm * zoom
import math
k = math.ceil(x0 / step)
while k * step <= x1:
    X = (k * step - x0) * s; bold = abs((k * step) % 5) < 1e-6
    d.line([X, 0, X, c.height], fill=(255, 0, 0) if bold else (255, 150, 150), width=1)
    d.text((X + 2, 2), "%g" % (k * step), fill=(255, 0, 0)); k += 1
k = math.ceil(z0 / step)
while k * step <= zz1:
    Y = (zz1 - k * step) * s; bold = abs((k * step) % 5) < 1e-6
    d.line([0, Y, c.width, Y], fill=(0, 0, 255) if bold else (150, 150, 255), width=1)
    d.text((2, Y + 1), "%g" % (k * step), fill=(0, 0, 255)); k += 1
c.save(out); print(out, c.size)
