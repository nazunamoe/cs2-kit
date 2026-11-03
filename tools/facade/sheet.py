# contact sheet: sheet.py out.png cols cellw files...
import sys
from PIL import Image, ImageDraw
out, cols, cw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
fs = sys.argv[4:]
ims = []
for f in fs:
    im = Image.open(f).convert("RGB"); r = cw / im.width
    ims.append((f, im.resize((cw, int(im.height * r)))))
ch = max(i.height for _, i in ims)
rows = (len(ims) + cols - 1) // cols
S = Image.new("RGB", (cols * cw, rows * (ch + 18)), (255, 255, 255))
d = ImageDraw.Draw(S)
for k, (f, im) in enumerate(ims):
    x, y = (k % cols) * cw, (k // cols) * (ch + 18)
    S.paste(im, (x, y + 18)); d.text((x + 4, y + 3), f.split("/")[-1] + " %dx%d" % Image.open(f).size, fill=(255, 0, 0))
S.save(out); print(out, S.size)
