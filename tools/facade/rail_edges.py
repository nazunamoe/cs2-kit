# 옥상 난간 조사 1단계: 생성기에서 동마다 파라펫 위 외벽 조각(지붕 + PARAPET 로 끝나는 조각)을 뽑아 JSON 으로 저장.
# usage: python tools/facade/rail_edges.py out.json [101,102,...]
# 출력 항목: dong, part, axis, c, s, a0, a1, slab, type, mat, cream (지금 모델이 크림 띠로 칠하는지), rot, move
import os, sys, json, importlib.util
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from _gen import gen_path  # noqa: E402  (활성 프로젝트의 생성기)
gen = gen_path()
spec = importlib.util.spec_from_file_location("gen", gen)
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)
out_path = sys.argv[1]
dongs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["101", "102", "103", "104", "105", "106", "107", "108"]
rows = []
for d in dongs:
    T = G.TOWERS[d]()
    for pi, P in enumerate(T.get("parts", [dict()])):
        TP = G.expand_slots(dict(T, **P))
        blocks = G.with_parapets(TP["blocks"])
        tops = [b[4] + G.PARAPET for b in TP["blocks"]]
        xs, ys, H = G.heightfield(blocks)
        for w in G.walls_of(xs, ys, H):
            if not any(abs(w["z1"] - t) < 1e-3 for t in tops) or w["z1"] < 15.0 + G.PARAPET or w["z0"] > w["z1"] - G.PARAPET - 0.5:
                continue
            pieces = G.split_zones(w, TP)
            cream = G.cream_split(TP, pieces)
            for a0, a1, z0, z1, zone in cream:
                if abs(z1 - w["z1"]) > 1e-3:
                    continue
                rows.append(dict(dong=d, part=pi, axis=w["axis"], c=w["c"], s=w["s"], a0=a0, a1=a1, slab=w["z1"] - G.PARAPET, wz0=w["z0"],
                                 type=zone["t"], mat=zone.get("mat"), cream=zone.get("mat") == "cream",
                                 rot=P.get("rot", 0.0), move=list(P.get("move", (0.0, 0.0)))))
json.dump(rows, open(out_path, "w"), indent=0)
print(len(rows), "pieces;", sum(r["cream"] for r in rows), "cream")
