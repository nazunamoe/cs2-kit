# -*- coding: utf-8 -*-
"""scan_tool.py - glb/gltf 건물 스캔을 뜯어보는 재사용 도구.

명령:
  list     glb 안의 건물 메시 목록 (이름, tris, bbox, 높이)
  info     메시 하나의 크기·area·높이 분포
  roof     옥상 분석: 위를 향한 면 -> 높이 레벨 -> 연결 comps(데크/파라펫 띠/옥탑 상자)
           roof_levels.json, roof_top.png, roof_heightfield.png
  slice    높이별 단면 폴리곤 (좌표 목록 + 그림)
  elev     x-z / y-z 실루엣 입면
  top      평면(위에서 본) 실루엣
  compare  스캔 vs 모델 OBJ 자동 정렬 겹침 (뒤집힘·이동 자동 판별)
  report   위 분석을 한 번에 돌리고 report.md 작성

공통 옵션:
  --up y|z            높이 축 (기본 y: glTF 규격)
  --axes x,-z         평면 두 축 (앞에 - 를 붙이면 뒤집기). 기본 x,-z
  --shift dx,dy,dz    축 변환 뒤 이동
  --ground auto|값     높이 기준 (auto = 최저점 0)
  --mesh 이름|번호     메시 선택 (list 로 확인)

예:
  python tools_scan/scan_tool.py list photos/3dview.glb
  python tools_scan/scan_tool.py report photos/3dview.glb --mesh 887188 -o work/scan
  python tools_scan/scan_tool.py compare photos/3dview.glb --mesh 887188 \
         --model output/X/_check/X.obj -o work/scan
"""
import argparse
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanlib as S  # noqa: E402


# ------------------------------------------------------------------ helpers
def _map_args(a):
    up = a.up
    axes = tuple(x.strip() for x in a.axes.split(","))
    shift = tuple(float(x) for x in a.shift.split(",")) if a.shift else (0.0, 0.0, 0.0)
    ground = "auto" if a.ground == "auto" else float(a.ground)
    return up, axes, shift, ground


def _open(a):
    up, axes, shift, ground = _map_args(a)
    if a.mesh is None:
        raise SystemExit("--mesh required (see list)")
    return S.load_mesh(a.glb, a.mesh, up=up, axes=axes, shift=shift, ground=ground)


def _out(a, name):
    d = a.out or os.path.join(os.path.dirname(os.path.abspath(a.glb)), "scan_out")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _bbox(V):
    return (V[:, 0].min(), V[:, 0].max(), V[:, 1].min(), V[:, 1].max(),
            V[:, 2].min(), V[:, 2].max())


# ------------------------------------------------------------------ list
def cmd_list(a):
    g = S.read_gltf(a.glb)
    up, axes, shift, ground = _map_args(a)
    pm = S.PlanMap(up=up, axes=axes, shift=shift, ground=None)
    print("%-6s %-22s %7s  %-26s %s" % ("idx", "name", "tris", "size x*y*z (m)", "height range"))
    for i, (name, mi, M) in enumerate(g.entries()):
        try:
            V, F, _ = g.mesh_triangles(name)
        except Exception as e:
            print("  %-4d %-22s  read failed: %s" % (i, name, e))
            continue
        V = pm.apply(V)
        b = _bbox(V)
        dx, dy, dz = b[1] - b[0], b[3] - b[2], b[5] - b[4]
        print("%-6d %-22s %7d  %8.1f x %6.1f x %5.1f  %.1f..%.1f"
              % (i, name, len(F), dx, dy, dz, b[4], b[5]))


# ------------------------------------------------------------------ info
def cmd_info(a):
    m = _open(a)
    V, F = m["V"], m["F"]
    b = _bbox(V)
    tri = V[F]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]),
                          axis=1).sum() / 2
    print("mesh %s  verts %d  tris %d" % (m["name"], len(V), len(F)))
    print("bbox  x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f" % b)
    print("size  %.2f x %.2f x %.2f m   surface %.0f m2" %
          (b[1] - b[0], b[3] - b[2], b[5] - b[4], area))
    print("map   %s" % m["map"].describe())
    levels, flipped = S.up_components(V, F)
    if flipped:
        print("WARN  up-face winding is inverted (judged by |nz|).")
    print("roof levels (up faces): %d" % len(levels))
    for g in levels[:12]:
        print("  z %7.2f  area %8.1f m2  comps %2d" % (g["z"], g["area"], g["ncomp"]))
    if len(F) < 3000:
        print("WARN  tris %d < 3000: map LOD scan. Small roof structures may be lost;"
              " compare with a roofview photo." % len(F))


