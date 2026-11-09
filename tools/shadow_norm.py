# -*- coding: utf-8 -*-
"""Normalize facade photos so shadowed walls read with the same colour as lit ones.

  python tools/shadow_norm.py --image photos/ref101/101_stitched_p16.png \
    --out photos/ref101/101_stitched_p16_lit.png

  python tools/shadow_norm.py --refs photo_refs.json --out-refs photo_refs_lit.json

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proj import ROOT, KIT, NAME  # noqa: E402,F401  (project folder; chdir done)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def patch_whites(lum, patch_frac=0.18):
    """98th luminance percentile of five patches: four corners and the centre.

    A single whole-image percentile is pulled down by a large shadowed area or by a
    bright sky/window; the median of the patches is closer to the lit wall itself.
    """
    h, w = lum.shape
    ps = max(8, int(round(min(h, w) * patch_frac)))
    spots = [(0, 0), (w - ps, 0), (0, h - ps), (w - ps, h - ps),
             ((w - ps) // 2, (h - ps) // 2)]
    vals = []
    for x, y in spots:
        blk = lum[max(0, y):y + ps, max(0, x):x + ps]
        if blk.size >= 16:
            vals.append(round(float(np.percentile(blk, 98)), 1))
    return vals


def normalize(arr, block=64, max_gain=1.8, bright_pct=92.0,
              patch_median=False, patch_frac=0.18):
    """Return the normalized image and a stats dict."""
    a = arr.astype(np.float32)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    h, w = lum.shape
    white = float(np.percentile(lum, 98))
    stats = {"white": round(white, 1), "mean": round(float(lum.mean()), 1),
             "gain_min": 1.0, "gain_max": 1.0, "skipped": None}
    if patch_median:
        vals = patch_whites(lum, patch_frac)
        stats["white_patches"] = vals
        stats["white_mode"] = "patch-median" if vals else "global"
        if vals:
            white = float(np.median(vals))
            stats["white"] = round(white, 1)
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
    ap.add_argument("--refs", help="photo_refs json: normalize every referenced image and write a new refs json")
    ap.add_argument("--out-refs", help="where to write the new refs json (default: <refs>_lit.json)")
    ap.add_argument("--block", type=int, default=64, help="block size in px for the gain map")
    ap.add_argument("--max-gain", type=float, default=1.8)
    ap.add_argument("--bright-pct", type=float, default=92.0)
    ap.add_argument("--patch-median", action="store_true",
                    help="use the median of five patch whites (corners + centre) as the white reference")
    ap.add_argument("--patch-frac", type=float, default=0.18,
                    help="patch size as a fraction of the shorter side (default 0.18)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.refs:
        return refs_mode(a)

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
        out_img, stats = normalize(np.asarray(im), a.block, max_gain=a.max_gain, bright_pct=a.bright_pct,
                                   patch_median=a.patch_median, patch_frac=a.patch_frac)
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


def refs_mode(a):
    """Normalize every image a photo_refs.json points at and write a new refs json."""
    with open(a.refs, encoding="utf-8-sig") as f:
        refs = json.load(f)
    out_refs = a.out_refs or (os.path.splitext(a.refs)[0] + "_lit.json")
    cache = {}
    results = []
    changed = 0
    for entry in refs.get("facades", []):
        path = entry.get("file")
        if not path:
            continue
        if not os.path.isfile(path):
            results.append({"in": path, "status": "missing"})
            continue
        if path in cache:
            entry["file"] = cache[path]
            continue
        im = Image.open(path).convert("RGB")
        out_img, stats = normalize(np.asarray(im), a.block, max_gain=a.max_gain, bright_pct=a.bright_pct,
                                   patch_median=a.patch_median, patch_frac=a.patch_frac)
        folder = os.path.dirname(path)
        stem, _ = os.path.splitext(os.path.basename(path))
        dest = os.path.join(folder, f"{stem}{a.suffix}.png")
        Image.fromarray(out_img).save(dest)
        dest = dest.replace("\\", "/")          # keep refs portable across platforms
        cache[path] = dest
        entry["file"] = dest
        changed += 1
        stats.update({"in": path, "out": dest, "status": "OK" if not stats["skipped"] else stats["skipped"]})
        results.append(stats)
        if not a.json:
            print(f"[shadow] {path} -> {dest}  white {stats['white']} gain {stats['gain_min']}~{stats['gain_max']}"
                  + (f"  ({stats['skipped']})" if stats["skipped"] else ""))
    refs["_help"] = (refs.get("_help", "") + " | shadow-normalized (tools/shadow_norm.py): "
                      "shadowed areas lifted to the lit wall colour, for colour measurement only").strip(" |")
    refs["_shadow_norm"] = {"source_refs": a.refs, "block": a.block, "max_gain": a.max_gain,
                            "bright_pct": a.bright_pct, "suffix": a.suffix,
                            "patch_median": bool(a.patch_median), "patch_frac": a.patch_frac,
                            "note": "use for albedo/paint measurement, not as a display photo"}
    with open(out_refs, "w", encoding="utf-8") as f:
        json.dump(refs, f, ensure_ascii=False, indent=1)
    if not a.json:
        print(f"[shadow] {changed} image(s) normalized, refs -> {out_refs}")
    if a.json:
        print(json.dumps({"status": "OK", "refs": out_refs, "images": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
