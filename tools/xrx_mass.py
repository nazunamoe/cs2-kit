# -*- coding: utf-8 -*-
"""Draft a generic_spec mass from Naver VR metadata (data.xrx.json).

  python tools/xrx_mass.py --project P --xrx photos/data.xrx.json --dongs 101,107
  python tools/agent.py glb-mass ... (for a real scan) ; this tool only uses footprints/heights

No facade evidence is created. The output is a reviewable mass draft: verify front
direction, tiers and hidden walls against photos before adding openings.
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402  (consumes --project and chdirs to the project)
sys.path.insert(0, proj.KIT)
import cs2kit as K  # noqa: E402
import glb_shape as GS  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rings_of(footprint):
    """Nested xrx footprint -> rings of (x, z) in metres."""
    rings = []

    def is_point(v):
        return isinstance(v, (list, tuple)) and len(v) >= 3 and all(isinstance(t, (int, float)) for t in v[:3])

    def rec(node):
        if isinstance(node, list) and node and all(is_point(p) for p in node):
            rings.append([(float(p[0]), float(p[2])) for p in node])
        elif isinstance(node, list):
            for child in node:
                rec(child)

    rec(footprint)
    return rings


def longest_edge(ring):
    best = None
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        d = math.dist(a, b)
        if best is None or d > best[0]:
            best = (d, a, b)
    return best[1], best[2]


def rotate(p, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def height_of(poi, floor_height):
    elevations = [float(s["elevation"]) for s in (poi.get("slices") or []) if "elevation" in s]
    floors = (poi.get("floor") or {}).get("maxFloor") or 0
    from_floors = floors * floor_height if floors else 0.0
    if elevations:
        measured = max(elevations) - min(elevations)
        if measured >= 3.0 and (not from_floors or 0.5 * from_floors <= measured <= 1.8 * from_floors):
            return measured, "slices"
        if from_floors:
            return from_floors, "floor_count"
        return measured, "slices"
    return from_floors, "floor_count"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xrx", required=True, help="Naver VR data.xrx.json")
    ap.add_argument("--dongs", default="", help="comma-separated dong names (default: all)")
    ap.add_argument("--out", default="generic_spec.json")
    ap.add_argument("--preview", default=os.path.join("previews", "xrx", "shape.png"))
    ap.add_argument("--report", default=os.path.join("previews", "xrx", "shape_report.json"))
    ap.add_argument("--simplify", type=float, default=0.6, help="footprint tolerance in metres")
    ap.add_argument("--min-area", type=float, default=20.0, help="drop rings smaller than this (m2)")
    ap.add_argument("--floor-height", type=float, default=2.9, help="fallback when slices are missing")
    ap.add_argument("--front-deg", type=float, default=0.0, help="extra rotation after auto front")
    ap.add_argument("--no-rotate", action="store_true", help="keep scene axes, no auto front")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.xrx):
        raise SystemExit(f"no such xrx file: {a.xrx}")
    if os.path.exists(a.out) and not a.force:
        raise SystemExit(f"output exists: {a.out}; use --force or another --out")
    data = json.loads(open(a.xrx, encoding="utf-8").read())
    pois = data.get("poi") or []
    want = [s.strip() for s in a.dongs.split(",") if s.strip()]
    if want:
        pois = [q for q in pois if q.get("name") in want]
    if not pois:
        raise SystemExit("no matching dong in data.xrx")

    warnings = []
    raw, meta = [], []
    for q in pois:
        rings = rings_of(q.get("footprint") or q.get("obb") or [])
        if not rings:
            warnings.append(f"{q.get('name')}: no footprint")
            continue
        rings.sort(key=lambda r: -abs(GS.ring_area(r)))
        if len(rings) > 1:
            warnings.append(f"{q.get('name')}: {len(rings)} footprint rings - kept the largest")
        ring = GS.simplify_ring(rings[0], a.simplify, 80)
        if ring is None or abs(GS.ring_area(ring)) < a.min_area:
            warnings.append(f"{q.get('name')}: footprint smaller than --min-area")
            continue
        height, source = height_of(q, a.floor_height)
        if height < 3.0:
            warnings.append(f"{q.get('name')}: height {height:.1f} m looks wrong")
        if source == "floor_count":
            warnings.append(f"{q.get('name')}: height from floor count, not slices")
        raw.append(ring)
        meta.append({"name": str(q.get("name")), "ring": ring, "height": height, "height_source": source})
    if not raw:
        raise SystemExit("no usable footprints")

    largest = max(range(len(raw)), key=lambda i: abs(GS.ring_area(raw[i])))
    if a.no_rotate:
        angle = math.radians(a.front_deg)
    else:
        edge = longest_edge(raw[largest])
        base = -math.atan2(edge[1][1] - edge[0][1], edge[1][0] - edge[0][0])
        ring_rot = [rotate(p, base) for p in raw[largest]]
        e0, e1 = rotate(edge[0], base), rotate(edge[1], base)
        cx = sum(p[0] for p in ring_rot) / len(ring_rot)
        cy = sum(p[1] for p in ring_rot) / len(ring_rot)
        mx, my = (e0[0] + e1[0]) / 2, (e0[1] + e1[1]) / 2
        nx, ny = e1[1] - e0[1], -(e1[0] - e0[0])
        if nx * (cx - mx) + ny * (cy - my) > 0:  # normal points inward
            nx, ny = -nx, -ny
        flip = math.pi if ny > 0 else 0.0
        angle = base + flip + math.radians(a.front_deg)
        if flip:
            warnings.append("auto front flipped: longest wall faces -Y; verify against the street")

    transformed = [[rotate(p, angle) for p in ring] for ring in raw]
    xs = [p[0] for ring in transformed for p in ring]
    ys = [p[1] for ring in transformed for p in ring]
    cx, ymin = (min(xs) + max(xs)) / 2, min(ys)
    volumes = []
    for item, ring in zip(meta, transformed):
        footprint = [[round(p[0] - cx, 3), round(p[1] - ymin, 3)] for p in ring]
        volumes.append({"id": f"dong_{item['name']}", "footprint": footprint,
                        "height": round(item["height"], 3), "z0": 0.0, "wall": "wall", "roof": "roof",
                        "source_dong": item["name"], "height_source": item["height_source"]})
    try:
        source_name = os.path.relpath(os.path.abspath(a.xrx), proj.ROOT).replace(os.sep, "/")
    except ValueError:
        source_name = os.path.abspath(a.xrx)
    spec = {
        "source": {"type": "xrx_metadata", "file": source_name, "sha256": sha256(a.xrx),
                   "complex": {"id": data.get("id"), "name": data.get("name")},
                   "dongs": [v["source_dong"] for v in volumes], "scale": "xrx scene units (m)",
                   "front_deg": a.front_deg, "auto_rotate": not a.no_rotate},
        "review": {"required": True, "preview": a.preview.replace(os.sep, "/"),
                   "note": "Mass evidence only. Verify front, tiers and hidden walls against photos."},
        "volumes": volumes, "openings": [], "attachments": [],
    }
    try:
        K.validate_volume_spec(spec)
    except ValueError as ex:
        raise SystemExit(f"invalid mass spec: {ex}")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, a.out)
    GS.draw_preview(a.preview, volumes, warnings, title="Naver VR metadata mass - verify front and tiers")
    report = {"status": "OK", "complex": spec["source"]["complex"], "volume_count": len(volumes),
              "warnings": warnings, "out": a.out, "preview": a.preview,
              "volumes": [{"id": v["id"], "height": v["height"], "area_m2": round(abs(GS.ring_area(v["footprint"])), 2),
                           "points": len(v["footprint"]), "height_source": v["height_source"]} for v in volumes]}
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    with open(a.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False) if a.json else
          f"[xrx] {len(volumes)} dong(s) -> {a.out}  preview {a.preview}  warnings {len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
