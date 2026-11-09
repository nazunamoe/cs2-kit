"""pread.py kind photo_idx sec [--a al,ar --px pl,pr] [--f f0,f1] [--chunks N] [--zoom Z]
Annotated crops (floor numbers, wall boundaries magenta, model windows cyan) + per-floor zone table.
Zones per wall: P = pier between windows (whole floor height), U = under a window (sill band), O = over a window.
Letters: W white, g light grey, b blue panel, n dark navy / shadow, - hidden (label / out of frame)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import argparse
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = ROOT
import photo_sections as P  # noqa: E402
T = gen()

ap = argparse.ArgumentParser()
ap.add_argument("kind"); ap.add_argument("pi", type=int); ap.add_argument("sec")
ap.add_argument("--a"); ap.add_argument("--px"); ap.add_argument("--f", default="6,58")
ap.add_argument("--chunks", type=int, default=0); ap.add_argument("--zoom", type=float, default=2.0)
ap.add_argument("--table", action="store_true")
ap.add_argument("--walls")
ap.add_argument("--rowh", type=float)
args = ap.parse_args()

T.MIRROR = False
ph = P.PHOTOS[args.kind][args.pi]
sec = dict([s for s in ph["secs"] if s["name"] == args.sec][0])
if args.a:
    sec["a"] = tuple(float(v) for v in args.a.split(","))
if args.px:
    sec["px"] = tuple(float(v) for v in args.px.split(","))
if args.walls:
    sec["walls"] = [int(v) for v in args.walls.split(",")]
if args.rowh is not None:
    sec["rowh"] = args.rowh
im = Image.open(P.os.path.join(ROOT, ph["file"])).convert("RGB")
rgb = np.asarray(im, np.float32)
g = rgb.mean(2)
H, W = g.shape
x0, x1 = sorted(sec["px"])
yc, pitch = P.fit_rows(g, sec, int(x0), int(x1), np.zeros(g.shape, bool))
a_l, a_r = sec["a"]
p_l, p_r = sec["px"]


def px(a):
    return p_l + (a - a_l) * (p_r - p_l) / (a_r - a_l)


def fl(f):
    """(y floor line, pitch) of floor f"""
    p = abs(yc(f + 0.5) - yc(f - 0.5))
    return yc(f) + P.rowh(sec) * p, p


def zy(f, z):
    yb, p = fl(f)
    return yb - z / T.FH * p


E = T.edges_of(T.full_poly(T.HALF, False))
T.a_edge(E[0])
f0, f1 = (int(v) for v in args.f.split(","))
tint = ((rgb[..., 2] - rgb[..., 0] > 85) & (rgb[..., 2] > 120)) | ((rgb[..., 0] - rgb[..., 1] > 25) & (rgb[..., 2] - rgb[..., 1] > 25))
mask = np.zeros((H, W), bool)
for bx0, by0, bx1, by1 in ph["masks"]:
    mask[by0:by1, bx0:bx1] = True
mask |= tint

# local white reference: 95th percentile of the section per floor band, smoothed
xa_s, xb_s = int(max(0, x0)), int(min(W, x1))
prof = np.percentile(g[:, xa_s:xb_s], 95, axis=1)
k = int(abs(pitch) * 3)
ref = np.array([np.median(prof[max(0, i - k):i + k + 1]) for i in range(H)])
ref_br = np.median((rgb[..., 2] - rgb[..., 0])[:, xa_s:xb_s][g[:, xa_s:xb_s] > 0.9 * ref[:, None]])


def letter(ya, yb, xa, xb):
    ya, yb, xa, xb = int(round(ya)), int(round(yb)), int(round(xa)), int(round(xb))
    if yb - ya < 1 or xb - xa < 1 or ya < 0 or yb > H or xa < 0 or xb > W:
        return "-"
    if mask[ya:yb, xa:xb].mean() > 0.3:
        return "-"
    blk = rgb[ya:yb, xa:xb].reshape(-1, 3)
    m = np.median(blk, 0)
    rel = m.mean() / max(ref[(ya + yb) // 2], 1)
    br = (m[2] - m[0]) - ref_br
    if rel > 0.82:
        return "W"
    if rel < 0.33:
        return "n"
    if br > 14:
        return "b"
    return "g" if rel > 0.6 else "b"


def zones(e):
    wl = sorted(T.windows_of(e), key=lambda w: w[0])
    out, pos = [], e["a0"]
    for c, w, kd in wl:
        lo, hi = c - w / 2, c + w / 2
        if lo - pos > 0.25:
            out.append(("P", pos + 0.08, lo - 0.08, None))
        out.append(("W", lo + 0.1, hi - 0.1, kd))
        pos = hi
    if e["a1"] - pos > 0.25:
        out.append(("P", pos + 0.08, e["a1"] - 0.08, None))
    if not wl:
        out = [("P", e["a0"] + 0.08, e["a1"] - 0.08, None)]
    return out


if args.table:
    for i in sec["walls"]:
        e = E[i]
        zs = zones(e)
        # order zones left to right in the image
        zs = sorted(zs, key=lambda z: px((z[1] + z[2]) / 2))
        hdr = []
        for z in zs:
            hdr.append(("P%.1f" % ((z[1] + z[2]) / 2)) if z[0] == "P" else ("%s%.1f" % (z[3], (z[1] + z[2]) / 2)))
        print("wall %d (a %.1f..%.1f, L %.1f)  zones: %s" % (i, e["a0"], e["a1"], e["L"], " ".join(hdr)))
        for f in range(f1, f0 - 1, -1):
            row = []
            for z in zs:
                xa, xb = sorted((px(z[1]), px(z[2])))
                if z[0] == "P":
                    row.append(letter(zy(f, 2.9), zy(f, 0.15), xa, xb))
                else:
                    sill, h, _ = T.WIN_KIND.get(z[3], (0.35, 2.15, 0)) if z[3] != "V" else (0.35, 2.15, 0)
                    u = letter(zy(f, max(0.12, sill - 0.12)), zy(f, 0.1), xa, xb) if sill > 0.4 else " "
                    o = letter(zy(f, 2.95), zy(f, min(2.85, sill + h + 0.12)), xa, xb) if sill + h < 2.7 else " "
                    row.append(u + o)
            print("  %2d  %s" % (f, "  ".join("%-3s" % r for r in row)))
        print()

# annotated crops
if args.chunks:
    yt, _ = fl(f1)
    yt -= abs(pitch) * 1.2
    yb_all, _ = fl(f0)
    span = (yb_all - yt) / args.chunks
    pad = 50
    Z = args.zoom
    for c in range(args.chunks):
        ya, yb = max(0, yt + c * span - 8), min(H, yt + (c + 1) * span + 8)
        crop = im.crop((int(x0) - 20, int(ya), int(x1) + 20, int(yb)))
        crop = crop.resize((int(crop.size[0] * Z), int(crop.size[1] * Z)), Image.LANCZOS)
        o = Image.new("RGB", (crop.size[0] + pad, crop.size[1] + 30), "white")
        o.paste(crop, (pad, 30))
        d = ImageDraw.Draw(o)
        X = lambda xx: pad + (xx - (int(x0) - 20)) * Z
        Y = lambda yy: 30 + (yy - int(ya)) * Z
        for f in range(f0, f1 + 1):
            y, p = fl(f)
            if ya <= y <= yb:
                d.line([(pad - 14, Y(y)), (pad, Y(y))], fill=(220, 0, 0), width=2)
                d.text((2, Y(y) - p * Z * 0.6), str(f), fill=(220, 0, 0))
        for i in sec["walls"]:
            e = E[i]
            for a in (e["a0"], e["a1"]):
                d.line([(X(px(a)), 0), (X(px(a)), 26)], fill=(255, 0, 255), width=2)
            d.text((X(px((e["a0"] + e["a1"]) / 2)) - 6, 2), str(i), fill=(200, 0, 200))
            for cc, w, kd in T.windows_of(e):
                xa, xb = sorted((X(px(cc - w / 2)), X(px(cc + w / 2))))
                d.line([(xa, 22), (xb, 22)], fill=(0, 170, 220), width=4)
                d.text(((xa + xb) / 2 - 3, 8), kd, fill=(0, 120, 180))
        o.save(P.os.path.join(ROOT, "previews", "pr_%s%d_%s_%d.png" % (args.kind, args.pi, args.sec, c)))
    print("crops saved", args.chunks)
