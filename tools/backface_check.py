# -*- coding: utf-8 -*-
"""Fast CPU backface/silhouette pre-check (no Blender).

  python tools/backface_check.py --project P output/<asset>
  python tools/backface_check.py --self-test

A hole is a pixel where cull-off has geometry but cull-on does not:
the camera sees only a back face. This catches single-sided paint quads,
open screen/solar corners, and open railing undersides before final LOD.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402,F401
from objio import Mesh, load_asset  # noqa: E402
from render import Tex, render  # noqa: E402

LIMIT = 0.05
MARGIN = 0.03


def mask_of(img):
    return np.asarray(img.convert("L")) > 127


def dilate(mask, radius=1):
    if radius <= 0:
        return mask
    im = Image.fromarray((mask.astype(np.uint8) * 255))
    return np.asarray(im.filter(ImageFilter.MaxFilter(2 * radius + 1)).convert("L")) > 127


def ground_mesh(mesh):
    """Closed ground slab like lod_check's ground, so the open building bottom is not a hole."""
    V = np.asarray(mesh.verts)
    x0, x1 = float(V[:, 0].min()) - 8, float(V[:, 0].max()) + 8
    y0, y1 = float(V[:, 1].min()) - 8, float(V[:, 1].max()) + 8
    z0, z1 = -0.3, -0.01
    verts = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                      [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    faces = [[0, 3, 2, 1], [0, 4, 7, 3], [1, 2, 6, 5],
             [4, 5, 6, 7], [3, 7, 6, 2], [0, 1, 5, 4]]
    return Mesh(verts, faces, [np.zeros((4, 2)) for _ in faces])


def part_sets(meshes, names):
    out = []
    for name in names:
        parts = []
        if meshes.get(name) is not None:
            parts.append((meshes[name], "wall"))
        win = name + "_win"
        if meshes.get(win) is not None:
            parts.append((meshes[win], "window"))
        if parts:
            out.append((name, parts))
    return out


def check_asset(path, names, res, az_count, elevs, dilate_px=1):
    asset, meshes, texdir, _ = load_asset(path)
    tex = Tex(texdir, asset, False, "color")
    groups = part_sets(meshes, names)
    if not groups:
        raise SystemExit("no requested parts found")
    ground = ground_mesh(meshes["main"])
    rows = []
    for gname, parts in groups:
        parts = parts + [(ground, "wall")]
        worst = None
        for el in elevs:
            for k in range(az_count):
                az = 360.0 * k / az_count
                off = mask_of(render(parts, tex, az, el, (res, res), cull=False, mask=True, label=False))
                on = dilate(mask_of(render(parts, tex, az, el, (res, res), cull=True, mask=True, label=False)),
                            dilate_px)
                hole = off & ~on
                pct = 100.0 * hole.sum() / max(1, int(off.sum()))
                row = dict(part=gname, az=round(az, 1), el=el, hole_pct=round(pct, 3),
                           hole_px=int(hole.sum()), mask_px=int(off.sum()))
                rows.append(row)
                if worst is None or row["hole_pct"] > worst["hole_pct"]:
                    worst = row
        print(f"  {gname} max {worst['hole_pct']:.3f}% (az {worst['az']:.0f}, el {worst['el']:+.0f})")
    bad = [r for r in rows if r["hole_pct"] > LIMIT]
    marginal = any(r["hole_pct"] > MARGIN for r in rows)
    out_dir = os.path.join(proj.ROOT, "previews", "backface", asset)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "backface.json"), "w", encoding="utf-8") as f:
        json.dump(dict(asset=asset, rows=rows), f, indent=1)
    status = "FAIL" if bad else "PASS"
    print(f"BACKFACE {status} max={max(r['hole_pct'] for r in rows):.3f}%"
          + (" marginal=1" if marginal and not bad else "")
          + f" -> {os.path.relpath(out_dir, proj.ROOT)}")
    return 0 if not bad else 1


def self_test():
    V = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                  [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)
    faces = [[0, 1, 2, 3], [0, 4, 7, 3], [1, 2, 6, 5],
             [4, 5, 6, 7], [3, 7, 6, 2], [0, 1, 5, 4]]
    uv = [np.zeros((4, 2)) for _ in faces]
    closed = Mesh(V, faces, uv)
    opened = Mesh(V, faces[:-1], uv[:-1])          # remove -Y (front) face

    def holes(mesh):
        off = mask_of(render([(mesh, "wall")], None, 0, 0, (96, 96), cull=False, mask=True, label=False))
        on = mask_of(render([(mesh, "wall")], None, 0, 0, (96, 96), cull=True, mask=True, label=False))
        return int((off & ~on).sum()), int(off.sum())

    c_hole, c_px = holes(closed)
    o_hole, o_px = holes(opened)
    ok = c_hole == 0 and o_hole > 0
    print(f"BACKFACE SELFTEST {'PASS' if ok else 'FAIL'} closed={c_hole}/{c_px} open={o_hole}/{o_px}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="output/<asset> folder")
    ap.add_argument("--parts", default="main", help="comma list: main,lod1,lod2")
    ap.add_argument("--res", type=int, default=128)
    ap.add_argument("--az", type=int, default=8)
    ap.add_argument("--elev", default="-10,25")
    ap.add_argument("--dilate", type=int, default=1, help="dilate the cull-on mask to close raster cracks")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if not a.path:
        ap.error("path is required unless --self-test is used")
    elevs = [float(x) for x in a.elev.split(",") if x.strip()]
    names = [x.strip() for x in a.parts.split(",") if x.strip()]
    sys.exit(check_asset(a.path, names, a.res, max(1, a.az), elevs, max(0, a.dilate)))


if __name__ == "__main__":
    main()
