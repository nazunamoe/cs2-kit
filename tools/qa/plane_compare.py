# -*- coding: utf-8 -*-
"""plane_compare.py - compare a photo plane with the model, plane by plane.

The capture photo and the model live in different coordinate frames, so a whole-photo
silhouette comparison (tools/qa/cmp_cam.py) cannot tell whether the *facade* of one wall
matches. This tool registers the two (work/plane_to_edge.json from tools/photo_plane_map.py),
renders the model from the exact capture camera, and warps photo and model onto the same
plane rectangle:

    python tools/qa/plane_compare.py --project my-building \
        --asset output/<asset> --meta photos/<dong>_meta.json --refs photo_refs.json \
        --plane-map work/plane_to_edge.json --out work/plane_compare

For every photo ref it writes
    work/plane_compare/<plane>_<shot>.png   photo | model   (same rectangle, same scale)
and prints how far the model plane sits from the photo plane inside the photo frame, so a
wrong registration shows up before the facade is judged.

A ref is one capture band (the file is the capture photo and its corners are in that
photo's pixels). A stitched multi-band plane has no single camera, so it is compared band
by band: use the band refs, or give the entry a "source_file" that names the capture photo.

Options:
    --ppm 20          pixels per metre of the comparison image
    --z0 / --z1      height band of the building to compare (default: the ref's own band)
    --no-render      reuse the existing render instead of calling Blender
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, "tools"))
import proj  # noqa: E402,F401  (work in the active project)
from extract_texture import warp  # noqa: E402

CAM_SCRIPT = os.path.join(KIT, "tools", "qa", "plane_cam.py")


def blender_exe():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    p = os.path.join(KIT, "tools", "blender_path.txt")
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else "blender"


def mat_from_list(v):
    """three.js column major 16 floats -> row major 4x4 numpy"""
    return np.array([[v[0], v[4], v[8], v[12]],
                     [v[1], v[5], v[9], v[13]],
                     [v[2], v[6], v[10], v[14]],
                     [v[3], v[7], v[11], v[15]]], dtype=float)


def build_matrix(pmap, ground_m):
    """model metres -> capture metres -> capture scene units (m/100).

    The registration of the plane map was computed on the 2D footprints: capture (X, Z) and
    model (x, y). model = R @ capture + t, so capture = R^-1 (model - t). The height maps
    1:1 (model z = 0 is the capture ground).
    """
    reg = pmap["registration"]
    a = math.radians(reg["rot_deg"])
    Rm = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    t = np.array(reg["translation"], dtype=float)
    Ri = np.linalg.inv(Rm)
    T = np.zeros((4, 4))
    T[3, 3] = 1.0
    T[0, 0], T[0, 1] = Ri[0, 0], Ri[0, 1]          # capture X from model x, y
    T[0, 3] = -(Ri[0, 0] * t[0] + Ri[0, 1] * t[1])
    T[1, 2] = 1.0                                    # capture height from model z
    T[1, 3] = ground_m
    T[2, 0], T[2, 1] = Ri[1, 0], Ri[1, 1]          # capture Z from model x, y
    T[2, 3] = -(Ri[1, 0] * t[0] + Ri[1, 1] * t[1])
    S = np.diag([0.01, 0.01, 0.01, 1.0])   # metres -> scene units (m/100), w stays 1
    return S @ T


def project(V, P, box, dpr, img, p_model):
    """model point -> pixel of the rendered photo grid (None behind the camera)."""
    p = np.array([p_model[0], p_model[1], p_model[2], 1.0])
    clip = P @ (V @ p)
    if clip[3] <= 1e-9:
        return None
    nx, ny = clip[0] / clip[3], clip[1] / clip[3]
    cx, cy = (nx + 1) / 2 * box["vw"], (1 - ny) / 2 * box["vh"]
    sx = img[0] / (box["width"] * dpr)
    sy = img[1] / (box["height"] * dpr)
    return [(cx - box["x"]) * dpr * sx, (cy - box["y"]) * dpr * sy]


def find_shot(entry, shots, group):
    """the capture photo this ref was taken from"""
    for key in ("source_file", "source_shot", "shot"):
        v = entry.get(key)
        if v:
            hit = next((s for s in shots if os.path.basename(s["file"]) == os.path.basename(v)), None)
            if hit:
                return hit
    base = os.path.basename(entry.get("file", ""))
    hit = next((s for s in shots if os.path.basename(s["file"]) == base), None)
    if hit:
        return hit
    if group is not None:
        return next((s for s in shots if s.get("wall") == group), None)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asset", required=True, help="asset folder (output/<asset>) or the .blend file")
    ap.add_argument("--meta", required=True, help="capture meta json")
    ap.add_argument("--refs", required=True, help="photo_refs json (band refs)")
    ap.add_argument("--plane-map", required=True, help="work/plane_to_edge.json")
    ap.add_argument("--ppm", type=float, default=20.0)
    ap.add_argument("--z0", type=float, help="bottom of the compared height band (m)")
    ap.add_argument("--z1", type=float, help="top of the compared height band (m)")
    ap.add_argument("--out", default="work/plane_compare")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    with open(a.meta, encoding="utf-8-sig") as f:
        meta = json.load(f)
    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    with open(a.plane_map, encoding="utf-8") as f:
        pmap = json.load(f)

    blend = a.asset
    if os.path.isdir(blend):
        names = [n for n in os.listdir(blend) if n.endswith(".blend")]
        if not names:
            raise SystemExit("no .blend in %s" % blend)
        blend = os.path.join(blend, names[0])

    M = build_matrix(pmap, meta["ground_m"])
    edges = {e["edge"]: e for e in pmap["model_edges"]}
    shots = meta["shots"]
    os.makedirs(a.out, exist_ok=True)
    renders = {}

    def render_shot(shot):
        if shot["file"] in renders:
            return renders[shot["file"]]
        out = os.path.join(a.out, "render_%s.png" % os.path.splitext(shot["file"])[0])
        if a.no_render or not os.path.isfile(out):
            V = mat_from_list(shot["cam"]["view"])
            P = mat_from_list(shot["cam"]["proj"])
            Vp = V @ M
            lens = 18.0 * P[0, 0]
            cmd = [blender_exe(), "-b", blend, "-P", CAM_SCRIPT, "--",
                   ",".join("%.9f" % x for x in Vp.flatten().tolist()),
                   "%.6f" % lens, str(shot["img"][0]), str(shot["img"][1]), os.path.abspath(out)]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if not os.path.isfile(out):
                raise SystemExit("blender render failed:\n" + (r.stdout + r.stderr)[-800:])
        renders[shot["file"]] = out
        return out

    total = 0
    for entry in refs.get("facades", []):
        plane = entry.get("source_plane_i")
        if plane is None:
            continue
        info = next((q for q in pmap["planes"] if q["plane"] == plane), None)
        if info is None:
            print("SKIP %s: plane %s is not in the plane map" % (entry.get("name"), plane))
            continue
        shot = find_shot(entry, shots, info.get("group"))
        if shot is None:
            print("SKIP %s: no capture shot for this ref" % entry.get("name"))
            continue
        edge = edges.get(info["edge"])
        if edge is None:
            continue
        size = entry.get("size_m") or []
        if len(size) < 2:
            continue
        w_m = float(size[0])
        z_m = entry.get("z_m") or [0.0, float(size[1])]
        z_top, z_bot = float(z_m[1]), float(z_m[0])
        band_z0 = a.z0 if a.z0 is not None else z_bot
        band_z1 = a.z1 if a.z1 is not None else z_top
        band_z0, band_z1 = max(band_z0, z_bot), min(band_z1, z_top)
        if band_z1 - band_z0 < 1.0:
            print("SKIP %s: empty height band" % entry.get("name"))
            continue

        a0, b0 = edge["a"], edge["b"]
        L = math.hypot(b0[0] - a0[0], b0[1] - a0[1])
        ux, uy = (b0[0] - a0[0]) / L, (b0[1] - a0[1]) / L
        s_left, s_right = info["photo_left_m"], info["photo_right_m"]

        def point(s, z):
            return (a0[0] + ux * s, a0[1] + uy * s, z)

        V = mat_from_list(shot["cam"]["view"])
        P = mat_from_list(shot["cam"]["proj"])
        box = dict(meta["canvas_css"])
        img = shot["img"]
        box["vw"] = shot["cam"].get("vw", img[0])
        box["vh"] = shot["cam"].get("vh", img[1])
        dpr = meta["dpr"]
        quad = []
        outside = False
        for s, z in ((s_left, band_z1), (s_right, band_z1), (s_right, band_z0), (s_left, band_z0)):
            px = project(V @ M, P, box, dpr, img, point(s, z))
            if px is None:
                outside = True
                break
            if not (-0.2 * img[0] <= px[0] <= 1.2 * img[0] and -0.2 * img[1] <= px[1] <= 1.2 * img[1]):
                outside = True
            quad.append([px[0], px[1]])
        if outside:
            print("SKIP %s: the model plane is outside the photo frame of %s "
                  "(compare the band refs instead)" % (entry.get("name"), shot["file"]))
            continue

        render = render_shot(shot)
        model_img = Image.open(render).convert("RGB")
        photo_img = Image.open(entry["file"]).convert("RGB")
        W = max(8, int(round(w_m * a.ppm)))
        H = max(8, int(round((band_z1 - band_z0) * a.ppm)))
        p_warp = warp(photo_img, [tuple(c) for c in entry["corners"]], W, H)
        m_warp = warp(model_img, [tuple(c) for c in quad], W, H)
        gap = 6
        sheet = Image.new("RGB", (W * 2 + gap, H), (235, 235, 235))
        sheet.paste(p_warp, (0, 0))
        sheet.paste(m_warp, (W + gap, 0))
        name = "%s_%s" % (plane, os.path.splitext(os.path.basename(shot["file"]))[0])
        outp = os.path.join(a.out, name + ".png")
        sheet.save(outp)
        total += 1
        dx = float(np.array(quad[0])[0] - np.array(entry["corners"][0])[0])
        dy = float(np.array(quad[3])[1] - np.array(entry["corners"][3])[1])
        print("%-22s plane %-3d edge %-3d  %5.2f m wide, z %6.1f..%6.1f  model quad %s  "
              "offset %+.0f/%+.0f px -> %s"
              % (entry.get("name"), plane, info["edge"], w_m, band_z0, band_z1,
                 " ".join("%.0f" % q[0] for q in quad), dx, dy, outp))
    print("PLANECOMPARE %d plane(s) -> %s" % (total, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
