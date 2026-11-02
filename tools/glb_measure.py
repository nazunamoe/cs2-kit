# -*- coding: utf-8 -*-
"""
glb_measure.py - measure a building from a scanned/VR .glb (size reference ONLY; the model is never copied into the asset).

    python tools/glb_measure.py scan.glb --list                      list meshes (name, size, tris) -> pick the building
    python tools/glb_measure.py scan.glb --mesh Building,Roof        measure only meshes whose name contains one of these
    python tools/glb_measure.py scan.glb --mesh-index 3,4            ... or by index from --list
    python tools/glb_measure.py scan.glb --box=-30,30,-20,20         crop (metres, glTF x / -z plane, after --scale) to drop neighbours
    options: --scale 1.0 (units -> metres), --up y|z (default y = glTF standard), --front-deg 0 (rotate result), --out previews/glb

Prints (and writes previews/glb/glb_measure.json):
    width/depth/height of the main block (minimum-area rotated rectangle, so a tilted scan is fine), yaw of the building,
    main roof height vs. total height (rooftop equipment), setbacks, floor pitch + floor count candidates, window-bay pitch.
Pictures: previews/glb/top.png, elev_a.png .. elev_d.png (point density, to compare with photos).
Not supported: Draco / meshopt compressed files (open in Blender, export again as uncompressed .glb), non-triangle modes.
"""
import argparse
import base64
import json
import math
import os
import struct
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from proj import ROOT, KIT, NAME  # noqa: E402,F401  (project folder; chdir done)
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def p(s):
    sys.stdout.write(str(s).encode("ascii", "backslashreplace").decode("ascii") + "\n")


# ---------------------------------------------------------------- glTF reading
def load_gltf(path):
    with open(path, "rb") as f:
        data = f.read()
    binchunk = None
    if data[:4] == b"glTF":
        _, _, total = struct.unpack("<III", data[:12])
        off = 12
        js = None
        while off < min(total, len(data)):
            ln, typ = struct.unpack("<II", data[off:off + 8])
            body = data[off + 8:off + 8 + ln]
            if typ == 0x4E4F534A:
                js = json.loads(body.decode("utf-8"))
            elif typ == 0x004E4942 and binchunk is None:
                binchunk = body
            off += 8 + ln
        if js is None:
            raise SystemExit("no JSON chunk - not a valid .glb")
    else:
        js = json.loads(data.decode("utf-8"))
    bad = [e for e in js.get("extensionsRequired", []) if e in ("KHR_draco_mesh_compression", "EXT_meshopt_compression")]
    if bad:
        raise SystemExit(f"compressed file ({', '.join(bad)}). Open it in Blender (File > Import > glTF) and export an uncompressed .glb, then retry.")
    base = os.path.dirname(os.path.abspath(path))
    bufs = []
    for b in js.get("buffers", []):
        uri = b.get("uri")
        if uri is None:
            bufs.append(binchunk)
        elif uri.startswith("data:"):
            bufs.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            with open(os.path.join(base, uri), "rb") as f:
                bufs.append(f.read())
    return js, bufs


