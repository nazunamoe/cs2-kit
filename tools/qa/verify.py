"""병렬 검증 — 빌드 한 번 뒤에 나머지 검사를 동시에 돌려 한 번에 요약한다 (순서대로 돌릴 때의 약 절반 시간).

검증 도구(tools/qa/). 보고 전과 단계가 끝날 때마다 `cycle.py ... && lod_check ...` 대신 이것 하나.
  python tools/qa/verify.py [--label 단계] [--generator <이름>_cs2.py]

순서
  1. python tools/cycle.py <생성기> --no-render        (빌드 + 규격 검사: 반드시 먼저, 실패하면 여기서 멈춤)
  2. 아래를 동시에 (스레드): lod_check · 미리보기 렌더(+ progress 기록) · cmp_cam(verify.json 의 shots) ·
     photo_refs.json 이 있으면 tile_compare 와 photo_check
  3. 한 줄씩 요약 + 마지막 줄  VERIFY PASS|FAIL   (FAIL = 빌드 오류 또는 LODCHECK FAIL. cmp_cam WARN·타일 결과는 참고)

프로젝트 설정(선택): projects/<이름>/verify.json
  {"generator": "x_cs2.py", "ground": 74.51,
   "shots": [{"photo": "photos/101_side1.png", "meta": "photos/101_meta.json",
              "crops": {"roofL": [1260,300,1760,640], "roofR": [1780,600,2540,900]}}]}
"""
import argparse
import concurrent.futures as cf
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> 키트 루트
sys.path.insert(0, os.path.join(KIT, "tools"))
import proj  # noqa: E402,F401  (작업 폴더 = 활성 프로젝트)

PY = sys.executable


def run(cmd):
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or ""), time.time() - t, r.returncode


def last(out, key=None):
    lines = [l for l in out.strip().splitlines() if (key in l if key else l.strip())]
    return lines[-1].strip() if lines else "(no output)"


def progress_copy(asset, label):
    src = os.path.join("previews", asset + ".png")
    if not os.path.exists(src):
        return
    d = os.path.join("previews", "progress", asset)
    os.makedirs(d, exist_ok=True)
    n = len([f for f in os.listdir(d) if f.endswith(".png")]) + 1
    shutil.copy(src, os.path.join(d, "%03d_%s_%s.png" % (n, datetime.datetime.now().strftime("%H%M%S"), label)))
    shutil.copy(src, os.path.join("previews", "progress", "latest.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="verify")
    ap.add_argument("--generator", default=None)
    a = ap.parse_args()
    cfg = json.load(open("verify.json", encoding="utf-8")) if os.path.exists("verify.json") else {}
    gen = a.generator or cfg.get("generator") or (sorted(glob.glob("*_cs2.py"), key=os.path.getmtime) or [None])[-1]
    if not gen:
        raise SystemExit("VERIFY FAIL no *_cs2.py in " + os.getcwd())
    t0 = time.time()
    out, dt, rc = run([PY, os.path.join(KIT, "tools", "cycle.py"), gen, "--no-render"])
    res = last(out, "RESULT")
    print("[build %4.0fs] %s" % (dt, res))
    for l in out.splitlines():
        if l.strip().startswith("ERROR") or "PHOTO_MISMATCH" in l:
            print("   " + l.strip()[:200])
    if "RESULT PASS" not in res:
        print("VERIFY FAIL (build/check)")
        sys.exit(1)
    asset = res.split("asset=")[1].split()[0]
    adir = os.path.join("output", asset)
    jobs = {"lod_check": [PY, os.path.join(KIT, "tools", "qa", "lod_check.py"), adir],
            "render": [PY, os.path.join(KIT, "tools", "render.py"), adir, "-o", os.path.join("previews", asset + ".png")]}
    for i, s in enumerate(cfg.get("shots", [])):
        cmd = [PY, os.path.join(KIT, "tools", "qa", "cmp_cam.py"), "--asset", adir, "--photo", s["photo"], "--meta", s["meta"],
               "--ground", str(s.get("ground", cfg.get("ground", 74.51)))]
        for nm, box in s.get("crops", {}).items():
            cmd += ["--crop", "%s:%s" % (nm, ",".join(str(v) for v in box))]
        jobs["cmp_cam#%d" % i] = cmd
    if os.path.exists("photo_refs.json"):
        jobs["photo_check"] = [PY, os.path.join(KIT, "tools", "photo_check.py"), adir]
        jobs["tile_compare"] = [PY, os.path.join(KIT, "tools", "tile_compare.py"), adir]
    fail = False
    with cf.ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
        futs = {ex.submit(run, c): k for k, c in jobs.items()}
        results = {}
        for f in cf.as_completed(futs):
            results[futs[f]] = f.result()
    for k in jobs:
        o, d, r = results[k]
        key = {"lod_check": "LODCHECK", "cmp_cam": "CMPCAM"}.get(k.split("#")[0])
        line = last(o, key)
        if k == "render":
            progress_copy(asset, a.label)
            line = "previews/%s.png + progress/latest.png" % asset
        if k == "lod_check" and "LODCHECK PASS" not in line:
            fail = True
        print("[%-12s %4.0fs] %s" % (k, d, line[:230]))
    print("VERIFY %s  total %.0fs  asset=%s" % ("FAIL" if fail else "PASS", time.time() - t0, asset))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
