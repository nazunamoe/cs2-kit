import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import sys, glob, os
from PIL import Image
pat, out = sys.argv[1], sys.argv[2]
fs = sorted(glob.glob(pat))
ims = [Image.open(f) for f in fs]
hs = [im.crop((im.size[0] // 2, 0, im.size[0], im.size[1])) for im in ims]   # overlay halves
H = 900
hs = [h.resize((max(1, h.size[0] * H // h.size[1]), H)) for h in hs]
W = sum(h.size[0] for h in hs) + 8 * len(hs)
o = Image.new("RGB", (W, H), "white"); x = 0
for h in hs:
    o.paste(h, (x, 0)); x += h.size[0] + 8
if W > 2400:
    o = o.resize((2400, H * 2400 // W))
o.save(out); print([os.path.basename(f) for f in fs])