def accessor(js, bufs, idx):
    a = js["accessors"][idx]
    n, k = a["count"], NC[a["type"]]
    dt = np.dtype(CT[a["componentType"]]).newbyteorder("<")
    if "bufferView" not in a:
        return np.zeros((n, k), dt)
    bv = js["bufferViews"][a["bufferView"]]
    buf = bufs[bv["buffer"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride") or dt.itemsize * k
    raw = np.frombuffer(buf, np.uint8, count=(n - 1) * stride + dt.itemsize * k, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(n, dt.itemsize * k), strides=(stride, 1))
    return np.ascontiguousarray(rows).view(dt).reshape(n, k)


def node_matrix(nd):
    if "matrix" in nd:
        return np.array(nd["matrix"], np.float64).reshape(4, 4).T
    t = np.array(nd.get("translation", [0, 0, 0]), np.float64)
    q = np.array(nd.get("rotation", [0, 0, 0, 1]), np.float64)
    s = np.array(nd.get("scale", [1, 1, 1]), np.float64)
    x, y, z, w = q
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R * s[None, :]
    M[:3, 3] = t
    return M


def collect(js, bufs):
    """-> list of dict(name, V (N,3) glTF coords world, F (M,3))"""
    out = []
    scenes = js.get("scenes") or [{"nodes": list(range(len(js.get("nodes", []))))}]
    roots = scenes[js.get("scene", 0)].get("nodes", [])

    def walk(i, parent):
        nd = js["nodes"][i]
        M = parent @ node_matrix(nd)
        if "mesh" in nd:
            mesh = js["meshes"][nd["mesh"]]
            for pi, prim in enumerate(mesh.get("primitives", [])):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                    continue
                V = accessor(js, bufs, prim["attributes"]["POSITION"]).astype(np.float64)
                F = accessor(js, bufs, prim["indices"]).astype(np.int64).reshape(-1, 3) if "indices" in prim \
                    else np.arange(len(V)).reshape(-1, 3)
                V = V @ M[:3, :3].T + M[:3, 3]
                nm = nd.get("name") or mesh.get("name") or f"node{i}"
                out.append({"name": nm + (f".{pi}" if len(mesh["primitives"]) > 1 else ""), "V": V, "F": F})
        for c in nd.get("children", []):
            walk(c, M)

    for r in roots:
        walk(r, np.eye(4))
    return out


# ---------------------------------------------------------------- geometry helpers
def to_zup(V, up):
    if up == "y":                    # glTF: x right, y up, z toward viewer -> x, -z, y
        return np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1)
    return V.copy()


def sample_surface(V, F, n_pts, rng):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    cr = np.cross(b - a, c - a)
    area = np.linalg.norm(cr, axis=1) / 2
    tot = area.sum()
    if tot <= 0:
        return V, np.zeros((0, 3)), 0.0
    k = rng.choice(len(F), size=n_pts, p=area / tot)
    r1, r2 = rng.random(n_pts), rng.random(n_pts)
    s = np.sqrt(r1)
    P = a[k] * (1 - s)[:, None] + b[k] * (s * (1 - r2))[:, None] + c[k] * (s * r2)[:, None]
    N = cr[k] / (np.linalg.norm(cr[k], axis=1)[:, None] + 1e-12)
    return P, N, tot


def min_area_rect(xy):
    """Rotation angle (deg, 0..90) minimising the bounding-box area of xy points."""
    best = (1e18, 0.0)
    for ang in np.arange(0, 90, 0.5):
        t = math.radians(ang)
        c, s = math.cos(t), math.sin(t)
        u = xy[:, 0] * c + xy[:, 1] * s
        v = -xy[:, 0] * s + xy[:, 1] * c
        ar = (np.percentile(u, 99.8) - np.percentile(u, 0.2)) * (np.percentile(v, 99.8) - np.percentile(v, 0.2))
        if ar < best[0]:
            best = (ar, float(ang))
    return best[1]


def period(profile, per_m, lo_m, hi_m):
    k = max(3, int(per_m))
    if len(profile) < 4 * k:
        return None, 0.0
    x = profile - np.convolve(profile, np.ones(k) / k, mode="same")
    x = x - x.mean()
    if np.std(x) < 1e-9:
        return None, 0.0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac /= ac[0]
    lo, hi = int(lo_m * per_m), min(len(ac) - 1, int(hi_m * per_m))
    if hi <= lo + 2:
        return None, 0.0
    seg = ac[lo:hi]
    k = int(np.argmax(seg))
    st = float(seg[k])
    for j in range(1, len(seg) - 1):
        if seg[j] >= seg[j - 1] and seg[j] >= seg[j + 1] and seg[j] > 0.8 * st:
            k = j
            break
    # refine with parabola
    kk = lo + k
    if 0 < kk < len(ac) - 1:
        y0, y1, y2 = ac[kk - 1], ac[kk], ac[kk + 1]
        d = (y0 - 2 * y1 + y2)
        if d != 0:
            kk = kk + 0.5 * (y0 - y2) / d
    return kk / per_m, st


def save_density(path, a, b, extent, title, size=700):
    """2-D histogram of points (a horizontal, b vertical) -> png."""
    from PIL import Image, ImageDraw
    (a0, a1), (b0, b1) = extent
    sc = min(size / max(a1 - a0, 1e-6), size / max(b1 - b0, 1e-6))
    w, h = max(1, int((a1 - a0) * sc)), max(1, int((b1 - b0) * sc))
    H, _, _ = np.histogram2d(a, b, bins=[w, h], range=[[a0, a1], [b0, b1]])
    H = np.log1p(H.T[::-1])
    H = (255 - 255 * H / max(H.max(), 1e-9)).astype(np.uint8)
    im = Image.fromarray(H).convert("RGB")
    ImageDraw.Draw(im).text((4, 4), title, fill=(200, 0, 0))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--mesh", default="", help="comma list of name parts")
    ap.add_argument("--mesh-index", default="", help="comma list of indexes from --list")
    ap.add_argument("--box", default="", help="x0,x1,y0,y1 crop in metres (use --box=-30,30,-20,20)")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--up", choices=["y", "z"], default="y")
    ap.add_argument("--front-deg", type=float, default=0.0, help="extra rotation of the result (deg, counter-clockwise from above)")
    ap.add_argument("--samples", type=int, default=400000)
    ap.add_argument("--out", default=os.path.join(ROOT, "previews", "glb"))
    a = ap.parse_args()

    js, bufs = load_gltf(a.file)
    meshes = collect(js, bufs)
    if not meshes:
        raise SystemExit("no triangle meshes found")
    for m in meshes:
        m["V"] = to_zup(m["V"], a.up) * a.scale
    if a.list:
        for i, m in enumerate(meshes):
            lo, hi = m["V"].min(0), m["V"].max(0)
            p(f"[{i:2d}] {m['name'][:40]:40s} size {hi[0]-lo[0]:7.1f} x {hi[1]-lo[1]:7.1f} x {hi[2]-lo[2]:6.1f} m  "
              f"z {lo[2]:6.1f}..{hi[2]:6.1f}  tris {len(m['F'])}")
        allv = np.concatenate([m["V"] for m in meshes])
        sz = allv.max(0) - allv.min(0)
        p(f"total {sz[0]:.1f} x {sz[1]:.1f} x {sz[2]:.1f} m  (if this looks 100x or 0.01x too big/small, use --scale)")
        return
    sel = list(range(len(meshes)))
    if a.mesh:
        keys = [k.strip().lower() for k in a.mesh.split(",") if k.strip()]
        sel = [i for i in sel if any(k in meshes[i]["name"].lower() for k in keys)]
    if a.mesh_index:
        sel = [int(t) for t in a.mesh_index.split(",")]
    if not sel:
        raise SystemExit("no mesh matches --mesh / --mesh-index (see --list)")

    rng = np.random.default_rng(1)
    Vs, Fs, off = [], [], 0
    for i in sel:
        Vs.append(meshes[i]["V"]); Fs.append(meshes[i]["F"] + off); off += len(meshes[i]["V"])
    V, F = np.concatenate(Vs), np.concatenate(Fs)
    if a.box:
        x0, x1, y0, y1 = [float(t) for t in a.box.split(",")]
        c = V[F].mean(1)
        keep = (c[:, 0] >= x0) & (c[:, 0] <= x1) & (c[:, 1] >= y0) & (c[:, 1] <= y1)
        F = F[keep]
        if not len(F):
            raise SystemExit("--box removed everything")
    P, N, area = sample_surface(V, F, a.samples, rng)
    if not len(P):
        raise SystemExit("zero surface area")

    # ground = low percentile of points; keep it robust against a few stray vertices
    z_ground = float(np.percentile(P[:, 2], 0.3))
    P[:, 2] -= z_ground
    H_total = float(np.percentile(P[:, 2], 99.95))
    if H_total < 6.0:
        raise SystemExit(f"selection is only {H_total:.1f} m tall - probably terrain/road, or --scale is wrong. "
                         "Use --list, then --mesh / --mesh-index / --box to pick the building.")

    # footprint rectangle from points above 1 m (ignore terrain), rotated frame u (width) / v (depth)
    mid = P[P[:, 2] > 1.0]
    ang = min_area_rect(mid[:, :2]) + a.front_deg
    t = math.radians(ang)
    c, s = math.cos(t), math.sin(t)
    U = P[:, 0] * c + P[:, 1] * s
    Vv = -P[:, 0] * s + P[:, 1] * c
    Z = P[:, 2]

    # main block = biggest footprint slice. footprint area per height (0.5 m cells)
    # bounding-extent area per 1 m slice (percentile extents, so walls-only scans and hollow shells give the same answer)
    zb = np.arange(0, H_total + 1, 1.0)
    areas = []
    for z in zb[:-1]:
        m = (Z >= z) & (Z < z + 1.0)
        if m.sum() < 50:
            areas.append(0.0); continue
        areas.append(float((np.percentile(U[m], 99.5) - np.percentile(U[m], 0.5)) *
                           (np.percentile(Vv[m], 99.5) - np.percentile(Vv[m], 0.5))))
    areas = np.array(areas)
    if len(areas) >= 3:                                   # median of 3 -> ignore single-slice noise
        areas = np.array([np.median(areas[max(0, i - 1):i + 2]) for i in range(len(areas))])
    amax = areas.max() if len(areas) else 0
    full = np.nonzero(areas >= 0.7 * amax)[0]
    top_slice = float(zb[full.max()] + 1.0) if len(full) else H_total
    # exact roof height = the largest horizontal surface near the end of the full-size block
    hs = np.abs(N[:, 2]) > 0.8
    zr = Z[hs & (Z > top_slice - 1.5) & (Z < top_slice + 1.0)]
    if len(zr) > 100:
        hh, ed = np.histogram(zr, bins=int(2.5 / 0.05), range=(top_slice - 1.5, top_slice + 1.0))
        roof_z = float(ed[int(np.argmax(hh))] + 0.025)
    else:
        roof_z = top_slice
    setbacks = []
    for i in range(1, len(areas)):
        if areas[i - 1] > 0 and abs(areas[i] - areas[i - 1]) / areas[i - 1] > 0.18 and zb[i] > 2:
            setbacks.append((float(zb[i]), float(areas[i - 1]), float(areas[i])))

    # block extents measured on the main body (between 20% and 80% of main roof height)
    body = (Z > 0.2 * roof_z) & (Z < 0.8 * roof_z)
    uu, vv = U[body], Vv[body]
    W = float(np.percentile(uu, 99.7) - np.percentile(uu, 0.3))
    D = float(np.percentile(vv, 99.7) - np.percentile(vv, 0.3))
    u0, v0 = float(np.percentile(uu, 0.3)), float(np.percentile(vv, 0.3))
    long_is_u = W >= D
    if not long_is_u:
        # make the long side the generator's X (width)
        U, Vv = Vv.copy(), -U.copy()
        W, D = D, W
        u0, v0 = float(np.percentile(U[body], 0.3)), float(np.percentile(Vv[body], 0.3))
        ang = (ang + 90) % 360

    # floor pitch: area of horizontal faces per height (slabs, sills, balconies) and vertex density, autocorrelation
    res = 0.1
    nb = int(roof_z / res)
    horiz = np.abs(N[:, 2]) > 0.8
    h1, _ = np.histogram(Z[horiz & (Z < roof_z)], bins=nb, range=(0, nb * res))
    wall = np.abs(N[:, 2]) < 0.3
    h2, _ = np.histogram(Z[wall & (Z < roof_z)], bins=nb, range=(0, nb * res))
    fp1, st1 = period(h1.astype(float), 1 / res, 1.2, 6.5)
    fp2, st2 = period(h2.astype(float), 1 / res, 1.2, 6.5)
    cands = [(st, f) for st, f in ((st1, fp1), (st2, fp2)) if f]
    floor_pitch = max(cands)[1] if cands else None
    floor_strength = max(cands)[0] if cands else 0.0

    # bay pitch along the width on the wall faces of the main body
    # only wall points that stick out of / sit behind the main wall plane (window reveals, ribs, balcony edges)
    midz = (Z > 0.25 * roof_z) & (Z < 0.9 * roof_z) & wall
    w_bins = max(10, int(W / 0.1))
    h3 = np.zeros(w_bins)
    for v_edge in (v0, v0 + D):
        near = midz & (np.abs(Vv - v_edge) < 1.0)
        if near.sum() < 200:
            continue
        hv, ev = np.histogram(Vv[near], bins=40, range=(v_edge - 1.0, v_edge + 1.0))
        plane = ev[int(np.argmax(hv))] + 0.025
        feat = near & (np.abs(Vv - plane) > 0.05)
        hh, _ = np.histogram(U[feat] - u0, bins=w_bins, range=(0, w_bins * 0.1))
        h3 += hh
    bay, bst = period(h3, 10.0, 1.5, 12.0) if h3.sum() > 100 else (None, 0.0)

    j = {
        "file": os.path.basename(a.file), "meshes_used": [meshes[i]["name"] for i in sel],
        "width_m": round(W, 2), "depth_m": round(D, 2), "total_height_m": round(H_total, 2),
        "main_roof_height_m": round(roof_z, 1), "rooftop_above_main_m": round(max(0.0, H_total - roof_z), 1),
        "yaw_deg_ccw": round(ang % 360, 1), "surface_area_m2": round(area, 0),
        "setbacks": [{"z": z, "area_before": round(x0_), "area_after": round(x1_)} for z, x0_, x1_ in setbacks[:8]],
        "floor_pitch_m": round(floor_pitch, 2) if floor_pitch else None, "floor_pitch_strength": round(floor_strength, 2),
        "floors_estimate": round(roof_z / floor_pitch) if floor_pitch else None,
        "bay_pitch_m": round(bay, 2) if bay else None, "bay_strength": round(bst, 2),
        "bays_estimate": round(W / bay) if bay else None,
    }
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "glb_measure.json"), "w", encoding="utf-8") as f:
        json.dump(j, f, indent=2)

    # pictures (width axis horizontal; a/b = long sides, c/d = short sides)
    ext_u, ext_v = (u0 - 2, u0 + W + 2), (v0 - 2, v0 + D + 2)
    save_density(os.path.join(a.out, "top.png"), U, Vv, (ext_u, ext_v), "top view (point density)")
    save_density(os.path.join(a.out, "elev_a.png"), U, Z, (ext_u, (0, H_total + 1)), "elevation: seen from -v side (long wall)")
    save_density(os.path.join(a.out, "elev_b.png"), -U, Z, ((-ext_u[1], -ext_u[0]), (0, H_total + 1)), "elevation: seen from +v side")
    save_density(os.path.join(a.out, "elev_c.png"), Vv, Z, (ext_v, (0, H_total + 1)), "elevation: short wall")
    save_density(os.path.join(a.out, "elev_d.png"), -Vv, Z, ((-ext_v[1], -ext_v[0]), (0, H_total + 1)), "elevation: other short wall")

    p("[glb_measure] used meshes: " + ", ".join(j["meshes_used"][:6]) + (" ..." if len(j["meshes_used"]) > 6 else ""))
    p(f"  footprint (long side = width): width {W:.1f} m x depth {D:.1f} m, building rotated {ang % 360:.1f} deg in the scan")
    p(f"  height: main roof {roof_z:.1f} m, top of rooftop equipment {H_total:.1f} m (+{max(0.0, H_total - roof_z):.1f})")
    if W > 250 or roof_z < 0.3 * H_total:
        p("  WARNING: numbers look wrong - the selection probably contains terrain or neighbouring buildings. "
          "Run --list, then use --mesh / --mesh-index / --box.")
    if setbacks:
        p("  footprint area changes at z(m): " + ", ".join(f"{z:.0f} ({x0_:.0f}->{x1_:.0f} m2)" for z, x0_, x1_ in setbacks[:6]))
    if floor_pitch:
        weak = "  (WEAK pattern - check by eye)" if floor_strength < 0.15 else ""
        p(f"  floor pitch {floor_pitch:.2f} m -> about {roof_z / floor_pitch:.1f} floors{weak}")
    else:
        p("  floor pitch: could not measure")
    if bay:
        p(f"  window bay pitch {bay:.2f} m -> about {W / bay:.1f} bays across the width" + ("  (weak)" if bst < 0.15 else ""))
    p(f"  TASK.md lines: size_m: width {W:.0f}, depth {D:.0f}, height {roof_z:.0f}"
      + (f" | floors: {round(roof_z / floor_pitch)}" if floor_pitch else ""))
    shown = os.path.relpath(a.out, ROOT) if os.path.abspath(a.out).startswith(ROOT) else a.out
    p(f"  pictures + json: {shown}  (glb_measure.json, top.png, elev_a..d.png)")
    p("  NOTE: size reference only - do not copy the scan's geometry or textures into the asset.")


if __name__ == "__main__":
    main()
