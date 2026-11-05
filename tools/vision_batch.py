# -*- coding: utf-8 -*-
"""Create wall/detail crops for vision review in one batch.

  python tools/vision_batch.py --project P --asset output/<asset> --refs photo_refs.json
  python tools/vision_batch.py --project P --photo photos/front.jpg \
      --wall-box edge_06=120,80,760,1500 --wall-box edge_10=800,80,1400,1500

Sources are never modified. Crops stay under previews/. Explicit wall boxes are
useful when a 3D view is a corner view and a pure facade rectangle is unavailable.
"""
import argparse
import hashlib
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_box(text):
    values = [int(v) for v in text.split(",")]
    if len(values) != 4:
        raise ValueError("box must be x0,y0,x1,y1")
    return values


def angle_diff(a, b):
    return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asset", default="", help="output/<asset> for wall metadata / angle warnings")
    ap.add_argument("--refs", default="photo_refs.json")
    ap.add_argument("--photo", default="", help="one source photo for --wall-box entries")
    ap.add_argument("--wall-box", action="append", default=[], metavar="WALL=x0,y0,x1,y1")
    ap.add_argument("--out", default="work/vision_batch.json")
    ap.add_argument("--crop-dir", default="previews/vision/batch")
    ap.add_argument("--max-side", type=int, default=1300)
    a = ap.parse_args()

    walls = {}
    if a.asset:
        man_path = a.asset if os.path.isabs(a.asset) else os.path.join(proj.ROOT, a.asset)
        man_path = os.path.join(man_path, "manifest.json")
        if os.path.isfile(man_path):
            man = json.load(open(man_path, encoding="utf-8"))
            walls = ((man.get("metadata") or {}).get("walls") or {})

    jobs = []
    if a.wall_box:
        if not a.photo:
            raise SystemExit("--wall-box requires --photo")
        for item in a.wall_box:
            if "=" not in item:
                raise SystemExit(f"bad --wall-box: {item}")
            wall, box = item.split("=", 1)
            jobs.append(dict(photo=a.photo, wall_id=wall, box=parse_box(box), source="explicit"))
    else:
        refs_path = a.refs if os.path.isabs(a.refs) else os.path.join(proj.ROOT, a.refs)
        if not os.path.isfile(refs_path):
            raise SystemExit(f"no refs: {a.refs} (use --wall-box for explicit crops)")
        refs = json.load(open(refs_path, encoding="utf-8"))
        ref_dir = os.path.dirname(refs_path)
        for ref in refs.get("facades", []):
            photo = ref.get("file")
            corners = ref.get("corners")
            wall_id = ref.get("wall_id") or ref.get("name") or ref.get("side")
            if not photo or not corners or not wall_id:
                continue
            photo_path = photo if os.path.isabs(photo) else os.path.join(ref_dir, photo)
            if a.photo and os.path.normcase(os.path.abspath(a.photo)) != os.path.normcase(photo_path):
                continue
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            jobs.append(dict(photo=photo_path, wall_id=wall_id,
                             box=[int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                             source=os.path.relpath(refs_path, proj.ROOT), ref=ref))

    if not jobs:
        raise SystemExit("no crops requested")

    crop_dir = a.crop_dir if os.path.isabs(a.crop_dir) else os.path.join(proj.ROOT, a.crop_dir)
    os.makedirs(crop_dir, exist_ok=True)
    records = []
    warnings = []
    for job in jobs:
        source = os.path.abspath(job["photo"])
        if not os.path.isfile(source):
            warnings.append(f"{job['wall_id']}: photo not found {job['photo']}")
            continue
        with Image.open(source) as im:
            im = im.convert("RGB")
            W, H = im.size
            x0, y0, x1, y1 = job["box"]
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(W, x1), min(H, y1)
            if x1 <= x0 or y1 <= y0:
                warnings.append(f"{job['wall_id']}: empty crop {job['box']}")
                continue
            crop = im.crop((x0, y0, x1, y1))
            if max(crop.size) > a.max_side:
                crop.thumbnail((a.max_side, a.max_side), Image.LANCZOS)
            safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(job["wall_id"]))
            out_path = os.path.join(crop_dir, safe + "_vision.jpg")
            crop.save(out_path, quality=92)
        ref = job.get("ref", {})
        az = ref.get("photo_azimuth_deg", ref.get("yaw_deg"))
        wall = walls.get(job["wall_id"], {})
        if az is not None and wall.get("normal_deg") is not None:
            diff = angle_diff(az, wall["normal_deg"])
            if diff > 15.0:
                warnings.append(f"{job['wall_id']}: photo {az} deg vs wall {wall['normal_deg']} deg "
                                f"= {diff:.1f} deg corner view; low confidence")
        records.append(dict(wall_id=job["wall_id"], source=os.path.relpath(source, proj.ROOT),
                            source_sha256=sha256(source), crop=job["box"],
                            derived=os.path.relpath(out_path, proj.ROOT),
                            derived_sha256=sha256(out_path), size=list(crop.size),
                            source_kind=job["source"], external_upload="explicit-only"))
    out = a.out if os.path.isabs(a.out) else os.path.join(proj.ROOT, a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(status="PASS" if records else "FAIL", crops=records, warnings=warnings), f,
                  ensure_ascii=False, indent=1)
    print(f"[vision_batch] {len(records)} crop(s) -> {os.path.relpath(out, proj.ROOT)}")
    for w in warnings:
        print(f"  WARN {w}")
    sys.exit(0 if records else 2)


if __name__ == "__main__":
    main()
