# 옥상 난간 조사 4단계: 조각별 판정 -> 같은 가장자리 선(axis, c, s, slab)에서 이어지는 난간 구간으로 합친다.
# 판정: 띠(지붕 +0.5..+1.4) 색의 노란 정도 (r+g)/2-b 중앙값 >= 7 이고 밝기 > 130 이면 난간 (흰 벽은 스캔에서 약간 푸르다: <= 5).
# 자료 없는 짧은 조각(< 0.6 m)은 이웃을 따른다.
# usage: python scripts/rail_decide.py work/rail_survey.json work/rail_runs.json
import json, sys, collections
R = json.load(open(sys.argv[1]))
lines = collections.defaultdict(list)
for r in R:
    band = [s["rgb"] for t, ss in r["samples"] for s in ss[1:] if s and s["rgb"] and abs(s["off"]) < 1.0]
    import statistics as st
    fr = None
    if band:
        yb = st.median([(c[0] + c[1]) / 2 - c[2] for c in band])
        br = st.median([sum(c) / 3 for c in band])
        fr = 1.0 if yb >= 7 and br > 130 else 0.0
    r["beige"] = fr
    lines[(r["dong"], r["part"], r["axis"], r["c"], r["s"], round(r["slab"], 3))].append(r)
runs = []
for key, ps in lines.items():
    ps.sort(key=lambda r: r["a0"])
    dec = []
    for i, r in enumerate(ps):
        if r["beige"] is None or (r["a1"] - r["a0"] < 0.6 and len(ps) > 1):
            dec.append(None)
        else:
            dec.append(r["beige"] >= 0.5 and r["type"] == "W")
    for i in range(len(ps)):                      # short / unknown pieces follow their neighbours (both must agree)
        if dec[i] is None:
            nb = [dec[j] for j in (i - 1, i + 1) if 0 <= j < len(ps) and dec[j] is not None and
                  (abs(ps[j]["a0"] - ps[i]["a1"]) < 0.01 or abs(ps[j]["a1"] - ps[i]["a0"]) < 0.01)]
            dec[i] = bool(nb) and all(nb) and ps[i]["type"] == "W"
    cur = None
    for r, d in zip(ps, dec):
        if d and cur and abs(cur["a1"] - r["a0"]) < 0.01:
            cur["a1"] = r["a1"]
        elif d:
            cur = dict(dong=r["dong"], part=r["part"], axis=r["axis"], c=r["c"], s=r["s"], slab=r["slab"], a0=r["a0"], a1=r["a1"])
            runs.append(cur)
        else:
            cur = None
json.dump(runs, open(sys.argv[2], "w"), indent=0)
tot = collections.defaultdict(float)
cre = collections.defaultdict(float)
for r in runs:
    tot[r["dong"]] += r["a1"] - r["a0"]
for r in R:
    if r["cream"]:
        cre[r["dong"]] += r["a1"] - r["a0"]
for d in sorted(set(r["dong"] for r in R)):
    print(d, "railing runs %d, %.1f m  (model cream %.1f m)" % (sum(1 for r in runs if r["dong"] == d), tot[d], cre[d]))
