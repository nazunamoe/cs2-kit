# -*- coding: utf-8 -*-
"""Extract still frames from a walkthrough video for photo evidence.

  python tools/video_frames.py --project P --video photos/walk.mp4 \
    --every 2.0 --width 1600 --out photos/frames

Backend: an explicit --ffmpeg, IMAGEIO_FFMPEG_EXE, the imageio-ffmpeg package,
or ffmpeg on PATH. Install one with `pip install imageio-ffmpeg` (no system
ffmpeg needed). Frames are ordinary JPEG photos; the source video is untouched.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proj  # noqa: E402  (consumes --project and chdirs to the project)


def find_ffmpeg(explicit=""):
    if explicit:
        p = os.path.abspath(explicit)
        if os.path.isfile(p):
            return p
        raise SystemExit(f"--ffmpeg is not a file: {explicit}")
    env = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env and os.path.isfile(env):
        return env
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    return None


def ffmpeg_version(exe):
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).splitlines()[0].strip()
    except Exception as ex:
        return f"unavailable ({type(ex).__name__})"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="input video file")
    ap.add_argument("--out", default="photos/frames", help="output folder")
    ap.add_argument("--prefix", default="", help="frame name prefix (default: source stem)")
    ap.add_argument("--every", type=float, default=2.0, help="seconds between frames")
    ap.add_argument("--start", type=float, default=0.0, help="start time in seconds")
    ap.add_argument("--end", type=float, default=None, help="stop time in seconds")
    ap.add_argument("--width", type=int, default=0, help="scale width in px (0 = keep source size)")
    ap.add_argument("--limit", type=int, default=0, help="maximum frames (0 = no limit)")
    ap.add_argument("--quality", type=int, default=2, help="JPEG quality 2..31 (lower is better)")
    ap.add_argument("--ffmpeg", default="", help="ffmpeg executable")
    ap.add_argument("--check", action="store_true", help="report the backend and exit")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    exe = find_ffmpeg(a.ffmpeg)
    if a.check:
        result = {"status": "OK" if exe else "MISSING", "ffmpeg": exe, "version": ffmpeg_version(exe) if exe else None,
                  "install": "pip install imageio-ffmpeg" if not exe else None}
        print(json.dumps(result, ensure_ascii=False) if a.json else
              f"[video] ffmpeg={exe or 'MISSING'}  {ffmpeg_version(exe) if exe else ''}".rstrip())
        return 0 if exe else 2
    if not exe:
        raise SystemExit("ffmpeg not found - pip install imageio-ffmpeg, or pass --ffmpeg")
    if not a.video:
        raise SystemExit("--video is required")
    if not os.path.isfile(a.video):
        raise SystemExit(f"no such video: {a.video}")
    if a.every <= 0:
        raise SystemExit("--every must be positive")
    if a.end is not None and a.end <= a.start:
        raise SystemExit("--end must be after --start")
    if not (0 <= a.quality <= 31):
        raise SystemExit("--quality must be between 0 and 31")

    stem = a.prefix or re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(a.video))[0])
    os.makedirs(a.out, exist_ok=True)
    pattern = os.path.join(a.out, f"{stem}_%04d.jpg")
    filters = [f"fps=1/{a.every:g}"]
    if a.width:
        filters.append(f"scale={a.width}:-2")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    if a.start:
        cmd += ["-ss", f"{a.start:g}"]
    cmd += ["-i", a.video]
    if a.end is not None:
        cmd += ["-t", f"{a.end - a.start:g}"]
    cmd += ["-vf", ",".join(filters), "-q:v", str(a.quality)]
    if a.limit:
        cmd += ["-frames:v", str(a.limit)]
    cmd.append(pattern)
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    if a.dry_run:
        result = {"status": "DRY_RUN", "command": printable, "out": a.out}
        print(json.dumps(result, ensure_ascii=False) if a.json else f"[video] {printable}")
        return 0

    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0:
        detail = (run.stderr or run.stdout or "").strip().splitlines()
        raise SystemExit("ffmpeg failed: " + (detail[-1] if detail else f"exit {run.returncode}"))
    frames = sorted(glob.glob(os.path.join(a.out, f"{stem}_*.jpg")))
    if not frames:
        raise SystemExit("ffmpeg produced no frames - check --start/--end and the video")
    result = {"status": "OK", "video": a.video, "ffmpeg": exe, "out": a.out,
              "every": a.every, "frames": len(frames), "first": frames[0], "last": frames[-1],
              "command": printable}
    print(json.dumps(result, ensure_ascii=False) if a.json else
          f"[video] {len(frames)} frames -> {a.out} ({os.path.basename(frames[0])} .. {os.path.basename(frames[-1])})")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
