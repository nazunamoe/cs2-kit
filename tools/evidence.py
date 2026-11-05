"""Photo evidence ledger: wall-linked U/V observations with source and confidence."""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proj import ROOT  # noqa: E402

PATH = os.path.join(ROOT, "work", "photo_evidence.json")
CONFIDENCE = ("high", "medium", "low")
VIEWS = ("frontal", "oblique", "roof", "detail")


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return dict(photos=data.get("photos", {}), walls=data.get("walls", {}), features=data.get("features", []))


def save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pair(text, name):
    values = [float(v) for v in text.split(",")]
    if len(values) != 2 or values[0] < 0 or values[1] > 1 or values[1] <= values[0]:
        raise ValueError(f"{name} must be increasing normalized coordinates, e.g. 0.1,0.2")
    return values


def add_photo(args):
    path = os.path.abspath(args.photo)
    if not os.path.isfile(path):
        raise ValueError(f"photo not found: {args.photo}")
    if args.view not in VIEWS or args.confidence not in CONFIDENCE:
        raise ValueError("invalid view or confidence")
    data = load()
    rel = os.path.relpath(path, ROOT)
    photo_id = args.photo_id or os.path.splitext(os.path.basename(path))[0]
    data["photos"][photo_id] = dict(file=rel, sha256=sha256(path), view=args.view,
                                    wall_id=args.wall, usable_for=args.use,
                                    occluded=args.occluded, confidence=args.confidence, note=args.note)
    data["walls"].setdefault(args.wall, dict(wall_id=args.wall, photo_ids=[]))
    if photo_id not in data["walls"][args.wall]["photo_ids"]:
        data["walls"][args.wall]["photo_ids"].append(photo_id)
    save(data)
    return dict(status="PASS", photo_id=photo_id, wall_id=args.wall, evidence=os.path.relpath(PATH, ROOT))


def add_feature(args):
    data = load()
    if args.wall not in data["walls"]:
        raise ValueError(f"unknown wall '{args.wall}'; add a photo for this wall first")
    if args.confidence not in CONFIDENCE:
        raise ValueError("invalid confidence")
    record = dict(kind=args.kind, wall_id=args.wall, photo_id=args.photo_id,
                  u=pair(args.u, "u"), v=pair(args.v, "v"), floor=args.floor,
                  confidence=args.confidence, estimated=args.estimated, note=args.note)
    if args.photo_id and args.photo_id not in data["photos"]:
        raise ValueError(f"unknown photo_id '{args.photo_id}'")
    data["features"].append(record)
    save(data)
    return dict(status="PASS", feature=len(data["features"]) - 1, wall_id=args.wall,
                evidence=os.path.relpath(PATH, ROOT))


def validate(data):
    errors = []
    for wall_id, wall in data["walls"].items():
        for photo_id in wall.get("photo_ids", []):
            if photo_id not in data["photos"]:
                errors.append(f"{wall_id}: missing photo {photo_id}")
    for i, feature in enumerate(data["features"]):
        if feature.get("wall_id") not in data["walls"]:
            errors.append(f"feature {i}: unknown wall")
        if feature.get("confidence") not in CONFIDENCE:
            errors.append(f"feature {i}: invalid confidence")
        if not feature.get("estimated") and feature.get("confidence") == "low":
            errors.append(f"feature {i}: low-confidence value should be estimated")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    photo = sub.add_parser("photo")
    photo.add_argument("--photo", required=True)
    photo.add_argument("--photo-id", default="")
    photo.add_argument("--wall", required=True)
    photo.add_argument("--view", choices=VIEWS, default="frontal")
    photo.add_argument("--use", default="floors,bays")
    photo.add_argument("--occluded", default="")
    photo.add_argument("--confidence", choices=CONFIDENCE, default="medium")
    photo.add_argument("--note", default="")
    feature = sub.add_parser("feature")
    feature.add_argument("--wall", required=True)
    feature.add_argument("--kind", required=True)
    feature.add_argument("--u", required=True)
    feature.add_argument("--v", required=True)
    feature.add_argument("--floor", type=int)
    feature.add_argument("--photo-id", default="")
    feature.add_argument("--confidence", choices=CONFIDENCE, default="medium")
    feature.add_argument("--estimated", action="store_true")
    feature.add_argument("--note", default="")
    sub.add_parser("validate")
    args = parser.parse_args()
    if args.cmd == "photo":
        result = add_photo(args)
    elif args.cmd == "feature":
        result = add_feature(args)
    else:
        errors = validate(load())
        result = dict(status="FAIL" if errors else "PASS", errors=errors)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if result["status"] == "FAIL" else 0)


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False))
        sys.exit(1)
