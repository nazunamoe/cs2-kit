# -*- coding: utf-8 -*-
"""
photo_plane_map.py - map the photo planes of a capture onto the model walls they cover.

A capture (Naver VR, 360 tour, ...) knows its own wall planes in scene metres, and the
model (generic_spec*.json) knows its own wall ring in model metres.  Neither knows the
other, so every measured photo has to be registered to the model before a window column
measured on the photo can be placed on the model wall.

    python tools/photo_plane_map.py --meta photos/ref101/101_meta.json \
        --mass generic_spec_xrx.json [--refs photo_refs_stitched2.json] \
        [--volume dong_101] [--min-len 6] [--min-px-per-m 15] \
        [--no-cache] [--out work/plane_to_edge.json] [--json]

How it works
    1. the capture footprint (meta["footprint_m"]) is registered onto the model ring with a
       rigid transform (rotation + translation) found by a Chamfer search; the residual is
       reported, because a large residual means the two outlines disagree.
    2. every exact plane of the capture (naver_vr.reference_walls_of) is projected onto the
       model ring: which model edge it covers, at which metre offset, and whether the photo
       runs with or against the edge direction (a mirrored photo flips the window order).
    3. the result is written as JSON and as a table:
       plane 4 (grp 0, 9.54 m) -> model edge 0, photo left 9.55 m, right 0.01 m, 40 px/m

Output (work/plane_to_edge.json):
    {"registration": {...}, "model_edges": [...], "planes": [...], "warnings": [...]}

Use it with facade_read.py output (columns in metres) to place measured columns, and with
tools/qa/plane_compare.py to compare the model with the photo plane by plane.
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proj import ROOT, KIT, NAME  # noqa: E402,F401  (project folder; chdir done)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def p(s=""):
    sys.stdout.write(str(s).encode("ascii", "backslashreplace").decode("ascii") + "\n")


# ---------------------------------------------------------------- model ring
def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _vertex_angle(a, b, c):
    """Interior angle at b in degrees (0 = spike, 180 = straight through)."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def simplify_ring(foot, min_len=2.0, max_angle=25.0):
    """Drop vertices that only create sliver walls (they show as LOD cracks).

    A short edge alone is not a sliver: a 1.5 m return wall on a 90 degree corner is real.
    A vertex is dropped only when an adjacent edge is shorter than ``min_len`` *and* the
    turn is sharp (``max_angle`` degrees or less from a spike/straight-through). This keeps
    genuine short wall segments and removes noise spikes.
    """
    pts = [tuple(float(q) for q in v) for v in foot]
    changed = True
    while changed and len(pts) > 4:
        changed = False
        n = len(pts)
        for i in range(n):
            a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
            short = _dist(a, b) < min_len or _dist(b, c) < min_len
            if not short:
                continue
            turn = _vertex_angle(a, b, c)
            sharp = min(turn, 180.0 - turn) <= max_angle
            if sharp:
                pts.pop(i)
                changed = True
                break
    return pts


def pick_volume(spec, want=None):
    vols = [v for v in spec.get("volumes", []) if v.get("footprint")]
    if not vols:
        raise SystemExit("no volume with a footprint in the mass file")
    if want:
        for v in vols:
            if v.get("id") == want:
                return v
        raise SystemExit("volume '%s' not found (%s)" % (want, ", ".join(str(v.get("id")) for v in vols)))
    if len(vols) == 1:
        return vols[0]
    best = max(vols, key=lambda v: len(v["footprint"]))
    return best


def polygon_area(pts):
    a = np.asarray(pts, dtype=float)
    x, y = a[:, 0], a[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


# ---------------------------------------------------------------- registration
def sample_polygon(poly, step=0.5):
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(round(L / step)))
        for j in range(k):
            f = j / k
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return np.array(out, dtype=float)


