# -*- coding: utf-8 -*-
"""
band_scan.py - facade_paint.py 가 찾은 층/창 경계로 벽을 [층(+스팬드럴/창/헤드 서브밴드) x 창-열/기둥-열]
2D 그리드로 나눠, 각 칸의 대표 색을 뽑고 K-means 로 (주조색/보조색/강조색/저층 석재) 라벨을 매긴다.
floor/window 탐지 자체는 facade_paint.py 와 완전히 같은 코드를 재사용한다(새로 안 만든다).

    python tools/band_scan.py --refs photo_refs.json --name front [--wall-size WxH] [--ppm 30]
                               [--fh 2.9] [--window-mode auto] [--k 4] [--out previews/paint_grid]

출력 previews/paint_grid/<name>.json (cs2kit.apply_facade_paint_grid 에 바로 넣을 수 있는 모양):
  {"rows": R, "cols": C, "cell_id": [[0,0,1,...], ...], "palette": {"0":"#dadcdf", ...},
   "row_z": [z0..zR] (절대 높이, 오름차순), "col_a": [a0..aC] (벽 기준 가로 거리, 오름차순),
   "accent_bands": [...], "mixed_cells": [[r,c], ...], "raw_L_ratio": [[..],[..]]}

주의: 아직 실제 사진으로 검증 안 됨(합성 이미지로만 실행 확인). 셀 표준편차가 높아 MIXED 로 빠진
칸은 라벨을 "가까운 깨끗한 칸" 으로 채우되, palette 색 자체는 그 칸 때문에 바뀌지 않는다.
"""
import argparse
import json
import os
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facade_paint as FP  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

MIXED_STD = 12.0   # 이보다 표준편차 높은 칸은 유리/그림자 혼입(MIXED)으로 뺀다


def _robust_patch_median(patch):
    """LESSONS.md 규칙: 박스 안에서 표준편차가 가장 낮은 부분으로 중앙값을 잡는다(배경 섞임 방지).
    patch: (h, w, 3). 3x3 서브블록 중 표준편차 최소인 것을 골라 중앙값 반환 + 그 표준편차."""
    h, w, _ = patch.shape
    if h < 6 or w < 6:
        g = patch.reshape(-1, 3)
        return np.median(g, 0), float(g.std())
    best = None
    for gy in range(3):
        for gx in range(3):
            y0, y1 = int(h * gy / 3), int(h * (gy + 1) / 3)
            x0, x1 = int(w * gx / 3), int(w * (gx + 1) / 3)
            sub = patch[y0:y1, x0:x1].reshape(-1, 3)
            if len(sub) < 4:
                continue
            sd = float(sub.std())
            if best is None or sd < best[1]:
                best = (np.median(sub, 0), sd)
    return best if best else (np.median(patch.reshape(-1, 3), 0), float(patch.std()))


def _dedup_boundaries(vals, min_gap):
    """오름차순 경계 목록에서 min_gap 보다 가까운 것들을 하나로 합친다(퇴화 칸 방지)."""
    vals = sorted(vals)
    out = [vals[0]]
    for v in vals[1:]:
        if v - out[-1] >= min_gap:
            out.append(v)
        else:
            out[-1] = v   # 가까운 쌍은 뒤쪽 값으로 합침(경계가 하나로 줄어듦)
    return out


def build_grid(wall, fl, T):
    """fl(find_floors) + T(build_windows 의 floor-invariant 창 템플릿) -> row_z(절대 m, 오름차순),
    col_a(벽 기준 가로 m, 오름차순). 행: 층마다 창 세로 범위로 스팬드럴/창/헤드 3 서브밴드(있으면).
    열: T 를 가로로 투영해 연속된 run(창 칸)과 그 사이(기둥 칸)로 나눈다."""
    ppm, w0, pitch = wall["ppm"], wall["x0"], fl["pitch_m"]
    prof = T[int(FP.NY * 0.15):int(FP.NY * 0.85)].mean(0) > 0.5
    runs = FP.runs_of(prof, max(2, int(0.2 * ppm)))
    col_px = sorted({0, wall["W"]} | {c for r in runs for c in r})
    col_a = [round(w0 + c / ppm, 3) for c in col_px]
    rows_t = np.where(T.mean(1) > 0.1)[0]
    if len(rows_t):
        sub_v = sorted({0.0, 1.0, float(1 - rows_t[0] / FP.NY), float(1 - (rows_t[-1] + 1) / FP.NY)})
    else:
        sub_v = [0.0, 1.0]
    centres = sorted(fl["centres"], key=lambda t: -t[0])   # top(작은 row idx) 먼저? centres 는 (px_row, found)
    row_z = []
    for c, _ in centres:
        z_center = FP.row_z(wall, c)
        z0, z1 = z_center - pitch / 2, z_center + pitch / 2
        for v in sub_v:
            row_z.append(round(z0 + v * pitch, 3))
    min_gap = 1.5 / ppm
    row_z = _dedup_boundaries(sorted(set(row_z)), min_gap)
    col_a = _dedup_boundaries(col_a, min_gap)
    return row_z, col_a


