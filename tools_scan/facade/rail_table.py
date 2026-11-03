# 옥상 난간 조사 5단계: rail_runs.json -> 생성기에 넣을 ROOF_RAILS 표 (106 두 동체 이음매처럼 다른 동체 안에 묻힌 구간은 뺀다)
# usage: python scripts/rail_table.py work/rail_runs.json > work/roof_rails_table.py
import json, sys, math, importlib.util, os
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("gen", os.path.join(here, "..", os.environ.get("FACADE_GEN", "generator_cs2.py")))
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
runs = json.load(open(sys.argv[1]))
out = {}
for r in runs:
    T = G.TOWERS[r["dong"]]()
    parts = T.get("parts", [dict()])
    def tw(P, x, y):
        a = math.radians(P.get("rot", 0.0)); mx, my = P.get("move", (0.0, 0.0))
        return (math.cos(a) * x - math.sin(a) * y + mx, math.sin(a) * x + math.cos(a) * y + my)
    def inv(P, x, y):
        a = math.radians(-P.get("rot", 0.0)); mx, my = P.get("move", (0.0, 0.0))
        x, y = x - mx, y - my
        return (math.cos(a) * x - math.sin(a) * y, math.sin(a) * x + math.cos(a) * y)
    m = (r["a0"] + r["a1"]) / 2
    p = (m, r["c"] + r["s"] * 0.6) if r["axis"] == "y" else (r["c"] + r["s"] * 0.6, m)
    P0 = parts[r["part"]]
    q = tw(P0, *p)
    buried = False
    for pj, P in enumerate(parts):
        if pj == r["part"]:
            continue
        x, y = inv(P, *q)
        if any(b[0] < x < b[1] and b[2] < y < b[3] and b[4] > r["slab"] - 3.0 for b in dict(T, **P)["blocks"]):
            buried = True
    if buried:
        print("# dropped (inside the other body):", r["dong"], r["part"], r["axis"], r["c"], r["a0"], r["a1"], file=sys.stderr)
        continue
    out.setdefault(r["dong"], []).append((r["part"], r["axis"], round(r["c"], 3), r["s"], round(r["a0"], 3), round(r["a1"], 3), round(r["slab"], 3)))
print("ROOF_RAILS = {")
for d in sorted(out):
    print('    "%s": [' % d)
    rs = sorted(out[d])
    for i in range(0, len(rs), 3):
        print("        " + " ".join("%s," % (t,) for t in rs[i:i + 3]))
    print("    ],")
print("}")
