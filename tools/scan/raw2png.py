# tex<i>.rgba + tex<i>.json -> tex<i>.png (ktx2raw.js 결과)
import sys, os, json, glob
from PIL import Image
d = sys.argv[1]
for j in sorted(glob.glob(os.path.join(d, "tex*.json"))):
    s = json.load(open(j)); raw = j[:-5] + ".rgba"
    Image.frombytes("RGBA", (s["w"], s["h"]), open(raw, "rb").read()).save(j[:-5] + ".png")
    os.remove(raw)
print("png", len(glob.glob(os.path.join(d, "tex*.png"))))