def scan_cells(wall, row_z, col_a, k):
    arr = wall["arr"]
    H, W = wall["H"], wall["W"]
    ppm, z1 = wall["ppm"], wall["z1"]
    rows, cols = len(row_z) - 1, len(col_a) - 1
    meds = np.zeros((rows, cols, 3))
    stds = np.full((rows, cols), 1e9)   # 퇴화 칸은 std=무한대로 둬서 반드시 MIXED 로 빠지게 함
    raw_meds = np.zeros((rows, cols, 3))
    valid = np.zeros((rows, cols), bool)
    for r in range(rows):
        za, zb = row_z[r], row_z[r + 1]
        y0, y1 = int(round((z1 - zb) * ppm)), int(round((z1 - za) * ppm))
        y0, y1 = max(0, min(y0, H - 1)), max(1, min(y1, H))
        for c in range(cols):
            x0, x1 = int(round((col_a[c] - wall["x0"]) * ppm)), int(round((col_a[c + 1] - wall["x0"]) * ppm))
            x0, x1 = max(0, min(x0, W - 1)), max(1, min(x1, W))
            if y1 <= y0 or x1 <= x0:
                continue
            patch = arr[y0:y1, x0:x1]
            med, sd = _robust_patch_median(patch)
            meds[r, c], stds[r, c] = med, sd
            raw_meds[r, c] = np.median(patch.reshape(-1, 3), 0)
            valid[r, c] = True
    return meds, stds, raw_meds, valid


def cluster_cells(meds, stds, k):
    rows, cols, _ = meds.shape
    mixed = stds > MIXED_STD
    clean = ~mixed
    lab = FP.to_lab(meds)
    ref_L = float(np.median(lab[clean][:, 0])) if clean.any() else float(np.median(lab[..., 0]))
    norm_lab = lab.copy()
    norm_lab[..., 0] = ref_L   # same-L: 조명 차이를 지우고 색(a,b)만으로 군집
    flat = norm_lab[clean].reshape(-1, 3) if clean.any() else norm_lab.reshape(-1, 3)
    kk = min(k, max(1, len(flat)))
    cen = FP.kmeans_lab(flat, kk) if len(flat) >= kk else lab.reshape(-1, 3)[:kk]
    full_norm = norm_lab.reshape(-1, 3)
    d = np.linalg.norm(full_norm[:, None, :] - cen[None, :, :], axis=-1)
    cell_id = d.argmin(1).reshape(rows, cols)
    # 가까운 깨끗한 칸으로 MIXED 라벨을 메운다(팔레트 색 자체는 바꾸지 않음) - 단순 최근접 사본
    if mixed.any() and clean.any():
        cy, cx = np.where(clean)
        for ry, rx in zip(*np.where(mixed)):
            dd = (cy - ry) ** 2 + (cx - rx) ** 2
            j = np.argmin(dd)
            cell_id[ry, rx] = cell_id[cy[j], cx[j]]
    palette = {str(i): FP.hexc(FP.from_lab(cen[i])) for i in range(len(cen))}
    return cell_id.tolist(), palette, mixed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refs", required=True)
    ap.add_argument("--name")
    ap.add_argument("--wall-size")
    ap.add_argument("--ppm", type=float, default=30.0)
    ap.add_argument("--fh", type=float)
    ap.add_argument("--window-mode", default="auto")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--out", default="previews/paint_grid")
    a = ap.parse_args()

    args = SimpleNamespace(refs=a.refs, name=a.name, wall_size=a.wall_size, ppm=a.ppm)
    wall = FP.load_wall(args)
    fl = FP.find_floors(wall, a.fh)
    S = FP.band_stack(wall, fl)
    M, mode_info = FP.window_mask(S, wall, a.window_mode, quiet=True)
    T, iou, special = FP.build_windows(M)
    row_z, col_a = build_grid(wall, fl, T)
    meds, stds, raw_meds, valid = scan_cells(wall, row_z, col_a, a.k)
    cell_id, palette, mixed = cluster_cells(meds, stds, a.k)
    raw_L = FP.to_lab(raw_meds)[..., 0]
    norm_L = FP.to_lab(meds)[..., 0]
    raw_L_ratio = (raw_L / np.maximum(norm_L, 1e-6)).round(3).tolist()
    accent = []
    rows = len(row_z) - 1
    for r in range(rows):
        labs_in_row = set(cell_id[r])
        if len(labs_in_row) == 1:
            lbl = next(iter(labs_in_row))
            neigh = set()
            if r > 0:
                neigh |= set(cell_id[r - 1])
            if r + 1 < rows:
                neigh |= set(cell_id[r + 1])
            if neigh and lbl not in neigh:
                accent.append({"row_range": [r, r], "label": lbl})
    out = dict(rows=rows, cols=len(col_a) - 1, cell_id=cell_id, palette=palette,
               row_z=row_z, col_a=col_a, accent_bands=accent,
               mixed_cells=[[int(r), int(c)] for r, c in zip(*np.where(mixed))],
               raw_L_ratio=raw_L_ratio, window_mode=mode_info)
    os.makedirs(a.out, exist_ok=True)
    outp = os.path.join(a.out, "%s.json" % wall["name"])
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("%s: %d rows x %d cols, %d colour(s) %s, %d mixed cell(s) -> %s" %
          (wall["name"], out["rows"], out["cols"], len(palette), list(palette.values()), len(out["mixed_cells"]), outp))


if __name__ == "__main__":
    main()
