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

창 마스크와 photo_refs 의 paint_include/paint_exclude 영역을 표본에서 제외한다. 각 영역은
{"u": [0, 1], "v": [0, 1], "reason": "tree"} 형태이며 v는 항목 전체 아래=0, 위=1 이다.
MIXED/저표본 칸은 cell_id=-1 로 남아 기본 벽 재질을 유지한다. 팔레트는 실제 Lab 명도를 보존한다.
아직 실제 사진 검증은 필요하며 <name>_mask.png 에서 제외 영역을 눈으로 확인해야 한다.
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


def _robust_patch_median(patch, allowed):
    """Choose the least variable valid subblock; excluded pixels never affect colour or spread."""
    h, w, _ = patch.shape
    coverage = float(allowed.mean()) if allowed.size else 0.0
    if coverage < 0.25:
        return np.zeros(3), float("inf"), coverage
    best = None
    for gy in range(3):
        for gx in range(3):
            y0, y1 = int(h * gy / 3), int(h * (gy + 1) / 3)
            x0, x1 = int(w * gx / 3), int(w * (gx + 1) / 3)
            sub_mask = allowed[y0:y1, x0:x1]
            if sub_mask.mean() < 0.45 or sub_mask.sum() < 4:
                continue
            sub = patch[y0:y1, x0:x1][sub_mask]
            sd = float(sub.std(axis=0).mean())
            if best is None or sd < best[1]:
                best = (np.median(sub, 0), sd)
    if best is None:
        values = patch[allowed]
        return np.median(values, 0), float(values.std(axis=0).mean()), coverage
    return best[0], best[1], coverage


def entry_paint_mask(wall):
    """Normalized wall U/V include/exclude regions -> warped-image boolean mask."""
    entry = wall["entry"]
    includes = entry.get("paint_include") or (entry.get("paint") or {}).get("include") or []
    excludes = entry.get("paint_exclude") or (entry.get("paint") or {}).get("exclude") or []
    mask = np.zeros((wall["H"], wall["W"]), bool) if includes else np.ones((wall["H"], wall["W"]), bool)

    def apply(regions, value):
        for region in regions:
            u, v = region.get("u", [0, 1]), region.get("v", [0, 1])
            x0 = max(0, min(wall["W"], int(round(float(u[0]) * wall["W"]))))
            x1 = max(0, min(wall["W"], int(round(float(u[1]) * wall["W"]))))
            y0 = max(0, min(wall["H"], int(round((1 - float(v[1])) * wall["H"]))))
            y1 = max(0, min(wall["H"], int(round((1 - float(v[0])) * wall["H"]))))
            mask[y0:y1, x0:x1] = value

    apply(includes, True)
    apply(excludes, False)
    return mask


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


def scan_cells(wall, row_z, col_a, allowed):
    arr = wall["arr"]
    H, W = wall["H"], wall["W"]
    ppm, z1 = wall["ppm"], wall["z1"]
    rows, cols = len(row_z) - 1, len(col_a) - 1
    meds = np.zeros((rows, cols, 3))
    stds = np.full((rows, cols), 1e9)
    raw_meds = np.zeros((rows, cols, 3))
    coverage = np.zeros((rows, cols))
    valid = np.zeros((rows, cols), bool)
    lab = FP.to_lab(arr)
    vegetation = (lab[..., 1] < -8) & (lab[..., 2] > 8)
    allowed = allowed & (arr.mean(2) > 30) & ~vegetation
    for r in range(rows):
        za, zb = row_z[r], row_z[r + 1]
        y0, y1 = int(round((z1 - zb) * ppm)), int(round((z1 - za) * ppm))
        y0, y1 = max(0, min(y0, H - 1)), max(1, min(y1, H))
        for c in range(cols):
            x0, x1 = int(round((col_a[c] - wall["x0"]) * ppm)), int(round((col_a[c + 1] - wall["x0"]) * ppm))
            x0, x1 = max(0, min(x0, W - 1)), max(1, min(x1, W))
            if y1 <= y0 or x1 <= x0:
                continue
            patch, patch_allowed = arr[y0:y1, x0:x1], allowed[y0:y1, x0:x1]
            med, sd, cov = _robust_patch_median(patch, patch_allowed)
            meds[r, c], stds[r, c], coverage[r, c] = med, sd, cov
            if patch_allowed.any():
                raw_meds[r, c] = np.median(patch[patch_allowed], 0)
            valid[r, c] = cov >= 0.35
    return meds, stds, raw_meds, valid, coverage


