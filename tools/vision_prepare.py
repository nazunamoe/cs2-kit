"""Prepare a wall/detail crop for external vision review without editing the source photo."""
import argparse
import hashlib
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proj import ROOT  # noqa: E402


def numbers(text, count=4):
    values = [int(v) for v in text.split(",")]
    if len(values) != count:
        raise ValueError("expected comma-separated rectangle x0,y0,x1,y1")
    return values


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rectangle(values, width, height):
    x0, y0, x1, y1 = values
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height or x1 <= x0 or y1 <= y0:
        raise ValueError(f"rectangle {values} is outside image {width}x{height} or empty")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo")
    parser.add_argument("--box", help="crop in original photo pixels: x0,y0,x1,y1")
    parser.add_argument("--redact", action="append", default=[], help="source-photo rectangle to black out; repeatable")
    parser.add_argument("--wall-id", default="")
    parser.add_argument("--max-side", type=int, default=1300)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    source = os.path.abspath(args.photo)
    if not os.path.isfile(source):
        raise ValueError(f"photo not found: {args.photo}")
    if not 256 <= args.max_side <= 4096:
        raise ValueError("max-side must be 256..4096")
    with Image.open(source) as original:
        image = original.convert("RGB")
    source_size = image.size
    crop = rectangle(numbers(args.box), *source_size) if args.box else [0, 0, *source_size]
    for text in args.redact:
        rx0, ry0, rx1, ry1 = rectangle(numbers(text), *source_size)
        ix0, iy0 = max(rx0, crop[0]), max(ry0, crop[1])
        ix1, iy1 = min(rx1, crop[2]), min(ry1, crop[3])
        if ix1 > ix0 and iy1 > iy0:
            image.paste((0, 0, 0), (ix0, iy0, ix1, iy1))
    image = image.crop(crop)
    if max(image.size) > args.max_side:
        image.thumbnail((args.max_side, args.max_side), Image.LANCZOS)
    default_name = os.path.splitext(os.path.basename(source))[0] + "_vision.jpg"
    out = os.path.abspath(args.out or os.path.join(ROOT, "previews", "vision", default_name))
    preview_root = os.path.join(ROOT, "previews")
    if os.path.normcase(os.path.commonpath([preview_root, out])) != os.path.normcase(preview_root):
        raise ValueError("derived vision images must stay under previews/")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    image.save(out, quality=92)
    result = dict(status="PASS", file=os.path.relpath(out, ROOT), source=os.path.relpath(source, ROOT),
                  source_sha256=sha256(source), derived_sha256=sha256(out), source_size=source_size,
                  crop=crop, size=image.size, redactions=len(args.redact), wall_id=args.wall_id,
                  detail="original", external_upload="explicit-only",
                  note="Source unchanged. Review the derived image before uploading it to an external vision API.")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)