# ------------------------------------------------------------------ roof
def cmd_roof(a):
    m = _open(a)
    V, F = m["V"], m["F"]
    levels, flipped = S.up_components(V, F, level_tol=a.level)
    out_png = _out(a, "roof_top.png")
    fig, ax = plt.subplots(figsize=(14, 10))
    cmap = plt.get_cmap("viridis")
    zmin = min(g["z"] for g in levels)
    zmax = max(g["z"] for g in levels)
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nn = np.linalg.norm(n, axis=1)
    nz = np.where(nn > 1e-9, n[:, 2] / np.maximum(nn, 1e-9), 0)
    up = (nz > 0.7) if not flipped else (nz < -0.7)
    for t, h in zip(tri[up], tri[up][:, :, 2].mean(axis=1)):
        col = cmap(0.15 + 0.8 * (h - zmin) / max(zmax - zmin, 1e-6))
        ax.fill(t[:, 0], t[:, 1], color=col, lw=0.2, edgecolor="#22222222")

    rows = []
    top = levels[0]["z"] if levels else 0
    for g in levels:
        rows.append({"z": round(g["z"], 2), "area": round(g["area"], 1),
                     "components": []})
        for c in g["comp"]:
            b = c["bbox"]
            kind = ("band" if (min(c["rect_w"], c["rect_h"]) <= 1.8 and
                               max(c["rect_w"], c["rect_h"]) /
                               max(min(c["rect_w"], c["rect_h"]), 1e-3) >= 3.0)
                    else ("box" if c["area"] >= 3 else "small"))
            rows[-1]["components"].append({
                "area": round(c["area"], 1),
                "bbox": [round(v, 2) for v in b],
                "rect": [round(c["rect_w"], 2), round(c["rect_h"], 2)],
                "angle": round(c["rect_angle"], 1),
                "centroid": [round(v, 2) for v in c["centroid"]],
                "kind": kind})
            if c["area"] >= 6:
                cx, cy = c["centroid"]
                ax.annotate("z%.1f\nA%.1f\n%.1fx%.1f@%.0f" %
                            (g["z"], c["area"], c["rect_w"], c["rect_h"],
                             c["rect_angle"]),
                            (cx, cy), fontsize=6, ha="center", va="center",
                            color="#111", bbox=dict(boxstyle="round,pad=0.15",
                                                    fc="white", ec="#888", alpha=0.75))
    ax.set_aspect("equal")
    ax.grid(True, lw=0.3, alpha=0.4)
    ax.set_title("roof: up-facing faces by height"
                 + ("  (winding flipped)" if flipped else ""))
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)

    # 높이장 (0.25 m 칸)
    res = a.cell
    b = _bbox(V)
    W = int((b[1] - b[0]) / res) + 2
    H = int((b[3] - b[2]) / res) + 2
    hf = np.full((H, W), np.nan)
    for t in tri[up]:
        xs = (t[:, 0] - b[0]) / res
        ys = (t[:, 1] - b[2]) / res
        h = t[:, 2].mean()
        px0, px1 = int(np.floor(xs.min())), int(np.ceil(xs.max()))
        py0, py1 = int(np.floor(ys.min())), int(np.ceil(ys.max()))
        px0, py0 = max(px0, 0), max(py0, 0)
        px1, py1 = min(px1, W - 1), min(py1, H - 1)
        if px1 < px0 or py1 < py0:
            continue
        yy, xx = np.mgrid[py0:py1 + 1, px0:px1 + 1]
        d = ((ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2]))
        if abs(d) < 1e-9:
            continue
        l1 = ((ys[1] - ys[2]) * (xx - xs[2]) + (xs[2] - xs[1]) * (yy - ys[2])) / d
        l2 = ((ys[2] - ys[0]) * (xx - xs[2]) + (xs[0] - xs[2]) * (yy - ys[2])) / d
        l3 = 1 - l1 - l2
        msk = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        cur = hf[yy[msk], xx[msk]]
        hf[yy[msk], xx[msk]] = np.where(np.isnan(cur), h, np.maximum(cur, h))
    fig, ax = plt.subplots(figsize=(14, 10))
    im = ax.imshow(np.flipud(hf), cmap="terrain", extent=[b[0], b[1], b[2], b[3]])
    plt.colorbar(im, ax=ax, label="z (m)")
    ax.set_title("roof heightfield (%.2f m cells)" % res)
    fig.tight_layout()
    fig.savefig(_out(a, "roof_heightfield.png"), dpi=110)
    plt.close(fig)

    data = {"mesh": m["name"], "tris": int(len(F)), "map": m["map"].describe(),
            "winding_flipped": bool(flipped),
            "levels": rows}
    with open(_out(a, "roof_levels.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print("roof levels %d (top->bottom).  saved: %s" % (len(levels), out_png))
    for g in levels:
        print("\n[z %.2f]  area %.1f m2  comps %d" % (g["z"], g["area"], g["ncomp"]))
        for k, c in enumerate(g["comp"]):
            mn = min(c["rect_w"], c["rect_h"])
            mx = max(c["rect_w"], c["rect_h"])
            kind = ("band" if (mn <= 1.8 and mx / max(mn, 1e-3) >= 3.0)
                    else ("box" if c["area"] >= 3 else "small"))
            tag = "DECK" if (k == 0 and c["area"] >= 20) else kind
            print("   %-5s A%7.1f  rect %5.1f x %5.1f @%6.1f  bbox x %6.1f..%6.1f y %5.1f..%5.1f"
                  % (tag, c["area"], c["rect_w"], c["rect_h"], c["rect_angle"],
                     c["bbox"][0], c["bbox"][2], c["bbox"][1], c["bbox"][3]))
    if len(F) < 3000:
        print("\nWARN  LOD scan (tris %d). Re-check roof boxes/rails/louvers with photos." % len(F))
    if levels:
        print("\nHighest level z %.2f (penthouse / machine room top candidate)." % levels[0]["z"])


# ------------------------------------------------------------------ slice
def cmd_slice(a):
    m = _open(a)
    V, F = m["V"], m["F"]
    b = _bbox(V)
    if a.z:
        zs = [float(x) for x in a.z.split(",")]
    else:
        step = a.auto or 5.0
        zs = list(np.arange(b[4] + 1e-6, b[5], step))
    n = len(zs)
    cols = min(4, n)
    rows = int(np.ceil(n / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(5 * cols, 4.6 * rows), squeeze=False)
    txt = []
    for k, z in enumerate(zs):
        ax = axs[k // cols][k % cols]
        polys = S.slice_polygons(V, F, z)
        txt.append("=== z %.2f  polygons %d" % (z, len(polys)))
        for p, area in polys:
            ax.plot(np.r_[p[:, 0], p[0, 0]], np.r_[p[:, 1], p[0, 1]], "-", lw=0.8)
            txt.append("-- area %.1f" % area)
            for x, y in p:
                txt.append("   %8.3f %8.3f" % (x, y))
        ax.set_title("z=%.2f  polys=%d" % (z, len(polys)), fontsize=9)
        ax.set_aspect("equal")
        ax.grid(True, lw=0.25, alpha=0.4)
        ax.set_xlim(b[0] - 1, b[1] + 1)
        ax.set_ylim(b[2] - 1, b[3] + 1)
    for k in range(n, rows * cols):
        axs[k // cols][k % cols].axis("off")
    fig.tight_layout()
    fig.savefig(_out(a, "slices.png"), dpi=100)
    plt.close(fig)
    with open(_out(a, "slices.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(txt))
    print("slices %d -> %s / slices.txt" % (n, _out(a, "slices.png")))


# ------------------------------------------------------------------ elev / top
def _draw_elev(V, F, a):
    tri = V[F]
    fig, axs = plt.subplots(1, 2, figsize=(22, 11))
    for ax, (u, v, name) in zip(axs, [(0, 2, "x-z (front/back)"),
                                      (1, 2, "y-z (side)")]):
        for t in tri:
            ax.fill(t[:, u], t[:, v], color="#888", lw=0)
        ax.set_title(name)
        ax.set_aspect("equal")
        ax.grid(True, lw=0.35, alpha=0.5)
        b = _bbox(V)
        ax.set_xlim(b[0] - 1, b[1] + 1) if u == 0 else ax.set_xlim(b[2] - 1, b[3] + 1)
        ax.set_ylim(min(0, b[4]) - 1, b[5] + 1)
    fig.tight_layout()
    p = _out(a, "elev.png")
    fig.savefig(p, dpi=100)
    plt.close(fig)
    return p


def cmd_elev(a):
    m = _open(a)
    print("elevation saved:", _draw_elev(m["V"], m["F"], a))


def cmd_top(a):
    m = _open(a)
    V, F = m["V"], m["F"]
    tri = V[F]
    b = _bbox(V)
    fig, ax = plt.subplots(figsize=(14, 10))
    for t in tri:
        ax.fill(t[:, 0], t[:, 1], color="#999", lw=0)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.35, alpha=0.45)
    ax.set_xlim(b[0] - 1, b[1] + 1)
    ax.set_ylim(b[2] - 1, b[3] + 1)
    ax.set_title("top view (all triangles projected)")
    fig.tight_layout()
    p = _out(a, "top.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print("top view saved:", p)


# ------------------------------------------------------------------ compare
def _align_and_score(scanV, scanF, modV, modF, size=448):
    """model 을 scan 평면에 맞춰 4가지 뒤집힘을 시도하고 IoU 가 가장 좋은 것을 고른다.
    돌려주는 값: (iou, fx, fy, 정렬된 model 정점 배열)"""
    st = scanV[scanF]
    bs = _bbox(scanV)
    best = None
    for fx in (1, -1):
        for fy in (1, -1):
            A = modV.copy()
            A[:, 0] *= fx
            A[:, 1] *= fy
            bm = _bbox(A)
            dx = (bs[0] + bs[1]) / 2 - (bm[0] + bm[1]) / 2
            dy = (bs[2] + bs[3]) / 2 - (bm[2] + bm[3]) / 2
            dz = bs[4] - bm[4]
            A2 = A + np.array([dx, dy, dz])
            bbox = (min(bs[0], bm[0] + dx), min(bs[2], bm[2] + dy),
                    max(bs[1], bm[1] + dx), max(bs[3], bm[3] + dy))
            mt = A2[modF]

            def _iou(a, b, idx):
                m1, _ = S.raster_triangles(a[:, :, idx], size=size, bbox=bbox)
                m2, _ = S.raster_triangles(b[:, :, idx], size=size, bbox=bbox)
                return (m1 & m2).sum() / max((m1 | m2).sum(), 1)
            iou = 0.5 * (_iou(st, mt, [0, 2]) + _iou(st, mt, [0, 1]))
            if best is None or iou > best[0]:
                best = (iou, fx, fy, A2)
    return best


def cmd_compare(a):
    m = _open(a)
    mv, mf = S.read_obj(a.model)
    V, F = m["V"], m["F"]
    iou, fx, fy, T = _align_and_score(V, F, mv, mf)
    print("auto align: x*%d, y*%d  plan IoU %.3f" % (fx, fy, iou))
    bs = _bbox(V)

    fig, axs = plt.subplots(1, 3, figsize=(30, 10))
    tri_s = V[F]
    tri_m = T[mf]
    # x-z
    ax = axs[0]
    for t in tri_s:
        ax.fill(t[:, 0], t[:, 2], color="#c8c8c8", lw=0)
    for t in tri_m:
        ax.fill(t[:, 0], t[:, 2], color="#e06a5a", lw=0, alpha=0.45)
    ax.set_title("x-z  scan(grey) vs model(red)")
    ax.set_aspect("equal")
    ax.set_xlim(bs[0] - 1, bs[1] + 1)
    ax.set_ylim(0, bs[5] + 1)
    ax.grid(True, lw=0.3, alpha=0.4)
    # y-z
    ax = axs[1]
    for t in tri_s:
        ax.fill(t[:, 1], t[:, 2], color="#c8c8c8", lw=0)
    for t in tri_m:
        ax.fill(t[:, 1], t[:, 2], color="#e06a5a", lw=0, alpha=0.45)
    ax.set_title("y-z  scan vs model")
    ax.set_aspect("equal")
    ax.set_xlim(bs[2] - 1, bs[3] + 1)
    ax.set_ylim(0, bs[5] + 1)
    ax.grid(True, lw=0.3, alpha=0.4)
    # top
    ax = axs[2]
    for t in tri_s:
        ax.fill(t[:, 0], t[:, 1], color="#d5d5d5", lw=0)
    for t in tri_m:
        ax.fill(t[:, 0], t[:, 1], color="#e06a5a", lw=0, alpha=0.35)
    ax.set_title("top  scan vs model")
    ax.set_aspect("equal")
    ax.set_xlim(bs[0] - 1, bs[1] + 1)
    ax.set_ylim(bs[2] - 1, bs[3] + 1)
    ax.grid(True, lw=0.3, alpha=0.4)
    fig.tight_layout()
    p = _out(a, "compare.png")
    fig.savefig(p, dpi=100)
    plt.close(fig)
    print("compare image:", p)
    # 옥상 레벨 비교 (스캔 vs 모델) - 옥상 조형이 맞는지 바로 확인
    sl, _ = S.up_components(V, F, level_tol=a.level)
    ml, _ = S.up_components(T, mf, level_tol=a.level)
    print("")
    print("roof levels: scan %d / model %d" % (len(sl), len(ml)))
    print("  scan z   model z   d      scan A   model A")
    used = set()
    diffs = []
    for g in sl:
        best = None
        for k, h in enumerate(ml):
            d = abs(g["z"] - h["z"])
            if best is None or d < best[1]:
                best = (k, d)
        k, d = best
        if d <= 1.0:
            used.add(k)
            diffs.append({"scan_z": round(g["z"], 2), "model_z": round(ml[k]["z"], 2),
                          "d": round(ml[k]["z"] - g["z"], 2),
                          "scan_area": round(g["area"], 1),
                          "model_area": round(ml[k]["area"], 1)})
            print("  %6.2f   %6.2f   %+6.2f  %7.1f  %7.1f"
                  % (g["z"], ml[k]["z"], ml[k]["z"] - g["z"], g["area"], ml[k]["area"]))
    for k, h in enumerate(ml):
        if k not in used and h["area"] >= 3:
            print("  ------   %6.2f   (only model)  %7s  %7.1f" % (h["z"], "-", h["area"]))
    if diffs:
        import json as _json
        with open(_out(a, "compare_levels.json"), "w", encoding="utf-8") as f:
            _json.dump(diffs, f, ensure_ascii=False, indent=1)
    print("size  scan %.2f x %.2f x %.2f / model %.2f x %.2f x %.2f" % (
        bs[1] - bs[0], bs[3] - bs[2], bs[5] - bs[4],
        mv[:, 0].max() - mv[:, 0].min(), mv[:, 1].max() - mv[:, 1].min(),
        mv[:, 2].max() - mv[:, 2].min()))


# ------------------------------------------------------------------ report
def cmd_report(a):
    m = _open(a)
    V, F = m["V"], m["F"]
    b = _bbox(V)
    levels, flipped = S.up_components(V, F, level_tol=a.level)
    cmd_roof(a)
    cmd_elev(a)
    cmd_top(a)
    cmd_slice(a)
    lines = ["# Scan analysis - %s" % m["name"], "",
             "- tris %d, bbox %.2f x %.2f x %.2f m" %
             (len(F), b[1] - b[0], b[3] - b[2], b[5] - b[4]),
             "- map: %s" % m["map"].describe(),
             "- winding inverted: %s" % ("yes (WARN)" if flipped else "no"), ""]
    if len(F) < 3000:
        lines.append("> tris < 3000: map LOD scan. Cross-check roof boxes/rails/louvers with a **roofview photo**.")
        lines.append("")
    lines.append("## Roof levels (top -> bottom)")
    lines.append("| z (m) | area (m2) | comps | largest (rect) |")
    lines.append("|---|---|---|---|")
    for g in levels:
        big = g["comp"][0] if g["comp"] else None
        rr = "%.1f x %.1f @ %.0f°" % (big["rect_w"], big["rect_h"], big["rect_angle"]) if big else "-"
        lines.append("| %.2f | %.1f | %d | %s |" % (g["z"], g["area"], g["ncomp"], rr))
    lines.append("")
    lines.append("## Images")
    for f in ("roof_top.png", "roof_heightfield.png", "elev.png", "top.png", "slices.png"):
        lines.append("- %s" % f)
    with open(_out(a, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\nreport:", _out(a, "report.md"))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="glb 건물 스캔 분석 도구")
    ap.add_argument("cmd", choices=["list", "info", "roof", "slice", "elev",
                                    "top", "compare", "report"])
    ap.add_argument("glb")
    ap.add_argument("--mesh", help="메시 이름 또는 번호")
    ap.add_argument("--up", default="y", choices=["x", "y", "z"])
    ap.add_argument("--axes", default="x,-z", help="평면 두 축 (기본 x,-z)")
    ap.add_argument("--shift", default="", help="dx,dy,dz")
    ap.add_argument("--ground", default="auto", help="auto 또는 높이 값")
    ap.add_argument("--level", type=float, default=0.15, help="옥상 레벨 묶음 허용(m)")
    ap.add_argument("--cell", type=float, default=0.25, help="높이장 칸 크기(m)")
    ap.add_argument("--z", default="", help="slice 높이 목록  예: 1,5,10")
    ap.add_argument("--auto", type=float, default=5.0, help="slice 자동 간격(m)")
    ap.add_argument("--model", default="", help="compare: 모델 OBJ 경로")
    ap.add_argument("-o", "--out", default="")
    a = ap.parse_args()
    fn = {"list": cmd_list, "info": cmd_info, "roof": cmd_roof,
          "slice": cmd_slice, "elev": cmd_elev, "top": cmd_top,
          "compare": cmd_compare, "report": cmd_report}[a.cmd]
    if a.cmd == "compare" and not a.model:
        raise SystemExit("compare needs --model <obj>")
    fn(a)


if __name__ == "__main__":
    main()
