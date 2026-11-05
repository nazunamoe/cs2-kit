# -*- coding: utf-8 -*-
"""Reconstruct simplified mass volumes from GLB cross-sections.

  python tools/glb_shape.py photos/scan.glb --list
  python tools/glb_shape.py photos/scan.glb --mesh-index 3 --out generic_spec.json --force
  python tools/glb_shape.py photos/scan.glb --mesh Building --levels 0,6,12 --out generic_spec.json

The output is a new, simplified volume specification. No source triangles, textures,
or facade materials are copied. Inspect the footprint preview before adding openings.
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

from proj import ROOT, KIT, NAME  # noqa: F401  (activates the explicit project)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_measure as GM  # noqa: E402
import glb_slices as GS  # noqa: E402
sys.path.insert(0, KIT)
import cs2kit as K  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ring_area(ring):
    return 0.5 * sum(ring[i][0] * ring[(i + 1) % len(ring)][1]
                     - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring)))


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for i, a in enumerate(ring):
        b = ring[(i + 1) % len(ring)]
        if (a[1] > y) != (b[1] > y):
            cross_x = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < cross_x:
                inside = not inside
    return inside


def rdp(points, tolerance):
    if len(points) <= 2:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        a, b = np.array(points[first]), np.array(points[last])
        ab = b - a
        denom = float(np.dot(ab, ab))
        best_i, best_d = None, tolerance
        for i in range(first + 1, last):
            p = np.array(points[i])
            t = max(0.0, min(1.0, float(np.dot(p - a, ab)) / denom)) if denom else 0.0
            d = float(np.linalg.norm(p - (a + t * ab)))
            if d > best_d:
                best_i, best_d = i, d
        if best_i is not None:
            keep[best_i] = True
            stack.extend(((first, best_i), (best_i, last)))
    return [p for p, use in zip(points, keep) if use]


def simplify_ring(points, tolerance, max_points):
    pts = []
    for point in points:
        p = (float(point[0]), float(point[1]))
        if not pts or math.dist(p, pts[-1]) > 0.02:
            pts.append(p)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 0.05:
        pts.pop()
    if len(pts) < 3:
        return None
    if ring_area(pts) < 0:
        pts.reverse()
    start = min(range(len(pts)), key=lambda i: (pts[i][0], pts[i][1]))
    opposite = max(range(len(pts)), key=lambda i: math.dist(pts[start], pts[i]))
    if start > opposite:
        start, opposite = opposite, start
    first = pts[start:opposite + 1]
    second = pts[opposite:] + pts[:start + 1]
    tol = tolerance
    for _ in range(16):
        result = rdp(first, tol)[:-1] + rdp(second, tol)[:-1]
        if len(result) >= 3 and abs(ring_area(result)) >= 0.1 and len(result) <= max_points:
            break
        tol *= 1.5
    if len(result) < 3:
        return None
    if ring_area(result) < 0:
        result.reverse()
    return [[round(x, 3), round(y, 3)] for x, y in result]


def describe_ring(ring):
    a = np.asarray(ring, dtype=float)
    return {
        "ring": ring,
        "area": abs(ring_area(ring)),
        "bounds": [float(a[:, 0].min()), float(a[:, 0].max()), float(a[:, 1].min()), float(a[:, 1].max())],
        "center": [float(a[:, 0].mean()), float(a[:, 1].mean())],
        "perimeter": sum(math.dist(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))),
    }


def extract_shape(V, F, z, tolerance, min_area, max_points):
    rings = GS.chain_segments(GS.slice_plane(V, F, z), tol=max(0.04, tolerance * 0.2))
    cleaned = []
    for raw in rings:
        ring = simplify_ring(raw, tolerance, max_points)
        if ring and abs(ring_area(ring)) >= min_area:
            cleaned.append(ring)
    outer = []
    holes = 0
    for i, ring in enumerate(cleaned):
        depth = 0
        point = tuple(ring[0])
        for j, other in enumerate(cleaned):
            if i != j and abs(ring_area(other)) > abs(ring_area(ring)) and point_in_ring(point, other):
                depth += 1
        if depth % 2:
            holes += 1
        else:
            outer.append(ring)
    described = [describe_ring(ring) for ring in outer]
    described.sort(key=lambda d: (round(d["center"][1], 2), round(d["center"][0], 2)))
    return described, holes, len(rings)


def same_shape(a, b, tolerance):
    if not a or len(a) != len(b):
        return False
    available = list(b)
    for left in a:
        if not available:
            return False
        right = min(available, key=lambda d: math.dist(left["center"], d["center"]))
        available.remove(right)
        if math.dist(left["center"], right["center"]) > max(2.0, tolerance * 4):
            return False
        if abs(left["area"] - right["area"]) / max(left["area"], right["area"]) > 0.08:
            return False
        if abs(left["perimeter"] - right["perimeter"]) / max(left["perimeter"], right["perimeter"]) > 0.10:
            return False
        if max(abs(x - y) for x, y in zip(left["bounds"], right["bounds"])) > max(0.8, tolerance * 2.5):
            return False
    return True


def automatic_groups(V, F, height, tolerance, min_area, max_points, warnings):
    step = max(0.75, min(2.0, height / 20.0))
    start = min(1.0, height * 0.15)
    levels = list(np.arange(start, max(start + 0.01, height - 0.2), step))
    if not levels or levels[-1] < height - 0.35:
        levels.append(height - 0.25)
    groups = []
    for z in levels:
        if z <= 0 or z >= height:
            continue
        shape, holes, raw_count = extract_shape(V, F, float(z), tolerance, min_area, max_points)
        if holes:
            warnings.append(f"z={z:.2f}: omitted {holes} inner ring(s); courtyards and holes need manual review")
        if not shape:
            if raw_count:
                warnings.append(f"z={z:.2f}: no outer footprint passed the area/simplification filters")
            continue
        if groups and same_shape(groups[-1]["shape"], shape, tolerance):
            groups[-1]["items"].append((float(z), shape))
            groups[-1]["end"] = float(z)
        else:
            groups.append({"start": float(z), "end": float(z), "shape": shape, "items": [(float(z), shape)]})
    for group in groups:
        group["shape"] = group["items"][len(group["items"]) // 2][1]
    for i in range(len(groups) - 1):
        lower, upper = groups[i], groups[i + 1]
        lo, hi = lower["end"], upper["start"]
        for _ in range(6):
            mid = (lo + hi) / 2
            shape, _, _ = extract_shape(V, F, mid, tolerance, min_area, max_points)
            if same_shape(lower["shape"], shape, tolerance):
                lo = mid
            else:
                hi = mid
        lower["boundary"] = (lo + hi) / 2
    return groups


def explicit_groups(V, F, levels, height, tolerance, min_area, max_points, warnings):
    boundaries = [0.0] + levels + [height]
    groups = []
    for z0, z1 in zip(boundaries, boundaries[1:]):
        z = (z0 + z1) / 2
        shape, holes, _ = extract_shape(V, F, z, tolerance, min_area, max_points)
        if holes:
            warnings.append(f"z={z:.2f}: omitted {holes} inner ring(s); courtyards and holes need manual review")
        if not shape:
            warnings.append(f"z={z:.2f}: empty level {z0:.2f}..{z1:.2f}; adjust --levels")
            continue
        groups.append({"start": z0, "end": z1, "shape": shape, "boundary": z1})
    return groups


def tier_hint(volume, height):
    """Conservative role hint; roof equipment/solar still needs photo confirmation."""
    z0 = float(volume["z0"])
    h = float(volume["height"])
    ring = volume["footprint"]
    area = abs(ring_area(ring))
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    mind = min(max(xs) - min(xs), max(ys) - min(ys))
    if z0 < height * 0.85:
        return "mass", True
    if h <= 0.9:
        return "parapet", True
    if mind < 0.9:
        return "screen", True
    if area >= 20.0 and h >= 3.0:
        return "roof_mass", True
    if area >= 20.0 or area < 6.0:
        return "equipment", False
    return "roof_mass", True


def draw_preview(path, volumes, warnings):
    from PIL import Image, ImageDraw
    all_points = [p for v in volumes for p in v["footprint"]]
    xs, ys = [p[0] for p in all_points], [p[1] for p in all_points]
    width, height = 1100, 800
    scale = min(700 / max(max(xs) - min(xs), 1), 700 / max(max(ys) - min(ys), 1))

    def pixel(p):
        return (50 + (p[0] - min(xs)) * scale, height - 50 - (p[1] - min(ys)) * scale)

    palette = [(186, 213, 232), (214, 190, 158), (181, 211, 181), (211, 184, 211),
               (222, 205, 137), (167, 205, 208), (221, 173, 166), (194, 194, 215)]
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 15), "Simplified GLB mass - review before facade work", fill="black")
    for i, volume in enumerate(volumes):
        points = [pixel(p) for p in volume["footprint"]]
        color = palette[i % len(palette)]
        draw.polygon(points, fill=color, outline=(35, 35, 35))
        center = np.mean(np.asarray(points), axis=0)
        draw.text(tuple(center), volume["id"], fill=(15, 15, 15))
        draw.text((820, 55 + i * 25), f"{volume['id']}  z {volume['z0']:.1f}..{volume['z0'] + volume['height']:.1f}", fill=color)
    draw.text((20, height - 25), f"{len(volumes)} simplified volume(s); {len(warnings)} review warning(s)", fill="black")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    image.save(path)


def load_and_align(args):
    js, buffers = GM.load_gltf(args.glb)
    meshes = GM.collect(js, buffers)
    if not meshes:
        raise SystemExit("no triangle meshes found")
    for mesh in meshes:
        mesh["V"] = GM.to_zup(mesh["V"], args.up) * args.scale
    if args.list:
        records = []
        for i, mesh in enumerate(meshes):
            lo, hi = mesh["V"].min(0), mesh["V"].max(0)
            records.append({"index": i, "name": mesh["name"], "size_m": [round(x, 3) for x in hi - lo],
                            "z_range": [round(lo[2], 3), round(hi[2], 3)], "triangles": len(mesh["F"])})
        return records
    selected = list(range(len(meshes)))
    if args.mesh:
        keys = [k.strip().lower() for k in args.mesh.split(",") if k.strip()]
        selected = [i for i in selected if any(k in meshes[i]["name"].lower() for k in keys)]
    if args.mesh_index:
        selected = [int(k) for k in args.mesh_index.split(",")]
        if any(i < 0 or i >= len(meshes) for i in selected):
            raise SystemExit("mesh index out of range; run --list")
    if not selected:
        raise SystemExit("no mesh matched; run --list and use --mesh or --mesh-index")
    vertices, faces, offset = [], [], 0
    for i in selected:
        vertices.append(meshes[i]["V"])
        faces.append(meshes[i]["F"] + offset)
        offset += len(meshes[i]["V"])
    V, F = np.concatenate(vertices), np.concatenate(faces)
    if args.box:
        x0, x1, y0, y1 = [float(x) for x in args.box.split(",")]
        centers = V[F].mean(1)
        F = F[(centers[:, 0] >= x0) & (centers[:, 0] <= x1)
              & (centers[:, 1] >= y0) & (centers[:, 1] <= y1)]
    if not len(F):
        raise SystemExit("selection/crop removed every triangle")
    points, _, _ = GM.sample_surface(V, F, min(args.samples, 400000), np.random.default_rng(1))
    ground = float(np.percentile(points[:, 2], 0.3))
    V[:, 2] -= ground
    points[:, 2] -= ground
    height = float(np.percentile(points[:, 2], 99.95))
    if height < 1.0:
        raise SystemExit(f"selection is only {height:.2f} m tall; check mesh selection and --scale")
    mid = points[points[:, 2] > min(1.0, height * 0.1)]
    if len(mid) < 50:
        mid = points
    angle = GM.min_area_rect(mid[:, :2]) + args.front_deg
    theta = math.radians(angle)
    c, s = math.cos(theta), math.sin(theta)

    def align(array):
        x = array[:, 0] * c + array[:, 1] * s
        y = -array[:, 0] * s + array[:, 1] * c
        return np.stack([x, y, array[:, 2]], axis=1)

    V, points = align(V), align(points)
    body = points[points[:, 2] > min(1.0, height * 0.1)]
    if len(body) < 50:
        body = points
    xmin, xmax = np.percentile(body[:, 0], [0.3, 99.7])
    ymin = np.percentile(body[:, 1], 0.3)
    V[:, 0] -= (xmin + xmax) / 2
    V[:, 1] -= ymin
    return V, F, height, angle % 360, [meshes[i]["name"] for i in selected]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb")
    ap.add_argument("--project", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--mesh", default="")
    ap.add_argument("--mesh-index", default="")
    ap.add_argument("--box", default="")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--up", choices=("y", "z"), default="y")
    ap.add_argument("--front-deg", type=float, default=0.0)
    ap.add_argument("--levels", default="", help="optional internal height boundaries, e.g. 6,12; omit for automatic slices")
    ap.add_argument("--simplify", type=float, default=0.35, help="footprint simplification tolerance in metres")
    ap.add_argument("--min-area", type=float, default=4.0, help="discard smaller section rings in square metres")
    ap.add_argument("--max-points", type=int, default=16)
    ap.add_argument("--samples", type=int, default=120000)
    ap.add_argument("--wall", default="wall")
    ap.add_argument("--roof", default="roof")
    ap.add_argument("--out", default="generic_spec.json")
    ap.add_argument("--force", action="store_true", help="replace the output spec, including its openings and attachments")
    ap.add_argument("--preview", default="previews/glb/shape.png")
    ap.add_argument("--report", default="previews/glb/shape_report.json")
    args = ap.parse_args()
    if args.simplify <= 0 or args.min_area <= 0 or args.max_points < 3 or args.max_points > 64:
        raise SystemExit("require --simplify > 0, --min-area > 0, and 3 <= --max-points <= 64")
    loaded = load_and_align(args)
    if args.list:
        print(json.dumps({"status": "OK", "meshes": loaded,
                          "next_action": {"command": None, "reason": "select only building meshes, then generate the mass spec"}}, ensure_ascii=False))
        return
    V, F, height, angle, mesh_names = loaded
    out = os.path.abspath(args.out)
    if os.path.exists(out) and not args.force:
        raise SystemExit(f"output exists: {args.out}; choose another --out or explicitly use --force")
    warnings = []
    if args.levels:
        levels = sorted(float(x) for x in args.levels.split(","))
        if any(x <= 0 or x >= height for x in levels) or len(set(levels)) != len(levels):
            raise SystemExit(f"--levels must be unique and between 0 and measured height {height:.2f}")
        groups = explicit_groups(V, F, levels, height, args.simplify, args.min_area, args.max_points, warnings)
    else:
        groups = automatic_groups(V, F, height, args.simplify, args.min_area, args.max_points, warnings)
    if not groups:
        raise SystemExit("no usable building footprint; inspect mesh selection, scale, and filters")
    volumes = []
    for i, group in enumerate(groups):
        z0 = 0.0 if i == 0 else groups[i - 1]["boundary"]
        z1 = height if i == len(groups) - 1 else group["boundary"]
        if z1 <= z0:
            raise SystemExit("non-positive automatic height interval; use explicit --levels after inspecting the scan")
        for j, shape in enumerate(group["shape"]):
            volume = {"id": f"mass_{i:02d}_{j:02d}", "footprint": shape["ring"],
                      "height": round(z1 - z0, 3), "z0": round(z0, 3),
                      "wall": args.wall, "roof": args.roof}
            role, keep_solid = tier_hint(volume, height)
            volume.update(role=role, keep_solid=keep_solid, source_section_z=round(z0, 3))
            volumes.append(volume)
            if role == "equipment":
                warnings.append(f"{volume['id']}: roof tier looks like equipment/solar; verify photos before keeping it solid")
    if len(groups) > 12:
        warnings.append("many section changes detected; scan noise or facade slabs may have created extra mass tiers")
    if any(len(v["footprint"]) >= args.max_points for v in volumes):
        warnings.append("one or more footprints reached --max-points; inspect simplification before facade placement")
    source_path = os.path.abspath(args.glb)
    try:
        source_name = os.path.relpath(source_path, ROOT).replace(os.sep, "/")
    except ValueError:
        source_name = source_path
    spec = {
        "source": {"type": "simplified_glb_mass", "file": source_name, "sha256": sha256(source_path),
                   "scale": args.scale, "up": args.up, "front_deg": args.front_deg,
                   "aligned_yaw_deg": round(angle, 2), "simplify_m": args.simplify,
                   "meshes_used": mesh_names},
        "review": {"required": True, "preview": args.preview.replace(os.sep, "/"),
                   "note": "Mass evidence only. Verify footprint tiers, front direction, ground, and hidden walls against photos."},
        "volumes": volumes, "openings": [], "attachments": [],
    }
    K.validate_volume_spec(spec)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    temporary = out + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temporary, out)
    preview = os.path.abspath(args.preview)
    report = os.path.abspath(args.report)
    draw_preview(preview, volumes, warnings)
    report_data = {"status": "OK", "measured_height_m": round(height, 3), "volume_count": len(volumes),
                   "section_count": len(groups), "warnings": warnings,
                   "volumes": [{"id": v["id"], "z0": v["z0"], "z1": round(v["z0"] + v["height"], 3),
                                "points": len(v["footprint"]), "role": v.get("role"),
                                "keep_solid": v.get("keep_solid")} for v in volumes]}
    os.makedirs(os.path.dirname(report) or ".", exist_ok=True)
    with open(report, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    generators = sorted(f for f in os.listdir(ROOT) if f.endswith("_cs2.py"))
    command = None
    if len(generators) == 1 and NAME:
        command = f"python tools/agent.py cycle --project {NAME} --generator {generators[0]} --mode quick --label mass --brief --json"
    result = dict(report_data)
    result.update({"spec": os.path.relpath(out, ROOT).replace(os.sep, "/"),
                   "preview": os.path.relpath(preview, ROOT).replace(os.sep, "/"),
                   "report": os.path.relpath(report, ROOT).replace(os.sep, "/"),
                   "next_action": {"command": command,
                                   "reason": "inspect the mass preview and source alignment, then run quick; add facade evidence separately"}})
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
