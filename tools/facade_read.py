# -*- coding: utf-8 -*-
"""
facade_read.py - photo_refs.json 의 모든 facade 항목을 한 번에 돌려(facade_paint.py 의 floor/window
찾기를 그대로 재사용) 벽 기준 정규화 좌표(U: 가로 0~1, V: 그 층 안에서 0~1)로 뽑는다.
창·층 자동 인식 알고리즘은 facade_paint.py 와 완전히 같다(새로 안 만든다) - 이 도구는 그 결과를
한 번에 여러 벽에 돌리고, cs2kit.py 의 wall_id/normal_deg 체계로 옮겨 적는 역할만 한다.

    python tools/facade_read.py --refs photo_refs.json [--slices previews/glb/slices.json]
                                 [--wall-size WxH] [--ppm 30] [--fh 2.9]
                                 [--window-mode auto] [--out previews/facade_read/]

--slices 를 주면 glb_slices.json 의 wall_N(normal_deg) 과 photo_refs 항목의 "normal_deg"(또는
"azimuth_deg") 를 각도로 매칭해 결과에 glb_wall_id 를 같이 적는다(없으면 생략, 에러 아님).
photo_refs 항목에 normal_deg/azimuth_deg 가 없으면 매칭 없이 그냥 넘어간다 - naver_vr.py 의
make_refs 가 만든 walls 목록에 azimuth_deg 가 있으니, 그 값을 손으로 옮겨 적어도 된다.

출력 previews/facade_read/<name>.json:
  {"name": "front", "wall_m": {"w":.., "h":..}, "normal_deg": .., "glb_wall_id": "wall_2",
   "columns": [{"u": [0.12, 0.18], "type": "window"}],
   "rows": [{"v": [0.0, 1.0], "floor": 1, "z_range": [0.0, 2.9]}]}
(이미 알려진 한계: 벽 하나 = photo_refs 항목 하나로 가정한다. 사진 여러 장을 이어붙인 한 벽은 아직
다루지 않는다 - 그런 경우는 facade_paint.py 를 손으로, 벽을 나눠 돌려야 한다.)
"""
import argparse
import json
import math
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facade_paint as FP  # noqa: E402  (load_wall/find_floors/band_stack/window_mask/build_windows/list_windows 재사용)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_one(refs_path, entry_name, wall_size, ppm, fh_hint, window_mode):
    a = SimpleNamespace(refs=refs_path, name=entry_name, wall_size=wall_size, ppm=ppm)
    wall = FP.load_wall(a)
    fl = FP.find_floors(wall, fh_hint)
    S = FP.band_stack(wall, fl)
    M, mode_info = FP.window_mask(S, wall, window_mode, quiet=True)
    T, iou, special = FP.build_windows(M)
    pitch_m = fl["pitch_m"]
    cols = []
    for w in FP.list_windows(T, wall, fl, None):
        u0 = (w["x0"] - wall["x0"]) / wall["w"]
        u1 = (w["x1"] - wall["x0"]) / wall["w"]
        v0 = w["band_bottom"] / pitch_m
        v1 = w["band_top"] / pitch_m
        cols.append({"u": [round(u0, 4), round(u1, 4)], "v": [round(max(0, v0), 4), round(min(1, v1), 4)],
                     "type": "window"})
    rows = []
    centres = sorted(fl["centres"], key=lambda t: t[0])   # bottom(low row idx? no: row grows downward) -> 위로
    for k, (c, found) in enumerate(centres):
        z_center = FP.row_z(wall, c)
        z0, z1 = z_center - pitch_m / 2, z_center + pitch_m / 2
        rows.append({"floor": k + 1, "v": [0.0, 1.0], "z_range": [round(z0, 2), round(z1, 2)], "found": bool(found)})
    return dict(name=wall["name"], wall_m=dict(w=wall["w"], h=wall["h"]), pitch_m=round(pitch_m, 3),
                window_mode=mode_info, columns=cols, rows=rows, special_floors=special)


def match_normal_deg(entry_deg, slices, tol=20.0):
    if entry_deg is None or not slices:
        return None
    best, best_d = None, 1e9
    for w in slices.get("walls", []):
        d = abs((entry_deg - w["normal_deg"] + 180) % 360 - 180)
        if d < best_d:
            best, best_d = w["id"], d
    return best if best_d <= tol else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refs", required=True)
    ap.add_argument("--slices", help="glb_slices.py 출력 (wall_id 매칭용, 선택)")
    ap.add_argument("--wall-size", help="항목에 size_m 이 없을 때 WxH (m)")
    ap.add_argument("--ppm", type=float, default=30.0)
    ap.add_argument("--fh", type=float, help="층고 힌트(m)")
    ap.add_argument("--window-mode", default="auto")
    ap.add_argument("--out", default="previews/facade_read")
    a = ap.parse_args()

    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    slices = json.load(open(a.slices, encoding="utf-8")) if a.slices else None
    os.makedirs(a.out, exist_ok=True)
    for e in refs.get("facades", []):
        name = e.get("name") or e.get("side")
        try:
            r = read_one(a.refs, name, a.wall_size, a.ppm, a.fh, a.window_mode)
        except SystemExit as ex:
            print("SKIP %s: %s" % (name, ex))
            continue
        deg = e.get("normal_deg", e.get("azimuth_deg"))
        r["normal_deg"] = deg
        glb_id = match_normal_deg(deg, slices)
        if glb_id:
            r["glb_wall_id"] = glb_id
        outp = os.path.join(a.out, "%s.json" % name)
        with open(outp, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        print("%-16s floors=%-3d windows=%-3d pitch=%.2fm mode=%s -> %s" %
              (name, len(r["rows"]), len(r["columns"]), r["pitch_m"], r["window_mode"].split(":")[0], outp))


if __name__ == "__main__":
    main()