def cluster_cells(meds, stds, valid, k):
    rows, cols, _ = meds.shape
    mixed = (stds > MIXED_STD) | ~valid
    clean = ~mixed
    cell_id = np.full((rows, cols), -1, int)
    if not clean.any():
        return cell_id.tolist(), {}, mixed
    lab = FP.to_lab(meds)
    flat = lab[clean]
    kk = min(k, len(flat))
    cen = FP.kmeans_lab(flat, kk)
    distances = np.linalg.norm(flat[:, None, :] - cen[None, :, :], axis=-1)
    cell_id[clean] = distances.argmin(1)
    palette = {str(i): FP.hexc(FP.from_lab(cen[i])) for i in range(len(cen))}
    return cell_id.tolist(), palette, mixed


def save_mask_preview(wall, allowed, path):
    from PIL import Image, ImageDraw
    arr = np.asarray(np.clip(wall["arr"], 0, 255), np.uint8).copy()
    arr[~allowed] = (0.4 * arr[~allowed] + 0.6 * np.array([230, 40, 40])).astype(np.uint8)
    image = Image.fromarray(arr)
    ImageDraw.Draw(image).text((5, 5), "red = excluded from paint samples", fill=(255, 255, 0))
    image.save(path)


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
    if a.k < 1:
        raise SystemExit("--k must be positive")

    args = SimpleNamespace(refs=a.refs, name=a.name, wall_size=a.wall_size, ppm=a.ppm)
    wall = FP.load_wall(args)
    fl = FP.find_floors(wall, a.fh)
    S = FP.band_stack(wall, fl)
    M, mode_info = FP.window_mask(S, wall, a.window_mode, quiet=True)
    T, iou, special = FP.build_windows(M)
    row_z, col_a = build_grid(wall, fl, T)
    allowed = entry_paint_mask(wall) & ~FP._dil(FP.mask_to_full(wall, fl, M), 2)
    meds, stds, raw_meds, valid, coverage = scan_cells(wall, row_z, col_a, allowed)
    cell_id, palette, mixed = cluster_cells(meds, stds, valid, a.k)
    if not palette:
        raise SystemExit("no reliable paint samples; inspect the ref plane, window mask, and paint_include/exclude regions")
    raw_L = FP.to_lab(raw_meds)[..., 0]
    reference_L = float(np.median(raw_L[~mixed]))
    raw_L_ratio = (raw_L / max(reference_L, 1e-6)).round(3).tolist()
    warnings = []
    entry = wall["entry"]
    if entry.get("confidence") == "low" or not (entry.get("paint") or {}).get("use_for_color", True):
        warnings.append("low-confidence or oblique color source; verify palette against a frontal photo")
    accent = []
    rows = len(row_z) - 1
    for r in range(rows):
        labs_in_row = set(cell_id[r])
        if len(labs_in_row) == 1 and -1 not in labs_in_row:
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
               sample_coverage=coverage.round(3).tolist(), raw_L_ratio=raw_L_ratio,
               palette_mode="observed_lab_lightness_preserved", source_confidence=entry.get("confidence"),
               warnings=warnings, review_required=True, window_mode=mode_info)
    os.makedirs(a.out, exist_ok=True)
    outp = os.path.join(a.out, "%s.json" % wall["name"])
    maskp = os.path.join(a.out, "%s_mask.png" % wall["name"])
    save_mask_preview(wall, allowed, maskp)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for warning in warnings:
        print("WARN " + warning)
    print("%s: %d rows x %d cols, %d colour(s) %s, %d unknown/mixed cell(s) -> %s; mask %s" %
          (wall["name"], out["rows"], out["cols"], len(palette), list(palette.values()), len(out["mixed_cells"]), outp, maskp))


if __name__ == "__main__":
    main()
