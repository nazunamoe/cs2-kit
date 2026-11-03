# 옥상 난간 조사 3단계: rail_survey.json -> 조각별 표 (띠 색 / 아래 벽 색 / 세로 단면에서 띠 높이)
# usage: python scripts/rail_report.py work/rail_survey.json [dong]
import json, sys, numpy as np
R = json.load(open(sys.argv[1]))
only = sys.argv[2] if len(sys.argv) > 2 else None
def med(cs):
    return tuple(int(v) for v in np.median(np.array(cs), 0)) if cs else None
for r in R:
    if only and r["dong"] != only:
        continue
    band, beige = [], 0
    for t, ss in r["samples"]:
        for s in ss[1:]:
            if s and s["rgb"] and abs(s["off"]) < 1.0:
                band.append(s["rgb"]); beige += s["rgb"][0] - s["rgb"][2] > 14
    below = [p[1]["rgb"] for p in r["profile"] if p[0] < -0.15 and p[1] and p[1]["rgb"] and abs(p[1]["off"]) < 1.0]
    prof = "".join(("B" if c[0] - c[2] > 14 and sum(c) > 360 else ("w" if sum(c) > 450 else ("g" if sum(c) > 270 else "."))) if c else " "
                   for c in [(p[1]["rgb"] if p[1] and p[1]["rgb"] and abs(p[1]["off"]) < 1.0 else None) for p in r["profile"]])
    side = {("y", -1): "F", ("y", 1): "B", ("x", -1): "L", ("x", 1): "R"}[(r["axis"], r["s"])]
    fr = beige / len(band) if band else -1
    print("%s p%d %s c=%7.2f a=%7.2f..%7.2f L=%5.1f slab=%6.2f %s/%-7s cream=%d beige=%.2f band=%s below=%s prof[-0.6..1.9]=%s" % (
        r["dong"], r["part"], side, r["c"], r["a0"], r["a1"], r["a1"] - r["a0"], r["slab"], r["type"], r["mat"], r["cream"], fr,
        med(band), med(below), prof))
