# -*- coding: utf-8 -*-
"""Score reference photos before facade work: blur, exposure clipping, duplicates, resolution.

  python tools/photo_quality.py --project P --dir photos --json
  python tools/photo_quality.py --project P --dir photos/frames --strict

Uses only Pillow and numpy. Flat walls and sky can score low on the blur metric;
inspect flagged photos rather than deleting them automatically.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402  (consumes --project and chdirs to the project)

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")


def laplacian_variance(gray, max_side=1024):
    if max(gray.shape) > max_side:
        scale = max_side / float(max(gray.shape))
        size = (max(1, int(gray.shape[1] * scale)), max(1, int(gray.shape[0] * scale)))
        gray = np.asarray(Image.fromarray(gray).resize(size, Image.LANCZOS), dtype=np.float32)
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    centre = -4.0 * gray[1:-1, 1:-1]
    lap = centre + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    return float(lap.var())


def dhash(gray):
    small = Image.fromarray(gray).resize((9, 8), Image.LANCZOS)
    a = np.asarray(small, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).astype(np.uint8)
    return "".join(f"{int(''.join(str(int(b)) for b in row), 2):02x}" for row in bits)


def hamming(a, b):
    return sum(bin(int(x, 16) ^ int(y, 16)).count("1") for x, y in zip(a, b))


def thumb_diff(a, b):
    return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())


def display_path(path):
    try:
        return os.path.relpath(path, proj.ROOT).replace(os.sep, "/")
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")


def measure(path, min_side, blur_min, dark_clip, bright_clip):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    gray = np.asarray(im.convert("L"), dtype=np.float32)
    flags = []
    if min(w, h) < min_side:
        flags.append("small")
    blur = laplacian_variance(gray)
    if blur < blur_min:
        flags.append("blur")
    dark = float((gray <= 5).mean())
    bright = float((gray >= 250).mean())
    std = float(gray.std())
    if dark > dark_clip:
        flags.append("dark")
    if bright > bright_clip:
        flags.append("clip")
    if std < 8.0:
        flags.append("flat")
    thumb = np.asarray(Image.fromarray(gray).resize((32, 32), Image.BILINEAR), dtype=np.uint8)
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:16]
    return {"file": display_path(path), "size": [w, h],
            "blur": round(blur, 1), "dark": round(dark, 4), "bright": round(bright, 4),
            "mean": round(float(gray.mean()), 1), "std": round(std, 1),
            "hash": dhash(gray), "sha": digest, "_thumb": thumb, "flags": flags}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="photos", help="folder with reference photos")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--min-side", type=int, default=600, help="warn below this short side (px)")
    ap.add_argument("--blur-min", type=float, default=30.0, help="Laplacian variance threshold")
    ap.add_argument("--dark-clip", type=float, default=0.98, help="warn when this fraction is near black")
    ap.add_argument("--bright-clip", type=float, default=0.98, help="warn when this fraction is near white")
    ap.add_argument("--dup-distance", type=int, default=2, help="dHash Hamming distance for duplicates")
    ap.add_argument("--dup-pixel", type=float, default=3.0, help="32x32 mean pixel difference for duplicates")
    ap.add_argument("--all", action="store_true", help="print every file, not only flagged")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any file is flagged")
    ap.add_argument("--report", help="write the JSON report here")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    pattern = "**/*" if a.recursive else "*"
    paths = [p for p in glob.glob(os.path.join(a.dir, pattern), recursive=a.recursive)
             if os.path.isfile(p) and os.path.splitext(p)[1].lower() in EXTS]
    paths.sort()
    if not paths:
        result = {"status": "MISSING", "dir": a.dir, "images": 0, "files": []}
        print(json.dumps(result, ensure_ascii=False) if a.json else f"[quality] no images in {a.dir}")
        return 2

    rows = []
    for p in paths:
        try:
            rows.append(measure(p, a.min_side, a.blur_min, a.dark_clip, a.bright_clip))
        except Exception as ex:  # noqa: BLE001
            rows.append({"file": display_path(p),
                         "flags": ["unreadable"], "error": f"{type(ex).__name__}: {ex}"})

    hashed = [r for r in rows if "hash" in r]
    for row in rows:
        row.setdefault("duplicate_of", None)
    parent = list(range(len(hashed)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(hashed)):
        for j in range(i + 1, len(hashed)):
            same = hashed[i]["sha"] == hashed[j]["sha"]
            near = (hamming(hashed[i]["hash"], hashed[j]["hash"]) <= a.dup_distance
                    and thumb_diff(hashed[i]["_thumb"], hashed[j]["_thumb"]) <= a.dup_pixel)
            if same or near:
                union(i, j)
    groups = {}
    for i, row in enumerate(hashed):
        groups.setdefault(find(i), []).append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        best = max(group, key=lambda r: (min(r.get("size", [0, 0])), r.get("blur", 0), r.get("std", 0)))
        for row in group:
            if row is best:
                continue
            row["duplicate_of"] = best["file"]
            if "duplicate" not in row["flags"]:
                row["flags"].append("duplicate")
    for row in rows:
        row.pop("_thumb", None)

    flagged = [r for r in rows if r["flags"]]
    result = {"status": "WARN" if flagged else "OK", "dir": a.dir, "images": len(rows),
              "flagged": len(flagged), "thresholds": {"min_side": a.min_side, "blur_min": a.blur_min,
                                                       "dark_clip": a.dark_clip, "bright_clip": a.bright_clip,
                                                       "dup_distance": a.dup_distance, "dup_pixel": a.dup_pixel},
              "files": rows}
    if a.report:
        os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    if a.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for r in rows if a.all else flagged:
            detail = f"blur {r.get('blur', '-')} dark {r.get('dark', '-')} bright {r.get('bright', '-')} size {r.get('size', '-')}"
            dup = f" dup={r['duplicate_of']}" if r.get("duplicate_of") else ""
            print(f"  {r['file']}  [{','.join(r['flags'])}]  {detail}{dup}")
        print(f"[quality] {len(rows)} images, {len(flagged)} flagged -> {result['status']}")
    return 1 if (a.strict and flagged) else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
