# 사진 | 같은 방향 렌더 나란히. usage: python vsphoto.py <asset> <out.png> "photo1:view1;photo2:view2;..."  (view = render.py 이름)
import sys, subprocess, os
from PIL import Image
asset, out, pairs = sys.argv[1], sys.argv[2], [p.split(":") for p in sys.argv[3].split(";")]
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(here, ".."))
import proj  # noqa: E402  (활성 프로젝트: proj.ROOT, 키트: proj.KIT)
views = ",".join(v for _, v in pairs)
tmp = os.path.join(proj.ROOT, "work", "_vs_render.png")
os.makedirs(os.path.dirname(tmp), exist_ok=True)
subprocess.run([sys.executable, os.path.join(proj.KIT, "tools", "render.py"), os.path.join(proj.ROOT, "output", asset), "-o", tmp,
                "--views", views, "--size", "600x1300", "--nolabel"], check=True, capture_output=True, cwd=proj.KIT)
R = Image.open(tmp).convert("RGB"); w = R.width // len(pairs); H = 900
tiles = []
for i, (ph, _) in enumerate(pairs):
    p = Image.open(os.path.join(proj.ROOT, "photos", ph)).convert("RGB"); m = R.crop((i * w, 0, (i + 1) * w, R.height))
    tiles += [p.resize((int(p.width * H / p.height), H)), m.resize((int(m.width * H / m.height), H))]
S = Image.new("RGB", (sum(t.width + 6 for t in tiles), H), "white"); x = 0
for t in tiles:
    S.paste(t, (x, 0)); x += t.width + 6
S.save(out); print(out, S.size)
