import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import sys
TA = gen()
from PIL import Image, ImageDraw
for mir, tag in ((False, "A"), (True, "B")):
    E = TA.edges_of(TA.full_poly(TA.HALF, mir))
    sc = 22; W, H = 80*sc, 56*sc
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    P = lambda x, y: (W/2 + x*sc, H/2 - y*sc)   # +y up, front (-y) at bottom
    for e in E:
        p, q = P(*e["p"]), P(*e["q"])
        col = (30,40,120) if TA.is_bal(e) else (200,0,0)
        d.line([p, q], fill=col, width=4)
        mx, my = (p[0]+q[0])/2, (p[1]+q[1])/2
        nx, ny = (e["s"]*18, 0) if e["axis"] == "x" else (0, -e["s"]*18)
        d.text((mx+nx-6, my+ny-5), str(e["i"]), fill=(0,0,0))
    d.text((10,10), tag + "  bottom = front (-y). blue=is_bal  red=head", fill=(0,0,0))
    im.save(os.path.join(ROOT, r"previews\plan_%s.png") % tag)
