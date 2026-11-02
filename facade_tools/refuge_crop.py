import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import sys
import numpy as np
from PIL import Image, ImageDraw
import photo_sections as P
# refcrop.py kind photo sec out -> crop floors 27..31 of the section, 3x, with floor 29 marked
kind, pi, sname, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
ph = P.PHOTOS[kind][pi]; sec = [s for s in ph["secs"] if s["name"] == sname][0]
im = Image.open(P.os.path.join(P.ROOT, ph["file"])).convert("RGB")
g = np.asarray(im.convert("L"), np.float32)
x0, x1 = sorted(sec["px"])
yc, p = P.fit_rows(g, sec, int(x0), int(x1), np.zeros(g.shape, bool))
pp = abs(p)
def line(f):  # floor line of floor f (bottom)
    return yc(f) + 0.62 * abs(yc(f + 0.5) - yc(f - 0.5))
ya, yb = line(31) - pp, line(27)
c = im.crop((int(x0) - 5, int(ya), int(x1) + 5, int(yb)))
c = c.resize((c.size[0] * 3, c.size[1] * 3), Image.LANCZOS)
d = ImageDraw.Draw(c)
for f, col in ((29, (255, 0, 0)), (30, (255, 0, 0))):
    y = (line(f) - ya) * 3 if f == 29 else (line(28) - ya) * 3
    d.line([(0, y), (12, y)], fill=col, width=3)
y29a, y29b = (line(29) - pp - ya) * 3, (line(29) - ya) * 3
d.rectangle([0, y29a, 10, y29b], fill=(255, 0, 0))
c.save(out)
