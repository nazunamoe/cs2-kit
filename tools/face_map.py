# -*- coding: utf-8 -*-
"""Draw a labeled wall/role map and write work/face_map.md.

  python tools/face_map.py output/<asset> [--refs photo_refs.json]

Roles use world axes: front=-Y, back=+Y, right=+X, left=-X.
The 90/270 degree photo views are often corner views after GLB alignment;
pass photo_refs.json with photo_azimuth_deg (or yaw_deg) to get warnings.
"""
import argparse
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from proj import ROOT  # noqa: E402


ROLE_COLOR = {
    "front": (35, 95, 210),
    "back": (30, 160, 90),
    "right": (230, 140, 20),
    "left": (200, 55, 55),
    "step": (110, 110, 110),
}


def role_of(normal_deg):
    n = float(normal_deg) % 360.0
    if 170.0 <= n <= 190.0:
        return "front"
    if n <= 10.0 or n >= 350.0:
        return "back"
    if 75.0 <= n <= 105.0:
        return "right"
    if 255.0 <= n <= 285.0:
        return "left"
    return "step"


def angle_diff(a, b):
    return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("asset", help="asset folder, e.g. output/Name_L1_6x6")
    ap.add_argument("--out", default="previews/face_map.png")
    ap.add_argument("--md", default="work/face_map.md")
    ap.add_argument("--json", default="work/face_map.json")
    ap.add_argument("--refs", default="photo_refs.json")
    ap.add_argument("--volume", default=None,
                    help="only draw walls of this volume (default: mass_01_00 when present)")
    a = ap.parse_args()

    asset_dir = a.asset if os.path.isabs(a.asset) else os.path.join(ROOT, a.asset)
    man_path = os.path.join(asset_dir, "manifest.json")
    if not os.path.exists(man_path):
        sys.exit(f"[face_map] manifest not found: {man_path}")
    manifest = json.load(open(man_path, encoding="utf-8"))
    walls = ((manifest.get("metadata") or {}).get("walls") or {})
    if not walls:
        sys.exit("[face_map] manifest.metadata.walls is empty; export wall metadata first")

    all_walls = walls
    volumes = {w.get("volume_id") for w in walls.values() if w.get("volume_id")}
    volume = None if a.volume == "all" else (a.volume or ("mass_01_00" if "mass_01_00" in volumes else None))
    if volume:
        walls = {wid: w for wid, w in walls.items() if w.get("volume_id") == volume}
        if not walls:
            sys.exit(f"[face_map] no walls for volume {volume}")

    rows = []
    pts = []
    for wid, w in walls.items():
        p0, p1 = w.get("p0"), w.get("p1")
        if not p0 or not p1:
            continue
        role = role_of(w.get("normal_deg", 0.0))
        mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        rows.append(dict(wall_id=wid, role=role, normal_deg=round(float(w.get("normal_deg", 0.0)), 1),
                         length_m=round(float(w.get("length_m", 0.0)), 2),
                         mid=[round(mid[0], 2), round(mid[1], 2)],
                         p0=list(p0), p1=list(p1)))
        pts.extend([p0, p1])
    if not pts:
        sys.exit("[face_map] no wall endpoints")

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pad = 3.0
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    W, H, M = 1100, 900, 70
    sc = min((W - 2 * M) / max(1e-6, x1 - x0), (H - 2 * M) / max(1e-6, y1 - y0))
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def T(x, y):
        return (W / 2 + (x - cx) * sc, H / 2 - (y - cy) * sc)

    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.load_default(size=14)
        small = ImageFont.load_default(size=11)
    except Exception:
        font = small = None
    d.text((15, 12), "world axes: front=-Y  back=+Y  right=+X  left=-X", fill=(0, 0, 0), font=font)
    d.text((15, 32), "photo 90/270 may be 44-degree corner views; use --refs warnings", fill=(90, 90, 90), font=small)
    # axes
    d.line([T(x0 + 1, y0 + 1), T(x0 + 6, y0 + 1)], fill=(0, 0, 0), width=2)
    d.text((T(x0 + 6, y0 + 1)[0] + 4, T(x0 + 6, y0 + 1)[1] - 7), "+X", fill=(0, 0, 0), font=small)
    d.line([T(x0 + 1, y0 + 1), T(x0 + 1, y0 + 6)], fill=(0, 0, 0), width=2)
    d.text((T(x0 + 1, y0 + 6)[0] + 4, T(x0 + 1, y0 + 6)[1] - 7), "+Y", fill=(0, 0, 0), font=small)

    for r in rows:
        col = ROLE_COLOR.get(r["role"], (110, 110, 110))
        p0 = T(*r["p0"])
        p1 = T(*r["p1"])
        d.line([p0, p1], fill=col, width=4)
        mx, my = T(*r["mid"])
        n = math.radians(r["normal_deg"])
        ax, ay = math.sin(n), math.cos(n)
        d.line([(mx, my), (mx + ax * 22, my - ay * 22)], fill=col, width=2)
        label = f"{r['wall_id'].split(':')[-1]} {r['role']} {r['length_m']:.1f}m"
        d.text((mx + 4, my + 4), label, fill=col, font=small)
    os.makedirs(os.path.dirname(os.path.join(ROOT, a.out)) or ".", exist_ok=True)
    out_png = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    im.save(out_png)

    warnings = []
    refs_path = a.refs if os.path.isabs(a.refs) else os.path.join(ROOT, a.refs)
    if os.path.exists(refs_path):
        try:
            refs = json.load(open(refs_path, encoding="utf-8"))
            for ref in refs.get("facades", []):
                wid = ref.get("wall_id")
                az = ref.get("photo_azimuth_deg", ref.get("yaw_deg"))
                w = all_walls.get(wid)
                if not w or az is None:
                    continue
                diff = angle_diff(az, w.get("normal_deg", 0.0))
                if diff > 15.0:
                    warnings.append(f"{ref.get('file', ref.get('side', '?'))} wall {wid}: photo {az} deg vs normal "
                                    f"{w.get('normal_deg')} deg = {diff:.1f} deg corner view")
        except Exception as exc:
            warnings.append(f"could not read refs: {exc}")
    else:
        warnings.append(f"no {os.path.basename(refs_path)}; corner-view check skipped")

    md = a.md if os.path.isabs(a.md) else os.path.join(ROOT, a.md)
    os.makedirs(os.path.dirname(md), exist_ok=True)
    with open(md, "w", encoding="utf-8") as f:
        f.write(f"# Face map - {os.path.basename(asset_dir)}\n\n")
        f.write("World axes: front=-Y, back=+Y, right=+X, left=-X. "
                "Photo azimuths are scene angles; the GLB may be rotated, so 90/270 views can be corners.\n\n")
        if volume:
            f.write(f"Volume filter: `{volume}`. Use `--volume all` or another id to include other tiers.\n\n")
        f.write("| wall_id | role | normal_deg | length_m | mid (x,y) |\n|---|---|---:|---:|---|\n")
        for r in rows:
            f.write(f"| {r['wall_id']} | {r['role']} | {r['normal_deg']:.1f} | {r['length_m']:.2f} | "
                    f"{r['mid'][0]:.2f}, {r['mid'][1]:.2f} |\n")
        if warnings:
            f.write("\n## Warnings\n\n")
            for w in warnings:
                f.write(f"- {w}\n")
        else:
            f.write("\n## Warnings\n\n- none\n")
    js = a.json if os.path.isabs(a.json) else os.path.join(ROOT, a.json)
    os.makedirs(os.path.dirname(js), exist_ok=True)
    with open(js, "w", encoding="utf-8") as f:
        json.dump(dict(asset=os.path.basename(asset_dir), walls=rows, warnings=warnings), f,
                  ensure_ascii=False, indent=1)
    print(f"[face_map] {os.path.relpath(out_png, ROOT)}")
    print(f"[face_map] {os.path.relpath(md, ROOT)}  ({len(rows)} walls)")
    for w in warnings:
        print(f"  WARN {w}")


if __name__ == "__main__":
    main()