def chamfer(A, B):
    """Mean distance from every point of A to its nearest point in B.

    Chunked vectorized brute force. A k-d tree adds complexity without a real win at the
    few-hundred-point sizes the registration uses (the per-chunk distance matrix is
    memory-bounded and already fast); scipy's cKDTree is used only when it is already
    imported by the caller.
    """
    if len(A) == 0 or len(B) == 0:
        return float("inf")
    tot = 0.0
    for i in range(0, len(A), 256):
        chunk = A[i:i + 256]
        d = np.sqrt(((chunk[:, None, :] - B[None, :, :]) ** 2).sum(2))
        tot += float(d.min(axis=1).sum())
    return tot / len(A)


def rot(theta):
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


def register(cap_pts, ring_pts, coarse_step=0.5, fine_step=0.05, search=1.5,
             coarse_deg=3.0, workers=0):
    """Rigid transform (rotation + translation) that maps the capture outline onto the model ring.

    A coarse rotation grid (3 deg) locks the basin, then one narrow rotation sweep (0.25 deg)
    and one two-stage translation grid (0.5 m then fine_step) refine it. This is ~200 chamfer
    calls instead of ~2000 for the original 0.5 deg full sweep + 61x61 translation grid, and
    the reported residual tells whether the two outlines even agree.

    ``workers`` > 1 evaluates the coarse rotation grid in threads. The winner is chosen by
    score and then by ascending angle, so the result does not depend on completion order.
    """
    S_cap = sample_polygon(cap_pts, coarse_step)
    S_model = sample_polygon(ring_pts, coarse_step)
    cap_center = cap_pts.mean(0) if len(cap_pts) else np.zeros(2)

    # coarse rotation sweep
    degs = list(np.arange(0.0, 360.0, coarse_deg))
    n_workers = min(8, len(degs), workers or (os.cpu_count() or 1))
    if n_workers > 1:
        from concurrent.futures import ThreadPoolExecutor

        def coarse(deg):
            th = math.radians(float(deg))
            R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
            t = ring_pts.mean(0) - R @ cap_center
            return chamfer((S_cap @ R.T) + t, S_model)

        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            values = list(ex.map(coarse, degs))
        idx = min(range(len(degs)), key=lambda k: (values[k], k))
        d, deg = values[idx], float(degs[idx])
        R = rot(math.radians(deg))
        t = ring_pts.mean(0) - R @ cap_center
    else:
        best = None
        for deg in degs:
            th = math.radians(float(deg))
            R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
            t = ring_pts.mean(0) - R @ cap_center
            d = chamfer((S_cap @ R.T) + t, S_model)
            if best is None or d < best[0]:
                best = (d, float(deg), R, t)
        d, deg, R, t = best
    # one narrow rotation refinement
    for d2 in np.arange(deg - coarse_deg, deg + coarse_deg + 1e-9, 0.25):
        th = math.radians(float(d2))
        R2 = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        t2 = ring_pts.mean(0) - R2 @ cap_center
        dd = chamfer((S_cap @ R2.T) + t2, S_model)
        if dd < d:
            d, deg, R, t = dd, float(d2), R2, t2
    # two-stage translation grid
    for grid_step, span in ((0.5, search), (fine_step, 0.55)):
        bt = (d, t)
        for dx in np.arange(-span, span + 1e-9, grid_step):
            for dy in np.arange(-span, span + 1e-9, grid_step):
                tt = t + np.array([dx, dy])
                dd = chamfer((S_cap @ R.T) + tt, S_model)
                if dd < bt[0]:
                    bt = (dd, tt)
        d, t = bt
    moved = (S_cap @ R.T) + t
    res = np.sqrt(((S_model[:, None, :] - moved[None, :, :]) ** 2).sum(2)).min(axis=1)
    info = {"rot_deg": round(deg % 360.0, 3), "translation": [round(float(t[0]), 4), round(float(t[1]), 4)],
            "chamfer_m": round(float(d), 4), "residual_mean_m": round(float(res.mean()), 4),
            "residual_max_m": round(float(res.max()), 4)}
    return R, t, info


CACHE_VERSION = 1
CACHE_LIMIT = 16


