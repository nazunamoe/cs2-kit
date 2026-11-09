# -*- coding: utf-8 -*-
"""
facade_read.py - photo_refs.json 의 모든 facade 항목을 한 번에 돌려(facade_paint.py 의 floor/window
찾기를 그대로 재사용) 벽 기준 정규화 좌표(U: 가로 0~1, V: 그 층 안에서 0~1)로 뽑는다.
창·층 자동 인식 알고리즘은 facade_paint.py 와 완전히 같다(새로 안 만든다) - 이 도구는 그 결과를
한 번에 여러 벽에 돌리고, cs2kit.py 의 wall_id/normal_deg 체계로 옮겨 적는 역할만 한다.

    python tools/facade_read.py --refs photo_refs.json [--slices previews/glb/slices.json]
                                 [--wall-size WxH] [--ppm 30] [--fh 2.9]
                                 [--window-mode auto] [--plane-map work/plane_to_edge.json]
                                 [--table] [--out previews/facade_read/]

--plane-map 을 주면 tools/photo_plane_map.py 가 만든 등록 결과를 써서, 각 열을 **모델 벽의
미터 좌표**로 옮겨 적는다(사진이 반전되어 있으면 순서도 뒤집힌다). --table 은 생성기에 바로
붙여 넣을 수 있는 columns 표를 함께 쓴다:
    COLUMNS = {"main:edge_11": [("wide", 1.10, 4.00), ("small", 5.75, 7.00), ...]}
kind 는 힌트다(wide | small | louver?). 루버와 좁은 창은 사진에서 구분되지 않을 수 있으므로
반드시 눈으로 확인한다.

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

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facade_paint as FP  # noqa: E402  (load_wall/find_floors/band_stack/window_mask/build_windows/list_windows 재사용)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_one(refs_path, entry_name, wall_size, ppm, fh_hint, window_mode, plane_map=None):
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
        col = {"u": [round(u0, 4), round(u1, 4)], "v": [round(max(0, v0), 4), round(min(1, v1), 4)],
               "type": "window",
               "m": [round(w["x0"], 2), round(w["x1"], 2)],
               "w": w["w"], "h": w["h"],
               "z": [round(w["band_bottom"], 2), round(w["band_top"], 2)]}
        col["hint"] = classify(w, wall)
        cols.append(col)
    louvers = louver_candidates(wall, fl, cols)
    rows = []
    centres = sorted(fl["centres"], key=lambda t: t[0])   # bottom(low row idx? no: row grows downward) -> 위로
    for k, (c, found) in enumerate(centres):
        z_center = FP.row_z(wall, c)
        z0, z1 = z_center - pitch_m / 2, z_center + pitch_m / 2
        rows.append({"floor": k + 1, "v": [0.0, 1.0], "z_range": [round(z0, 2), round(z1, 2)], "found": bool(found)})
    out = dict(name=wall["name"], wall_m=dict(w=wall["w"], h=wall["h"]), pitch_m=round(pitch_m, 3),
               window_mode=mode_info, columns=cols, louver_candidates=louvers,
               rows=rows, special_floors=special)
    if plane_map:
        out["model"] = to_model(cols, louvers, wall, plane_map, wall["entry"])
        ppm_capture = out["model"].get("px_per_m_capture")
        if ppm_capture:
            if ppm_capture < 20:
                out["warnings"] = ["capture resolution %.0f px/m: window widths are not measurable" % ppm_capture]
            elif ppm_capture < 30:
                out["warnings"] = ["capture resolution %.0f px/m: louver slats are not separable from blinds"
                                   % ppm_capture]
    return out


def louver_candidates(wall, fl, cols, min_lines=5):
    """Find louver bands that the window detector missed.

    A louver panel is not a dark hole, so the window mask ignores it. What it has is a
    regular row-to-row pattern (the slats): inside a slatted strip the number of strong
    horizontal lines per floor is high and repeats on every floor, while a plain wall is
    flat and a window is dark (and is already detected as a window).

    So we slide a narrow strip over the wall, count the strong horizontal lines per floor
    inside it, and keep the strips that are clearly slatted and are not inside a detected
    window column.

    The result is a candidate list, not a decision: check it against the photo.
    """
    arr = wall["arr"].mean(2)
    ppm = wall["ppm"]
    H, W = arr.shape
    if H < 10 or W < 10:
        return []
    g = np.abs(np.diff(arr, axis=0))                 # row-to-row energy, (H-1, W)
    pitch_px = fl.get("pitch_px") or 0
    if not pitch_px:
        return []
    win = max(3, int(round(0.45 * ppm)))
    step = max(1, int(round(0.08 * ppm)))
    # prefix sum over x: every strip's per-row energy is then two lookups, so the whole
    # profile for all strips costs O(H * W) instead of O(strips * win * floors * rows)
    csx = np.cumsum(g, axis=1, dtype=np.float64)
    csx = np.hstack([np.zeros((csx.shape[0], 1), dtype=np.float64), csx])  # (H, W+1)
    centres = np.array([c for c, _ in fl["centres"]], dtype=float)
    r0 = np.clip((centres - pitch_px / 2).astype(int), 0, g.shape[0])
    r1 = np.clip((centres + pitch_px / 2).astype(int), 1, g.shape[0])
    valid = (r1 - r0) >= 5
    if valid.sum() < 4:
        return []
    # per-row mean energy for a strip = (row_sum(x1) - row_sum(x0)) / win, for every row
    # vectorized over rows: (H, W+1) prefix sums give it directly
    r0v, r1v = r0[valid], r1[valid]
    nfl = len(r0v)

    def strip_counts(x0, x1):
        x1c = min(x1, W)
        row_e = (csx[:, x1c] - csx[:, x0]) / max(x1c - x0, 1) if x1c > x0 else np.zeros(csx.shape[0])
        counts = np.empty(nfl, dtype=np.int64)
        for i in range(nfl):
            a0, a1 = r0v[i], r1v[i]
            e = row_e[a0:a1]
            thr = max(6.0, 2.0 * float(np.median(e)))
            counts[i] = int((e > thr).sum())
        return counts

    strips = []
    for x0 in range(0, max(1, W - win + 1), step):
        x1 = min(W, x0 + win)
        counts = strip_counts(x0, x1)
        strips.append((x0, x1, float(np.median(counts)), float(np.percentile(counts, 75)), nfl))

    hot = [s for s in strips if s[2] >= min_lines]
    if not hot:
        return []
    # cluster consecutive hot strips; a gap of one cold strip starts a new band
    clusters = []
    prev_hot = False
    for s in strips:
        if s[2] >= min_lines:
            if prev_hot and clusters:
                c = clusters[-1]
                clusters[-1] = (c[0], s[1], max(c[2], s[2]), s[4])
            else:
                clusters.append((s[0], s[1], s[2], s[4]))
            prev_hot = True
        else:
            prev_hot = False
    out = []
    for x0, x1, v, n in clusters:
        m0 = wall["x0"] + x0 / ppm
        m1 = wall["x0"] + x1 / ppm
        u0 = (m0 - wall["x0"]) / wall["w"]
        u1 = (m1 - wall["x0"]) / wall["w"]
        if u1 - u0 < 0.02:
            continue
        # a strip that sits inside a detected window is that window, not a louver
        if any(not (u1 <= c["u"][0] or u0 >= c["u"][1]) for c in cols):
            continue
        out.append({"u": [round(u0, 4), round(u1, 4)], "m": [round(m0, 2), round(m1, 2)],
                    "w": round(m1 - m0, 2), "lines_per_floor": round(v, 1),
                    "floors": n, "type": "louver?", "hint": "louver?"})
    return out


def classify(w, wall):
    """Guess the column kind from its measured width. Louver is never decided here.

    A louver panel and a narrow window look the same in a low-resolution photo, so the kind
    is only a hint: 'wide' (balcony window) or 'small' (narrow window). Louver candidates
    come from louver_candidates(), which looks for slats instead of darkness.
    """
    return "wide" if w["w"] >= 1.8 else "small"


def to_model(cols, louvers, wall, plane_map, entry):
    """Column positions on the model wall that this photo plane covers.

    photo_plane_map.json gives the metre offset of the photo's left edge on the model wall
    and whether the photo is mirrored; the columns are moved there and flipped if needed.
    """
    plane = entry.get("source_plane_i")
    info = plane_map.get("planes", [])
    hit = next((q for q in info if q["plane"] == plane), None)
    if hit is None:
        return {"mapped": False, "reason": "no plane %s in the plane map" % plane}
    left, right = hit["photo_left_m"], hit["photo_right_m"]

    def to_edge(x_m):
        u = (x_m - wall["x0"]) / max(wall["w"], 1e-6)
        return left + (right - left) * u

    def moved(items):
        out = []
        for c in items:
            a, b = to_edge(c["m"][0]), to_edge(c["m"][1])
            if a > b:
                a, b = b, a
            c2 = dict(c)
            c2["edge_m"] = [round(a, 2), round(b, 2)]
            out.append(c2)
        return out
    return {"mapped": True, "edge": hit["edge"], "wall_id": "main:edge_%02d" % hit["edge"],
            "mirrored": hit["mirrored"], "edge_length_m": hit["edge_length_m"],
            "photo_left_m": left, "photo_right_m": right,
            "columns": moved(cols), "louver_candidates": moved(louvers),
            "px_per_m_capture": hit.get("px_per_m_capture")}


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
    ap.add_argument("--plane-map", help="photo_plane_map.py 결과 json -> 열을 모델 벽 미터로 옮겨 적는다")
    ap.add_argument("--table", action="store_true", help="생성기용 columns 표도 같이 쓴다")
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 한 덩어리로 출력(개별 <name>.json 도 그대로 쓴다)")
    ap.add_argument("--out", default="previews/facade_read")
    a = ap.parse_args()

    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    slices = json.load(open(a.slices, encoding="utf-8")) if a.slices else None
    plane_map = json.load(open(a.plane_map, encoding="utf-8")) if a.plane_map else None
    os.makedirs(a.out, exist_ok=True)
    tables = {}
    summary = []
    for e in refs.get("facades", []):
        name = e.get("name") or e.get("side")
        try:
            r = read_one(a.refs, name, a.wall_size, a.ppm, a.fh, a.window_mode, plane_map)
        except SystemExit as ex:
            if not a.json:
                print("SKIP %s: %s" % (name, ex))
            summary.append({"name": name, "error": str(ex)})
            continue
        deg = e.get("normal_deg", e.get("azimuth_deg"))
        r["normal_deg"] = deg
        glb_id = match_normal_deg(deg, slices)
        if glb_id:
            r["glb_wall_id"] = glb_id
        outp = os.path.join(a.out, "%s.json" % name)
        with open(outp, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        summary.append({"name": name, "file": outp, "floors": len(r["rows"]),
                        "windows": len(r["columns"]), "pitch_m": r["pitch_m"],
                        "window_mode": r["window_mode"], "normal_deg": deg,
                        "glb_wall_id": glb_id, "warnings": r.get("warnings", [])})
        cols = r["columns"]
        mapped = r.get("model", {})
        shown = mapped["columns"] if mapped.get("mapped") else cols
        if not a.json:
            print("%-16s floors=%-3d windows=%-3d pitch=%.2fm mode=%s -> %s"
                  % (name, len(r["rows"]), len(cols), r["pitch_m"], r["window_mode"].split(":")[0], outp))
        for c in shown:
            where = ""
            if mapped.get("mapped"):
                where = "  edge_m %5.2f..%5.2f" % (c["edge_m"][0], c["edge_m"][1])
            if not a.json:
                print("      u %5.3f..%5.3f  w %4.2f m  h %4.2f m  %-8s%s"
                      % (c["u"][0], c["u"][1], c["w"], c["h"], c["hint"], where))
        for c in mapped.get("louver_candidates", []) if mapped.get("mapped") else r["louver_candidates"]:
            where = ""
            if mapped.get("mapped"):
                where = "  edge_m %5.2f..%5.2f" % (c["edge_m"][0], c["edge_m"][1])
            if not a.json:
                print("      u %5.3f..%5.3f  w %4.2f m  %-8s%s  (%.0f lines/floor over %d floors)"
                      % (c["u"][0], c["u"][1], c["w"], c["hint"], where, c["lines_per_floor"], c["floors"]))
        if mapped.get("mapped"):
            wid = mapped["wall_id"]
            table = tables.setdefault(wid, {"edge": mapped["edge"], "mirrored": mapped["mirrored"],
                                            "columns": [], "plane": name})
            for c in mapped["columns"]:
                table["columns"].append((c["hint"], c["edge_m"][0], c["edge_m"][1]))
            for c in mapped.get("louver_candidates", []):
                table["columns"].append((c["hint"], c["edge_m"][0], c["edge_m"][1]))
        if not a.json:
            for w in r.get("warnings", []):
                print("      WARN %s" % w)
    if a.table and tables:
        tp = os.path.join(a.out, "columns_table.py")
        with open(tp, "w", encoding="utf-8") as f:
            f.write("# generated by tools/facade_read.py - measured window columns per model wall\n")
            f.write("# kinds are hints: 'wide' | 'small' | 'louver?' - check them against the photo\n")
            f.write("COLUMNS = {\n")
            for wid, t in tables.items():
                f.write("    %r: [  # %s, mirrored=%s\n" % (wid, t["plane"], t["mirrored"]))
                for kind, a0, a1 in t["columns"]:
                    f.write("        (%r, %.2f, %.2f),\n" % (kind, a0, a1))
                f.write("    ],\n")
            f.write("}\n")
        if not a.json:
            print("\nwrote %s" % tp)
            for wid, t in tables.items():
                print("  %-16s %d column(s)" % (wid, len(t["columns"])))
    combined = os.path.join(a.out, "facade_read.json")
    with open(combined, "w", encoding="utf-8") as f:
        json.dump({"status": "OK", "refs": a.refs, "planes": plane_map is not None,
                   "walls": summary}, f, ensure_ascii=False, indent=1)
    if a.json:
        print(json.dumps({"status": "OK", "out": a.out, "combined": combined,
                          "walls": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
