"""Compatibility wrapper for the shared cycle gate plus optional same-camera checks."""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(KIT, "tools"))
import proj  # noqa: E402,F401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scores  # noqa: E402

PY = sys.executable


def run(cmd):
    started = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (result.stdout or "") + (result.stderr or ""), time.time() - started, result.returncode


def last(out, key=None):
    lines = [line for line in out.strip().splitlines() if (key in line if key else line.strip())]
    return lines[-1].strip() if lines else "(no output)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="verify")
    parser.add_argument("--generator", default=None)
    parser.add_argument("--fast", action="store_true", help="shared quick OBJ/check gate; not valid for a final report")
    parser.add_argument("--all-shots", action="store_true")
    args = parser.parse_args()
    cfg = json.load(open("verify.json", encoding="utf-8")) if os.path.exists("verify.json") else {}
    generator = args.generator or cfg.get("generator") or (sorted(glob.glob("*_cs2.py"), key=os.path.getmtime) or [None])[-1]
    if not generator:
        raise SystemExit("VERIFY FAIL no *_cs2.py; pass --generator explicitly")
    mode = "quick" if args.fast else "final"
    started = time.time()
    out, _, code = run([PY, os.path.join(KIT, "tools", "cycle.py"), generator, "--mode", mode,
                        "--json", "--label", args.label])
    for line in out.splitlines():
        if line.startswith(("[1/3", "[2/3", "[3/3", "GATE ", "RESULT ", "[json]", "   ERROR", "   PHOTO_MISMATCH")):
            print(line)
    gate = None
    for line in out.splitlines():
        if line.startswith("[json] "):
            path = line[7:].strip()
            with open(path, encoding="utf-8") as f:
                gate = json.load(f)
    if gate is None:
        print(out[-4000:])
        print("VERIFY FAIL (no gate.json)")
        sys.exit(1)
    if gate["status"] != "PASS":
        print(f"VERIFY {gate['status']} total {time.time() - started:.0f}s asset={gate.get('asset')}")
        sys.exit(code)
    asset = gate["asset"]
    asset_dir = os.path.join("output", asset)
    jobs = {}
    if args.all_shots:
        meta = cfg.get("meta") or (cfg.get("shots") or [{}])[0].get("meta")
        if not meta:
            raise SystemExit("VERIFY FAIL --all-shots needs verify.json 'meta'")
        if os.path.exists("work/chk_all/summary.json"):
            os.remove("work/chk_all/summary.json")
        jobs["cmp_all"] = [PY, os.path.join(KIT, "tools", "qa", "cmp_all.py"), "--asset", asset_dir,
                           "--meta", meta, "--ground", str(cfg.get("ground", 74.51))]
    for i, shot in enumerate(cfg.get("shots", [])):
        cmd = [PY, os.path.join(KIT, "tools", "qa", "cmp_cam.py"), "--asset", asset_dir,
               "--photo", shot["photo"], "--meta", shot["meta"], "--ground", str(shot.get("ground", cfg.get("ground", 74.51)))]
        for name, box in shot.get("crops", {}).items():
            cmd += ["--crop", "%s:%s" % (name, ",".join(str(v) for v in box))]
        jobs["cmp_cam#%d" % i] = cmd
    results = {}
    if jobs:
        with cf.ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
            futures = {executor.submit(run, cmd): name for name, cmd in jobs.items()}
            for future in cf.as_completed(futures):
                results[futures[future]] = future.result()
    for name in jobs:
        output, duration, _ = results[name]
        key = "CMPALL" if name == "cmp_all" else "CMPCAM"
        print("[%-12s %4.0fs] %s" % (name, duration, last(output, key)[:230]))

    record = dict(label=args.label, mode="fast" if args.fast else "full", asset=asset, shots={}, scales={})
    record["tris"] = gate.get("check", {}).get("info", {}).get("tris", {})
    lod_line = gate.get("lod", {}).get("line") or ""
    matches = re.findall(r"(main|lod1|lod2) max ([\d.]+)%", lod_line)
    if matches:
        record["lod"] = dict({name: float(value) for name, value in matches}, mode="full")
    for name in jobs:
        if name.startswith("cmp_cam"):
            match = re.search(r"shot=(\S+).*? iou=([\d.]+)", last(results[name][0], "CMPCAM"))
            if match:
                record["shots"]["cmp_cam:" + match.group(1)] = float(match.group(2))
    if "cmp_all" in jobs:
        summary_path = "work/chk_all/summary.json"
        if results["cmp_all"][2] == 0 and os.path.exists(summary_path):
            summary = json.load(open(summary_path, encoding="utf-8"))
            for filename, values in summary.get("shots", {}).items():
                record["shots"]["all:" + filename] = values["iou"]
                record["scales"]["all:" + filename] = values["scale"]
        else:
            print("SCORES note: cmp_all failed; its values were NOT recorded")
    warnings = scores.append(os.path.join("work", "chk", "scores.json"), record)
    for warning in warnings:
        print("SCORES " + warning)
    print("SCORES %s (%d values recorded -> work/chk/scores.json)" %
          ("REGRESS %d" % len(warnings) if warnings else "ok", len(record["shots"]) + (1 if "lod" in record else 0)))
    verdict = "FAST" if args.fast else "PASS"
    suffix = "  (quick OBJ/check: NOT valid for report)" if args.fast else ""
    print("VERIFY %s total %.0fs asset=%s%s" % (verdict, time.time() - started, asset, suffix))


if __name__ == "__main__":
    main()
