# 옥상 난간 조사: 동마다 평면도 (덩어리 = 회색, 난간 구간 = 빨강, 지금 크림 조각 = 노랑 점선)
# usage: python scripts/rail_plan.py work/rail_runs.json work/rail_survey.json previews/rail/plan.png
import json, sys, math, importlib.util, os
from PIL import Image, ImageDraw
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("gen", os.path.join(here, "..", os.environ.get("FACADE_GEN", "generator_cs2.py")))
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
runs = json.load(open(sys.argv[1])); S = json.load(open(sys.argv[2]))
K, W, H = 9, 560, 440
sheet = Image.new("RGB", (W * 4, H * 2), "white")
for n, d in enumerate(["101", "102", "103", "104", "105", "106", "107", "108"]):
    im = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(im)
    T = G.TOWERS[d]()
    parts = T.get("parts", [dict()])
    def tw(P, x, y):
        r = math.radians(P.get("rot", 0.0)); mx, my = P.get("move", (0.0, 0.0))
        return (math.cos(r) * x - math.sin(r) * y + mx, math.sin(r) * x + math.cos(r) * y + my)
    px = lambda p: (W / 2 + p[0] * K, H - 30 - (p[1] + 4) * K * 0.9)
    for pi, P in enumerate(parts):
        TP = dict(T, **P)
        for b in TP["blocks"]:
            if b[4] < 15: continue
            q = [px(tw(P, x, y)) for x, y in ((b[0], b[2]), (b[1], b[2]), (b[1], b[3]), (b[0], b[3]))]
            g = int(235 - min(1.0, (b[4] - 60) / 80) * 120)
            dr.polygon(q, fill=(g, g, g), outline=(150, 150, 150))
    for r in S:
        if r["dong"] != d or not r["cream"]: continue
        P = parts[r["part"]]
        a, b = ((r["a0"], r["c"]), (r["a1"], r["c"])) if r["axis"] == "y" else ((r["c"], r["a0"]), (r["c"], r["a1"]))
        dr.line([px(tw(P, *a)), px(tw(P, *b))], fill=(230, 190, 0), width=7)
    for r in runs:
        if r["dong"] != d: continue
        P = parts[r["part"]]
        a, b = ((r["a0"], r["c"]), (r["a1"], r["c"])) if r["axis"] == "y" else ((r["c"], r["a0"]), (r["c"], r["a1"]))
        dr.line([px(tw(P, *a)), px(tw(P, *b))], fill=(220, 0, 0), width=3)
    dr.text((8, 8), d + "  red = railing (scan), yellow = model cream now; front (-Y) at the bottom", fill=(0, 0, 0))
    sheet.paste(im, ((n % 4) * W, (n // 4) * H))
sheet.save(sys.argv[3])
