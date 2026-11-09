# -*- coding: utf-8 -*-
"""Normalize facade photos so shadowed walls read with the same colour as lit ones.

  python tools/shadow_norm.py --image photos/ref101/101_stitched_p16.png \
    --out photos/ref101/101_stitched_p16_lit.png

Method: the brightest percentile of the image is treated as the white wall
reference. Each block gets its own gain from its own bright pixels, the gain map
is smoothed, and every pixel is scaled by it. Shadowed blocks brighten toward
the lit white, so sampled colours describe the material instead of the lighting.

This is for measurement and albedo textures, not for display images.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def normalize(arr, block=64, max_gain=1.8, bright_pct=92.0):
    """Return the normalized image and a stats dict."""
    a = arr.astype(np.float32)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    h, w = lum.shape
    white = float(np.percentile(lum, 98))
    stats = {"white": round(white, 1), "mean": round(float(lum.mean()), 1),
             "gain_min": 1.0, "gain_max": 1.0, "skipped": None}
    if white < 45:
        stats["skipped"] = "no bright reference (image too dark)"
        return arr, stats
    bs = max(8, int(block))
    bh, bw = int(np.ceil(h / bs)), int(np.ceil(w / bs))
    gains = np.ones((bh, bw), dtype=np.float32)
    for i in range(bh):
        for j in range(bw):
            blk = lum[i * bs:(i + 1) * bs, j * bs:(j + 1) * bs]
            if blk.size < 16:
                continue
            b = float(np.percentile(blk, bright_pct))
            if b < 25:
                continue                       # deep shadow: keep as is (noise)
            gains[i, j] = min(max_gain, max(1.0, white / b))
    norm = np.clip(gains / max(max_gain, 1e-6), 0.0, 1.0)
    g = Image.fromarray((norm * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    g = np.asarray(g, dtype=np.float32) / 255.0 * max_gain
    out = np.clip(a * g[..., None], 0, 255)
    stats["gain_min"] = round(float(gains.min()), 3)
    stats["gain_max"] = round(float(gains.max()), 3)
    stats["white_after"] = round(float(np.percentile(0.299 * out[..., 0] + 0.587 * out[..., 1] + 0.114 * out[..., 2], 98)), 1)
    return out.astype(np.uint8), stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", action="append", help="image file (repeatable)")
    ap.add_argument("--dir", help="folder of images")
    ap.add_argument("--out", help="output file (single image) or folder (with --dir)")
    ap.add_argument("--suffix", default="_lit", help="output name suffix for --dir")
    ap.add_argument("--block", type=int, default=64, help="block size in px for the gain map")
    ap.add_argument("--max-gain", type=float, default=1.8)
    ap.add_argument("--bright-pct", type=float, default=92.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    files = list(a.image or [])
    if a.dir:
        files += sorted(os.path.join(a.dir, f) for f in os.listdir(a.dir)
                       if f.lower().endswith(EXTS) and not f.endswith(a.suffix + ".png"))
    if not files:
        raise SystemExit("no input: use --image or --dir")

    results = []
    for path in files:
        if not os.path.isfile(path):
            raise SystemExit(f"no such image: {path}")
        im = Image.open(path).convert("RGB")
        out_img, stats = normalize(np.asarray(im), a.block, max_gain=a.max_gain, bright_pct=a.bright_pct)
        if a.out and len(files) == 1 and not a.dir:
            dest = a.out
        else:
            folder = a.out or os.path.dirname(path)
            os.makedirs(folder, exist_ok=True)
            stem, ext = os.path.splitext(os.path.basename(path))
            dest = os.path.join(folder, f"{stem}{a.suffix}.png")
        Image.fromarray(out_img).save(dest)
        stats["in"] = path
        stats["out"] = dest
        results.append(stats)
        if not a.json:
            print(f"[shadow] {path} -> {dest}  white {stats['white']} gain {stats['gain_min']}~{stats['gain_max']}"
                  + (f"  ({stats['skipped']})" if stats["skipped"] else ""))
    if a.json:
        print(json.dumps({"status": "OK", "images": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
