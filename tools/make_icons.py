"""Transparent square building icons for every finished asset of a project.

    python tools/make_icons.py <project> [name-substring ...]

Reads projects/<project>/output/<asset>/ (OBJ + textures, rendered with tools/render.py's rasteriser, colour + silhouette)
and writes projects/<project>/icons/{512,256,128}/<AssetName>.png plus _sheet_light.png / _sheet_dark.png.
View: yaw -35 / pitch 20 (front + right face).  Assets without an OBJ are skipped and listed.
"""
import os
import re
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import render as R  # noqa: E402

YAW, PITCH = -35, 20
SS = 1800                      # supersampled render size
SIZES = (512, 256, 128)
MARGIN = 0.07


def has_obj(a):
    for d in (os.path.join(a, "_check"), a):
        if os.path.isdir(d) and any(f.endswith(".obj") and "_LOD" not in f and "_Win" not in f for f in os.listdir(d)):
            return True
    return False


def render_pair(path):
    asset, M, texdir, man = R.load_asset(path)
    tex = R.Tex(texdir, asset, False, "color")
    parts = [(M.get("main"), "s"), (M.get("win"), "window"), (M.get("gls"), "glass")]
    col = R.render(parts, tex, YAW, PITCH, (SS, SS), "", label=False)
    msk = R.render(parts, tex, YAW, PITCH, (SS, SS), "", label=False, mask=True)
    rgb = np.asarray(col.convert("RGB"), np.float32)
    a = (np.asarray(msk.convert("L"), np.float32) > 127).astype(np.float32)
    return rgb, a


def square_crop(rgb, a):
    ys, xs = np.nonzero(a > 0)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb, a = rgb[y0:y1, x0:x1], a[y0:y1, x0:x1]
    h, w = a.shape
    s = int(max(h, w) * (1 + 2 * MARGIN))
    cr = np.zeros((s, s, 3), np.float32)
    ca = np.zeros((s, s), np.float32)
    oy = (s - h) // 2 + int(0.015 * s)           # a little lower so the roof antenna has room
    ox = (s - w) // 2
    cr[oy:oy + h, ox:ox + w] = rgb
    ca[oy:oy + h, ox:ox + w] = a
    return cr, ca


def downscale(cr, ca, n):
    """premultiplied-alpha downscale (no halo from the sky colour)"""
    ch = [Image.fromarray(np.ascontiguousarray(x, dtype=np.float32)).resize((n, n), Image.LANCZOS) for x in
          (cr[..., 0] * ca, cr[..., 1] * ca, cr[..., 2] * ca, ca * 255.0)]
    r, g, b, al = (np.asarray(c, np.float32) for c in ch)
    alpha = (al / 255.0).clip(0, 1)
    div = np.maximum(alpha, 1e-4)
    rgb = np.dstack([r / div, g / div, b / div]).clip(0, 255)
    out = np.dstack([rgb, alpha * 255.0]).clip(0, 255).astype(np.uint8)
    out[alpha < 0.004] = 0
    return Image.fromarray(out, "RGBA")


def main():
    project = sys.argv[1]
    only = sys.argv[2:]
    P = os.path.join(ROOT, "projects", project)
    OUT = os.path.join(P, "icons")
    for n in SIZES:
        os.makedirs(os.path.join(OUT, str(n)), exist_ok=True)
    names = sorted(d for d in os.listdir(os.path.join(P, "output")) if os.path.isdir(os.path.join(P, "output", d)))
    sheet, skipped = [], []
    for name in names:
        short = re.sub(r"_L\d+(_\d+x\d+)?$", "", name)
        if only and not any(o in short for o in only):
            continue
        path = os.path.join(P, "output", name)
        if not has_obj(path):
            skipped.append(name)
            continue
        rgb, a = render_pair(path)
        if a.max() <= 0:
            skipped.append(name + " (empty render)")
            continue
        cr, ca = square_crop(rgb, a)
        for n in SIZES:
            downscale(cr, ca, n).save(os.path.join(OUT, str(n), short + ".png"))
        sheet.append(Image.open(os.path.join(OUT, "256", short + ".png")))
        print("ok", project, short, flush=True)
    if sheet and not only:
        W, cols = 256, 4
        rows = (len(sheet) + cols - 1) // cols
        for tag, bg in (("light", (214, 226, 242)), ("dark", (38, 44, 54))):
            im = Image.new("RGB", (cols * W, rows * W), bg)
            for i, ic in enumerate(sheet):
                im.paste(ic, ((i % cols) * W, (i // cols) * W), ic)
            im.save(os.path.join(OUT, f"_sheet_{tag}.png"))
    for s in skipped:
        print("skip", project, s, flush=True)


if __name__ == "__main__":
    main()
