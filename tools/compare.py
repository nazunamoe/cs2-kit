# -*- coding: utf-8 -*-
"""
compare.py — 수정 전후 비교 (다른 부분을 건드리지 않았는지 확인)

  python tools/compare.py snap output/<asset>                 → backup/<asset>_<시각>/ 에 복사 (수정 전에 한 번)
  python tools/compare.py diff backup/<asset>_<시각> output/<asset>
      메시별 tris 차이, 추가·삭제된 면 수와 위치(범위), 텍스처 픽셀이 바뀐 영역(px 범위)을 출력
      --box=x0,x1,y0,y1,z0,z1  (음수가 있으면 = 로 붙여 쓸 것) 이 범위 밖에서 바뀐 면이 있으면 오류 (예: "입구만 고쳤다" 확인)
종료 코드: --box 위반이면 1
"""
import argparse
import os
import shutil
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)
from objio import MAPS, find_asset, load_asset, load_png, tex_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass


def face_keys(mesh, with_uv=True):
    keys = {}
    for i, f in enumerate(mesh.faces):
        q = np.round(mesh.verts[f], 3)
        k = tuple(sorted(map(tuple, q))) + (tuple(np.round(mesh.uvs[i], 4).flatten()) if with_uv else ())
        keys.setdefault(k, []).append(i)
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["snap", "diff"])
    ap.add_argument("a")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--box")
    ap.add_argument("--backup", default="backup")
    a = ap.parse_args()
    if a.cmd == "snap":
        asset, objdir, texdir = find_asset(a.a)
        dst = os.path.join(a.backup, f"{asset}_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copytree(texdir, dst)
        print(f"[snap] {dst}")
        return
    A = load_asset(a.a); B = load_asset(a.b)
    box = [float(t) for t in a.box.split(",")] if a.box else None
    bad = 0
    for k in sorted(set(A[1]) | set(B[1])):
        ma, mb = A[1].get(k), B[1].get(k)
        if ma is None or mb is None:
            print(f"  {k}: {'added' if ma is None else 'removed'}"); continue
        wu = "win" not in k   # 창 UV 는 창 하나만 늘어도 전부 다시 배정되므로 위치만 비교
        ka, kb = face_keys(ma, wu), face_keys(mb, wu)
        rem = [i for key in set(ka) - set(kb) for i in ka[key]]
        add = [i for key in set(kb) - set(ka) for i in kb[key]]
        line = f"  {k}: tris {ma.tri_count} -> {mb.tri_count}  faces -{len(rem)} +{len(add)}"
        pts = [ma.verts[ma.faces[i]].mean(0) for i in rem] + [mb.verts[mb.faces[i]].mean(0) for i in add]
        if pts:
            P = np.array(pts)
            line += f"  range x[{P[:,0].min():.1f},{P[:,0].max():.1f}] y[{P[:,1].min():.1f},{P[:,1].max():.1f}] z[{P[:,2].min():.1f},{P[:,2].max():.1f}]"
            if box:
                out = ~((P[:, 0] >= box[0]) & (P[:, 0] <= box[1]) & (P[:, 1] >= box[2]) & (P[:, 1] <= box[3]) &
                        (P[:, 2] >= box[4]) & (P[:, 2] <= box[5]))
                if out.any():
                    bad += int(out.sum())
                    line += f"  ERROR {int(out.sum())} changed outside --box (e.g. {np.round(P[out][0], 2).tolist()})"
        print(line)
    for lod2 in (False, True):
        for m in MAPS:
            pa, pb = tex_path(A[2], A[0], m, lod2), tex_path(B[2], B[0], m, lod2)
            if not (pa and pb):
                continue
            ia, ib = load_png(pa), load_png(pb)
            name = ("LOD2_" if lod2 else "") + m
            if ia.shape != ib.shape:
                print(f"  {name}: size {ia.shape[:2]} -> {ib.shape[:2]}"); continue
            d = np.abs(ia - ib).max(-1) > 2
            if d.any():
                ys, xs = np.nonzero(d)
                print(f"  {name}: {d.mean() * 100:.2f}% pixels changed, px x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]")
    print("[diff] done" + (f" - ERROR {bad} changes outside --box" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
