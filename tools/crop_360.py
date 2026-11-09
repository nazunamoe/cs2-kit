# -*- coding: utf-8 -*-
"""Crop perspective views from an equirectangular 360 photo.

  python tools/crop_360.py --project P --image photos/pano.jpg \
    --yaws 0,90,180,270 --fov 90 --size 1600x1200 --out photos/crops

The source photo is never modified. The crop is a normal perspective image, so
photo_refs / evidence can use it like any other facade photo. Yaw 0 looks at
the equirectangular center column; positive yaw turns right.
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402  (consumes --project and chdirs to the project)


def parse_size(text):
    m = re.fullmatch(r"\s*(\d+)\s*[xX,]\s*(\d+)\s*", text or "")
    if not m:
        raise SystemExit("--size must look like 1600x1200")
    w, h = int(m.group(1)), int(m.group(2))
    if w < 16 or h < 16:
        raise SystemExit("--size is too small")
    return w, h


def equirect_to_perspective(img, yaw_deg, pitch_deg, fov_deg, width, height):
    """Bilinear perspective sample from an equirectangular RGB array."""
    H, W = img.shape[:2]
    fov = math.radians(fov_deg)
    tan_h = math.tan(fov / 2.0)
    tan_v = tan_h * height / width

    xs = (np.arange(width, dtype=np.float32) + 0.5) / width * 2.0 - 1.0
    ys = 1.0 - (np.arange(height, dtype=np.float32) + 0.5) / height * 2.0
    xx, yy = np.meshgrid(xs * tan_h, ys * tan_v)
    zz = np.ones_like(xx)

    # camera rays: pitch about X, then yaw about Y
    p = math.radians(pitch_deg)
    cp, sp = math.cos(p), math.sin(p)
    y1 = yy * cp + zz * sp
    z1 = -yy * sp + zz * cp
    x1 = xx

    yw = math.radians(yaw_deg)
    cy, sy = math.cos(yw), math.sin(yw)
    x2 = x1 * cy + z1 * sy
    z2 = -x1 * sy + z1 * cy
    y2 = y1

    norm = np.sqrt(x2 * x2 + y2 * y2 + z2 * z2)
    x2, y2, z2 = x2 / norm, y2 / norm, z2 / norm
    lon = np.arctan2(x2, z2)
    lat = np.arcsin(np.clip(y2, -1.0, 1.0))

    u = (lon / (2.0 * math.pi) + 0.5) * W - 0.5
    v = (0.5 - lat / math.pi) * H - 0.5
    u = np.mod(u, W)
    v = np.clip(v, 0.0, H - 1.0)

    u0 = np.floor(u).astype(np.int32)
    v0 = np.floor(v).astype(np.int32)
    u1 = (u0 + 1) % W
    v1 = np.minimum(v0 + 1, H - 1)
    fu = (u - u0)[..., None]
    fv = (v - v0)[..., None]
    a = img[v0, u0] * (1 - fu) + img[v0, u1] * fu
    b = img[v1, u0] * (1 - fu) + img[v1, u1] * fu
    out = a * (1 - fv) + b * fv
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def output_path(out, prefix, yaw, single):
    if single and not os.path.isdir(out) and os.path.splitext(out)[1]:
        return out
    os.makedirs(out, exist_ok=True)
    tag = ("%+g" % yaw).replace("+", "p").replace("-", "m")
    return os.path.join(out, f"{prefix}_yaw{tag}.jpg")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True, help="equirectangular 360 photo")
    ap.add_argument("--yaws", default="0", help="comma-separated yaw degrees (0 = center column, + = right)")
    ap.add_argument("--pitch", type=float, default=0.0, help="vertical look angle in degrees (+ = up)")
    ap.add_argument("--fov", type=float, default=90.0, help="horizontal field of view in degrees")
    ap.add_argument("--size", default="1600x1200", help="output WxH")
    ap.add_argument("--out", default="photos", help="output folder, or one file when a single yaw is used")
    ap.add_argument("--prefix", default="", help="output name prefix (default: source stem)")
    ap.add_argument("--quality", type=int, default=95, help="JPEG quality")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.image):
        raise SystemExit(f"no such image: {a.image}")
    if not (1.0 <= a.fov <= 170.0):
        raise SystemExit("--fov must be between 1 and 170 degrees")
    width, height = parse_size(a.size)

    src = Image.open(a.image).convert("RGB")
    img = np.asarray(src, dtype=np.float32)
    if img.shape[1] < img.shape[0] * 1.8:
        raise SystemExit("source does not look equirectangular (width should be about 2x height)")
    if abs(img.shape[1] - img.shape[0] * 2) > max(8, img.shape[0] * 0.05):
        print(f"[crop_360] WARN aspect {img.shape[1]}x{img.shape[0]} is not exactly 2:1", file=sys.stderr)

    stem = a.prefix or os.path.splitext(os.path.basename(a.image))[0]
    yaws = [float(t) for t in a.yaws.replace(" ", "").split(",") if t]
    if not yaws:
        raise SystemExit("--yaws is empty")
    single = len(yaws) == 1
    outputs = []
    for yaw in yaws:
        path = output_path(a.out, stem, yaw, single)
        outputs.append(path)
        if a.dry_run:
            continue
        crop = equirect_to_perspective(img, yaw, a.pitch, a.fov, width, height)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        Image.fromarray(crop).save(path, quality=a.quality)
        print(f"[crop_360] yaw {yaw:g} pitch {a.pitch:g} fov {a.fov:g} -> {path}")

    result = {"status": "DRY_RUN" if a.dry_run else "OK", "image": a.image,
              "source_size": [src.width, src.height], "yaws": yaws, "pitch": a.pitch,
              "fov": a.fov, "size": [width, height], "outputs": outputs}
    if a.json:
        print(json.dumps(result, ensure_ascii=False))
    return


if __name__ == "__main__":
    main()