def _cache_key(cap_pts, ring_pts, params):
    """Digest of both outlines and the search parameters; a changed input is a cache miss."""
    h = hashlib.sha256()
    h.update(("v%d|%s" % (CACHE_VERSION, json.dumps(params, sort_keys=True))).encode("utf-8"))
    for arr in (cap_pts, ring_pts):
        a = np.ascontiguousarray(arr, dtype="<f8")
        h.update(("%s|" % (a.shape,)).encode("ascii"))
        h.update(a.tobytes())
    return h.hexdigest()


def register_cached(cap_pts, ring_pts, cache_path, use_cache=True, workers=0, **kw):
    """register() with a deterministic cache; the result depends only on the key inputs.

    Returns (R, t, info, cache_hit). A cache read/write failure falls back to register(),
    so a stale or corrupt file can never change the mapping, only its speed.
    """
    if not use_cache or not cache_path:
        return register(cap_pts, ring_pts, workers=workers, **kw) + (False,)

    key = _cache_key(cap_pts, ring_pts, kw)
    entries = {}
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries") if isinstance(data, dict) else None
            if not isinstance(entries, dict):
                entries = {}
        except Exception:  # noqa: BLE001 - a broken cache is just a miss
            entries = {}
    hit = entries.get(key)
    if isinstance(hit, dict):
        try:
            R = np.array(hit["R"], dtype=float)
            t = np.array(hit["t"], dtype=float)
            if R.shape == (2, 2) and t.shape == (2,):
                return R, t, dict(hit["info"]), True
        except Exception:  # noqa: BLE001
            pass

    R, t, info = register(cap_pts, ring_pts, workers=workers, **kw)
    entries[key] = {"R": R.tolist(), "t": t.tolist(), "info": info}
    for old in list(entries)[:-CACHE_LIMIT]:
        entries.pop(old, None)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        tmp = cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"_schema": "photo-plane-registration-cache-v1", "entries": entries},
                      f, ensure_ascii=False, indent=0)
        os.replace(tmp, cache_path)
    except Exception:  # noqa: BLE001 - never fail the mapping because of the cache
        pass
    return R, t, info, False


# ---------------------------------------------------------------- planes
def capture_planes(meta):
    """Exact planes of the capture (same code the Naver VR refs use)."""
    sys.path.insert(0, os.path.join(KIT, "capture"))
    try:
        import naver_vr as NV
    except Exception as ex:
        raise SystemExit("capture/naver_vr.py is needed for the plane list (%s)" % ex)
    return NV.reference_walls_of(meta.get("footprint_m") or [], meta.get("walls") or [],
                                  min_len=1.0, angle_tol=2.0, offset_tol=0.05)


def photo_left_is_p0(meta, plane, shot):
    """Which plane endpoint appears on the left in the photo (that fixes the mirror direction)."""
    sys.path.insert(0, os.path.join(KIT, "capture"))
    import naver_vr as NV
    g, roof = meta["ground_m"], meta["roof_m"]
    box, dpr = meta["canvas_css"], meta["dpr"]
    y = g + (roof - g) * 0.5
    pa = NV.project_px(shot, [plane["p0"][0], y, plane["p0"][1]], box, dpr, shot["img"])
    pb = NV.project_px(shot, [plane["p1"][0], y, plane["p1"][1]], box, dpr, shot["img"])
    if not pa or not pb:
        return None
    return pa[0] < pb[0]


def edge_coverage(ring, m0, m1, max_perp=1.5, min_overlap=0.5):
    """Best model edge for the (already transformed) plane segment."""
    best = None
    n = len(ring)
    for k in range(n):
        ra, rb = ring[k], ring[(k + 1) % n]
        d = rb - ra
        Ld = float(np.linalg.norm(d))
        if Ld < 1e-6:
            continue
        u = d / Ld
        s0 = float(np.dot(m0 - ra, u))
        s1 = float(np.dot(m1 - ra, u))
        lo, hi = min(s0, s1), max(s0, s1)
        perp = max(abs((m0[0] - ra[0]) * u[1] - (m0[1] - ra[1]) * u[0]),
                   abs((m1[0] - ra[0]) * u[1] - (m1[1] - ra[1]) * u[0]))
        overlap = min(hi, Ld) - max(lo, 0.0)
        if perp <= max_perp and overlap >= min_overlap:
            score = (round(perp, 3), -round(overlap, 3))
            if best is None or score < best[0]:
                best = (score, k, s0, s1, Ld, perp, overlap)
    return best


