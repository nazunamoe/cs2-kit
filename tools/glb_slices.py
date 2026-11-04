# -*- coding: utf-8 -*-
"""
glb_slices.py - scan(.glb)에서 지정한 z(높이)마다 외곽 단면을 잘라 벽 세그먼트 목록을 뽑는다
(치수 참고용. glb_measure.py 처럼 스캔 지오메트리/텍스처는 에셋에 안 쓴다).

    python tools/glb_slices.py scan.glb --z 1.5,15.0,30.0 [--scale 1.0] [--up y]
                                [--mesh Building,Roof] [--box=-30,30,-20,20]
                                [--out previews/glb/slices.json]

각 z 레벨에서 메시를 그 평면으로 잘라 나온 변(edge)마다:
  id("wall_0","wall_1",...), start/end(x,y), length_m, normal_deg(0~360, 바깥쪽 법선 방위각).
normal_deg 규약(cs2kit.py 의 preset_*/attach_* 와 반드시 같다): 바깥 법선 (nx,ny) 에 대해
  normal_deg = atan2(nx, ny) % 360   (front=-Y 바깥=180, back=+Y 바깥=0, right=+X 바깥=90, left=-X 바깥=270)
여러 z 레벨을 주면, 각도(5도)+위치(겹침)가 비슷한 변을 같은 wall_id 로 묶어 건물 높이 전체의
벽 하나로 합친다(단차 구간은 자동으로 다른 wall_id 가 된다 - 의도된 동작).

출력 previews/glb/slices.json:
  {"levels": [1.5, 15.0], "walls": [{"id":"wall_0","start":[x,y],"end":[x,y],
   "length_m":12.3,"normal_deg":182.4,"z_range":[1.5,30.0]}]}

주의: 이 도구는 건물이 축 정렬(axis-aligned) 벽으로 이루어졌다고 가정하지 않는다 - 단면에서 나온
변은 어떤 각도든 나올 수 있다. cs2kit.py 의 axbox/paint 는 축 정렬 벽만 지원하므로, 비스듬한 변이
나오면 facade_read.py 쪽에서 가장 가까운 축 정렬 근사를 쓰거나 사람이 확인해야 한다.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_measure as GM  # noqa: E402  (load_gltf/accessor/node_matrix/collect/to_zup 재사용)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _filter_box(V, box):
    if not box:
        return np.ones(len(V), bool)
    x0, x1, y0, y1 = box
    return (V[:, 0] >= x0) & (V[:, 0] <= x1) & (V[:, 1] >= y0) & (V[:, 1] <= y1)


def slice_plane(V, F, z):
    """메시(V: Nx3 z-up, F: Mx3)를 z 평면으로 잘라 2D 선분 목록([(x0,y0,x1,y1), ...]) 반환."""
    segs = []
    v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    tri = np.stack([v0, v1, v2], axis=1)   # (M,3,3)
    for t in tri:
        pts = []
        for i in range(3):
            p, q = t[i], t[(i + 1) % 3]
            dz0, dz1 = p[2] - z, q[2] - z
            if dz0 == 0:
                pts.append((p[0], p[1]))
            if (dz0 > 0) != (dz1 > 0):
                k = dz0 / (dz0 - dz1)
                pts.append((p[0] + k * (q[0] - p[0]), p[1] + k * (q[1] - p[1])))
        if len(pts) >= 2:
            segs.append((pts[0][0], pts[0][1], pts[1][0], pts[1][1]))
    return segs


def chain_segments(segs, tol=0.03):
    """선분 목록 -> 이어붙인 폴리라인(링) 목록. 끝점이 tol 안에서 맞으면 연결한다."""
    pts = [((s[0], s[1]), (s[2], s[3])) for s in segs]
    used = [False] * len(pts)

    def close(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol

    rings = []
    for i in range(len(pts)):
        if used[i]:
            continue
        used[i] = True
        chain = [pts[i][0], pts[i][1]]
        extended = True
        while extended:
            extended = False
            for j in range(len(pts)):
                if used[j]:
                    continue
                a, b = pts[j]
                if close(chain[-1], a):
                    chain.append(b)
                elif close(chain[-1], b):
                    chain.append(a)
                elif close(chain[0], a):
                    chain.insert(0, b)
                elif close(chain[0], b):
                    chain.insert(0, a)
                else:
                    continue
                used[j] = True
                extended = True
                break
        rings.append(chain)
    return rings


def ring_to_walls(ring):
    """링(점 목록) -> 변마다 id 없이 (start,end,length_m,normal_deg) 목록. CCW 로 맞춘다."""
    pts = ring[:-1] if len(ring) > 2 and math.hypot(ring[0][0] - ring[-1][0], ring[0][1] - ring[-1][1]) < 0.05 else ring
    if len(pts) < 3:
        return []
    area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area2 < 0:
        pts = pts[::-1]
    out = []
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 0.1:
            continue
        dx, dy = x1 - x0, y1 - y0
        nx, ny = dy / length, -dx / length
        deg = math.degrees(math.atan2(nx, ny)) % 360
        out.append(dict(start=[round(x0, 3), round(y0, 3)], end=[round(x1, 3), round(y1, 3)],
                         length_m=round(length, 3), normal_deg=round(deg, 2)))
    return out


def merge_levels(per_level, ang_tol=5.0, pos_tol=1.0):
    """레벨마다 뽑은 벽 목록을 각도+위치로 합친다. 첫 레벨이 wall_id 를 정하고, 다음 레벨은
    가장 가까운 기존 벽에 합치거나(각도 ang_tol 안 + 벽선까지 수직거리 pos_tol 안) 새 벽으로 추가."""
    merged = []   # dict(start,end,length_m,normal_deg,z_levels=[...])

    def dist_to_wall(w, pt):
        x0, y0 = w["start"]
        x1, y1 = w["end"]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((pt[0] - x0) * dx + (pt[1] - y0) * dy) / L2))
        px, py = x0 + t * dx, y0 + t * dy
        return math.hypot(pt[0] - px, pt[1] - py)

    for z, walls in per_level:
        for w in walls:
            mid = ((w["start"][0] + w["end"][0]) / 2, (w["start"][1] + w["end"][1]) / 2)
            best, best_d = None, 1e9
            for m in merged:
                ad = abs((w["normal_deg"] - m["normal_deg"] + 180) % 360 - 180)
                if ad > ang_tol:
                    continue
                d = dist_to_wall(m, mid)
                if d < pos_tol and d < best_d:
                    best, best_d = m, d
            if best is None:
                w2 = dict(w)
                w2["z_levels"] = [z]
                merged.append(w2)
            else:
                best["z_levels"].append(z)
                if w["length_m"] > best["length_m"]:
                    best["start"], best["end"], best["length_m"] = w["start"], w["end"], w["length_m"]
    out = []
    for k, m in enumerate(merged):
        out.append(dict(id="wall_%d" % k, start=m["start"], end=m["end"], length_m=m["length_m"],
                         normal_deg=m["normal_deg"], z_range=[round(min(m["z_levels"]), 2), round(max(m["z_levels"]), 2)]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb")
    ap.add_argument("--z", required=True, help="자를 높이들(m), 쉼표 구분")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--up", choices=["y", "z"], default="y")
    ap.add_argument("--mesh", help="이름에 이 문자열(쉼표로 여러 개) 들어간 메시만")
    ap.add_argument("--box", help="x0,x1,y0,y1 (스케일 적용 후, 지형/주변 건물 제외)")
    ap.add_argument("--out", default="previews/glb/slices.json")
    a = ap.parse_args()
    levels = [float(x) for x in a.z.split(",")]
    box = tuple(float(x) for x in a.box.split(",")) if a.box else None
    needles = [s.strip().lower() for s in a.mesh.split(",")] if a.mesh else None

    js, bufs = GM.load_gltf(a.glb)
    meshes = GM.collect(js, bufs)
    if needles:
        meshes = [m for m in meshes if any(n in m["name"].lower() for n in needles)]
    if not meshes:
        raise SystemExit("no mesh matched (check --mesh against glb_measure.py --list)")

    per_level = []
    for z in levels:
        all_segs = []
        for m in meshes:
            V = GM.to_zup(m["V"], a.up) * a.scale
            keep = _filter_box(V, box)
            F = m["F"]
            if not keep.all():
                F = F[keep[F].all(axis=1)]
            if len(F) == 0:
                continue
            all_segs.extend(slice_plane(V, F, z))
        rings = chain_segments(all_segs)
        walls = []
        for ring in rings:
            walls.extend(ring_to_walls(ring))
        per_level.append((z, walls))
        print("z=%.2f: %d segment(s) -> %d ring(s) -> %d wall(s)" % (z, len(all_segs), len(rings), len(walls)))

    merged = merge_levels(per_level)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"levels": levels, "walls": merged}, f, ensure_ascii=False, indent=1)
    print("%d wall(s) total -> %s" % (len(merged), a.out))
    for w in merged:
        print("  %-8s len=%6.2fm normal=%6.1fdeg z=%s" % (w["id"], w["length_m"], w["normal_deg"], w["z_range"]))


if __name__ == "__main__":
    main()