def refs_px_per_m(refs_path):
    """px per metre of every plane that has a ref entry (image width / real width)."""
    out = {}
    if not refs_path or not os.path.isfile(refs_path):
        return out
    with open(refs_path, encoding="utf-8-sig") as f:
        refs = json.load(f)
    for e in refs.get("facades", []):
        plane = e.get("source_plane_i")
        if plane is None:
            continue
        path = e.get("file")
        if not path or not os.path.isfile(path):
            continue
        try:
            from PIL import Image
            with Image.open(path) as im:
                w = im.size[0]
        except Exception:
            continue
        size = e.get("size_m") or []
        if not size or not size[0]:
            continue
        ppm = w / float(size[0])
        prev = out.get(plane)
        if prev is None or ppm > prev:
            out[plane] = ppm
    return out


def capture_px_per_m(meta, plane, shot):
    """px per metre of the plane inside the capture photo (projected width / real width).

    This is what limits measurement: a 35 m wall shot at 1366 px is only ~39 px/m, and a
    facade that fills the frame with its whole width gives far less than that.
    """
    sys.path.insert(0, os.path.join(KIT, "capture"))
    import naver_vr as NV
    g, roof = meta["ground_m"], meta["roof_m"]
    box, dpr = meta["canvas_css"], meta["dpr"]
    W_, H_ = shot["img"]
    mx, my = W_ * 0.02, H_ * 0.02
    N = 240
    ok = []
    for k in range(N + 1):
        y = g + (roof - g) * k / N
        a = NV.project_px(shot, [plane["p0"][0], y, plane["p0"][1]], box, dpr, shot["img"])
        b = NV.project_px(shot, [plane["p1"][0], y, plane["p1"][1]], box, dpr, shot["img"])
        ok.append(bool(a and b and all(mx <= t[0] <= W_ - mx and my <= t[1] <= H_ - my for t in (a, b))))
    best, run0 = (0, 0), None
    for k, good in enumerate(ok + [False]):
        if good and run0 is None:
            run0 = k
        if not good and run0 is not None:
            if k - 1 - run0 > best[1] - best[0]:
                best = (run0, k - 1)
            run0 = None
    y0 = g + (roof - g) * best[0] / N
    y1 = g + (roof - g) * best[1] / N
    P = lambda x_, z_, y_: NV.project_px(shot, [x_, y_, z_], box, dpr, shot["img"])
    pa0, pa1 = P(*plane["p0"], y1), P(*plane["p0"], y0)
    pb0, pb1 = P(*plane["p1"], y1), P(*plane["p1"], y0)
    if not (pa0 and pa1 and pb0 and pb1):
        return None, None
    wpx = ((pa0[0] - pb0[0]) + (pa1[0] - pb1[0])) / 2
    return abs(wpx) / max(plane["length_m"], 1e-6), (y1 - y0)



# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--meta", required=True, help="capture meta json (photos/.../<dong>_meta.json)")
    ap.add_argument("--mass", help="model mass json (generic_spec*.json); default: the biggest one in the project")
    ap.add_argument("--volume", help="volume id inside the mass file")
    ap.add_argument("--refs", help="photo_refs json, only used to read the px/m of each plane")
    ap.add_argument("--min-len", type=float, default=6.0, help="ignore planes shorter than this (m)")
    ap.add_argument("--min-px-per-m", type=float, default=20.0,
                    help="warn below this capture resolution (window widths need ~20, louver slats ~30)")
    ap.add_argument("--max-perp", type=float, default=1.5, help="max distance of the plane from the model edge (m)")
    ap.add_argument("--out", default="work/plane_to_edge.json")
    ap.add_argument("--cache", default="work/registration_cache.json",
                    help="registration cache inside the project (empty string disables it)")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore and do not update the registration cache")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when a plane is below --min-px-per-m (a capture that cannot be measured)")
    ap.add_argument("--workers", type=int, default=0,
                    help="threads for the coarse registration sweep (0=auto, 1=serial)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.meta):
        raise SystemExit("no such meta file: %s" % a.meta)
    with open(a.meta, encoding="utf-8-sig") as f:
        meta = json.load(f)

    mass_path = a.mass
    if not mass_path:
        cands = sorted(f for f in os.listdir(ROOT) if f.startswith("generic_spec") and f.endswith(".json"))
        if not cands:
            raise SystemExit("no generic_spec*.json in %s - pass --mass" % ROOT)
        mass_path = os.path.join(ROOT, cands[0])
    with open(mass_path, encoding="utf-8-sig") as f:
        spec = json.load(f)
    vol = pick_volume(spec, a.volume)
    ring = simplify_ring(vol["footprint"], 2.0)
    ring_pts = np.array(ring, dtype=float)

    cap_pts = np.array(meta.get("footprint_m") or [], dtype=float)
    if len(cap_pts) < 4:
        raise SystemExit("capture meta has no footprint_m")

    R, t, reg, cache_hit = register_cached(cap_pts, ring_pts, None if a.no_cache else a.cache,
                                           workers=max(0, a.workers))
    warnings = []
    if reg["residual_mean_m"] > 0.5:
        warnings.append("registration residual %.2f m: the model outline and the capture outline disagree"
                        % reg["residual_mean_m"])

    shots = meta.get("shots", [])
    ppm_by_plane = refs_px_per_m(a.refs)
    planes_out = []
    for pl in capture_planes(meta):
        if pl.get("group_i") is None or pl["length_m"] < a.min_len:
            continue
        shot = next((s for s in shots if s.get("wall") == pl["group_i"]), None)
        if shot is None:
            continue
        m0 = R @ np.array(pl["p0"], dtype=float) + t
        m1 = R @ np.array(pl["p1"], dtype=float) + t
        hit = edge_coverage(ring_pts, m0, m1, a.max_perp)
        if not hit:
            continue
        _, k, s0, s1, Ld, perp, overlap = hit
        left_p0 = photo_left_is_p0(meta, pl, shot)
        if left_p0 is None:
            continue
        # s of the photo's left edge: p0 is on the left when left_p0, else p1
        s_left = s0 if left_p0 else s1
        s_right = s1 if left_p0 else s0
        ppm = ppm_by_plane.get(pl["i"])
        cap_ppm, vis_h = capture_px_per_m(meta, pl, shot)
        entry = {
            "plane": pl["i"], "group": pl["group_i"], "length_m": round(pl["length_m"], 3),
            "azimuth_deg": pl["azimuth_deg"], "edge": k, "edge_length_m": round(Ld, 3),
            "photo_left_m": round(s_left, 3), "photo_right_m": round(s_right, 3),
            "mirrored": bool(s_right < s_left),
            "coverage_m": round(float(overlap), 3),
            "coverage_ratio": round(float(overlap) / max(pl["length_m"], 1e-6), 3),
            "perp_m": round(float(perp), 3),
            # the capture resolution is the real information limit; a stitched plane file can
            # be resampled to any resolution, so it never raises the limit.
            "px_per_m_capture": round(cap_ppm, 1) if cap_ppm else None,
            "px_per_m_file": round(ppm, 1) if ppm else None,
            "visible_height_m": round(float(vis_h), 1) if vis_h else None,
        }
        pw = []
        limit = entry["px_per_m_capture"] or entry["px_per_m_file"]
        if limit and limit < a.min_px_per_m:
            pw.append("capture resolution %.0f px/m is too low to measure window widths (need %.0f); "
                      "recapture this face wider" % (limit, a.min_px_per_m))
        if entry["px_per_m_file"] and entry["px_per_m_capture"] \
                and entry["px_per_m_file"] > entry["px_per_m_capture"] * 1.5:
            pw.append("the ref file is resampled up (%.0f px/m from %.0f px/m): it has no more detail"
                      % (entry["px_per_m_file"], entry["px_per_m_capture"]))
        if entry["coverage_ratio"] < 0.9:
            pw.append("photo covers only %.0f%% of the model edge" % (entry["coverage_ratio"] * 100))
        if entry["photo_left_m"] < -0.3 or entry["photo_right_m"] > Ld + 0.3:
            pw.append("photo reaches outside the model edge (%.2f..%.2f of %.2f m)"
                      % (entry["photo_left_m"], entry["photo_right_m"], Ld))
        entry["warnings"] = pw
        warnings += ["plane %d: %s" % (pl["i"], w) for w in pw]
        planes_out.append(entry)

    edges_out = []
    for k in range(len(ring)):
        ra, rb = ring[k], ring[(k + 1) % len(ring)]
        Ld = math.hypot(rb[0] - ra[0], rb[1] - ra[1])
        covering = [q["plane"] for q in planes_out if q["edge"] == k]
        edges_out.append({"edge": k, "length_m": round(Ld, 3),
                          "a": [round(ra[0], 3), round(ra[1], 3)],
                          "b": [round(rb[0], 3), round(rb[1], 3)],
                          "planes": covering})
        if not covering:
            warnings.append("model edge %d (%.2f m) has no photo plane" % (k, Ld))

    low_res = [q for q in planes_out
               if any(w.startswith("capture resolution") for w in q["warnings"])]

    out = {"_schema": "photo-plane-map-v1",
           "_help": "photo planes of the capture mapped onto the model ring; photo u=0 -> photo_left_m",
           "capture": {"meta": a.meta, "dong": meta.get("dong")},
           "mass": {"file": os.path.relpath(mass_path, ROOT), "volume": vol.get("id"),
                    "edges": len(ring)},
           "registration": reg,
           "registration_cache": {"path": os.path.relpath(os.path.abspath(a.cache), ROOT).replace(os.sep, "/")
                                  if a.cache and not a.no_cache else None,
                                  "hit": cache_hit},
           "model_edges": edges_out,
           "planes": planes_out,
           "warnings": warnings,
           }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    if a.json:
        print(json.dumps(out, ensure_ascii=False))
        return 1 if (a.strict and low_res) else 0

    p("registration: rot %.2f deg, residual mean %.2f m / max %.2f m  (model %s, %d edges)%s"
      % (reg["rot_deg"], reg["residual_mean_m"], reg["residual_max_m"], out["mass"]["volume"], len(ring),
         "  [cache hit]" if cache_hit else ""))
    p("")
    p("%-6s %-5s %8s %-6s %9s %9s %6s %7s %7s %7s  %s"
      % ("plane", "grp", "len_m", "edge", "left_m", "right_m", "cover", "perp", "cap_px", "file_px", "warn"))
    for q in planes_out:
        p("%-6d %-5d %8.2f %-6d %9.2f %9.2f %6.2f %7.2f %7s %7s  %s"
          % (q["plane"], q["group"], q["length_m"], q["edge"], q["photo_left_m"], q["photo_right_m"],
             q["coverage_ratio"], q["perp_m"],
             q["px_per_m_capture"] if q["px_per_m_capture"] else "-",
             q["px_per_m_file"] if q["px_per_m_file"] else "-",
             "; ".join(q["warnings"])))
    if warnings:
        p("")
        p("warnings:")
        for w in warnings:
            p("  - " + w)
    p("")
    p("wrote %s" % a.out)
    if a.strict and low_res:
        p("strict: %d plane(s) below %.0f px/m - recapture before measuring columns"
          % (len(low_res), a.min_px_per_m))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
