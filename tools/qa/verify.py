"""병렬 검증 — 빌드 한 번 뒤에 나머지 검사를 동시에 돌려 한 번에 요약한다 (순서대로 돌릴 때의 약 절반 시간).

검증 도구(tools/qa/). 보고 전과 단계가 끝날 때마다 `cycle.py ... && lod_check ...` 대신 이것 하나.
  python tools/qa/verify.py [--label 단계] [--generator <이름>_cs2.py]

순서
  1. python tools/cycle.py <생성기> --no-render        (빌드 + 규격 검사: 반드시 먼저, 실패하면 여기서 멈춤)
  2. 아래를 동시에 (스레드): lod_check · 미리보기 렌더(+ progress 기록) · cmp_cam(verify.json 의 shots) ·
     photo_refs.json 이 있으면 tile_compare 와 photo_check
  3. 한 줄씩 요약 + 마지막 줄  VERIFY PASS|FAIL   (FAIL = 빌드 오류 또는 LODCHECK FAIL. cmp_cam WARN·타일 결과는 참고)

옵션 (기본 동작은 그대로)
  --fast        반복용: LOD 검사는 --quick(16시점, ~5 s), 미리보기 렌더 생략. 마지막 줄이 `VERIFY FAST` 이고 **보고용이 아니다**
                (보고 전에는 --fast 없이 전체 LODCHECK PASS 를 받는다).
  --all-shots   meta 의 사진 전부를 cmp_all.py 로(Blender 1회, 표 + 접촉 시트 work/chk_all/sheet_*.png). 기본 꺼짐.
점수 기록: 매번 work/chk/scores.json 에 IoU·LOD 최대 구멍·tris 를 쌓고, 같은 키의 직전 값보다 나빠지면 `SCORES REGRESS ...` 를 낸다
  (회귀 감시용이며 "사진과 같다"의 증거가 아니다 - tools/qa/scores.py).

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
import re
import shutil
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> 키트 루트
sys.path.insert(0, os.path.join(KIT, "tools"))
import proj  # noqa: E402,F401  (작업 폴더 = 활성 프로젝트)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scores  # noqa: E402

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
    ap.add_argument("--fast", action="store_true", help="반복용: lod_check --quick, 미리보기 생략 (보고용 아님)")
    ap.add_argument("--all-shots", action="store_true", help="meta 사진 전부를 cmp_all.py 로 비교")
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
    jobs = {"lod_check": [PY, os.path.join(KIT, "tools", "qa", "lod_check.py"), adir] + (["--quick"] if a.fast else [])}
    if not a.fast:
        jobs["render"] = [PY, os.path.join(KIT, "tools", "render.py"), adir, "-o", os.path.join("previews", asset + ".png")]
    if a.all_shots:
        meta = cfg.get("meta") or (cfg.get("shots") or [{}])[0].get("meta")
        if not meta:
            raise SystemExit("VERIFY FAIL --all-shots needs verify.json 'meta' (or shots[0].meta)")
        if os.path.exists("work/chk_all/summary.json"):
            os.remove("work/chk_all/summary.json")          # 이번 실행이 실패하면 옛 값이 새 기록으로 들어가지 않게
        jobs["cmp_all"] = [PY, os.path.join(KIT, "tools", "qa", "cmp_all.py"), "--asset", adir, "--meta", meta,
                           "--ground", str(cfg.get("ground", 74.51))]
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
        key = {"lod_check": "LODCHECK", "cmp_cam": "CMPCAM", "cmp_all": "CMPALL"}.get(k.split("#")[0])
        line = last(o, key)
        if k == "render":
            progress_copy(asset, a.label)
            line = "previews/%s.png + progress/latest.png" % asset
        if k == "lod_check" and ("LODCHECK PASS" not in line and "LODCHECK QUICK ok" not in line):
            fail = True
        print("[%-12s %4.0fs] %s" % (k, d, line[:230]))
    # 점수 기록 + 회귀 경고
    rec = dict(label=a.label, mode="fast" if a.fast else "full", asset=asset, shots={}, scales={})
    m = re.search(r"tris (\d+)/LOD1 (\d+)/LOD2 (\d+)", out)
    if m:
        rec["tris"] = dict(main=int(m.group(1)), lod1=int(m.group(2)), lod2=int(m.group(3)))
    ll = results["lod_check"][0]
    mm = re.findall(r"(main|lod1|lod2) max ([\d.]+)%", ll)
    if mm:
        rec["lod"] = dict({g: float(v) for g, v in mm}, mode="quick" if a.fast else "full")
    for k in jobs:
        if k.startswith("cmp_cam"):
            mi = re.search(r"shot=(\S+).*? iou=([\d.]+)", last(results[k][0], "CMPCAM"))
            if mi:
                rec["shots"]["cmp_cam:" + mi.group(1)] = float(mi.group(2))
    if "cmp_all" in jobs:
        sj = "work/chk_all/summary.json"
        if results["cmp_all"][2] == 0 and os.path.exists(sj):   # 성공한 이번 실행의 결과만 기록
            summ = json.load(open(sj, encoding="utf-8"))
            if summ.get("asset") == asset + ".blend" or summ.get("asset", "").startswith(asset):
                for f, r in summ["shots"].items():
                    rec["shots"]["all:" + f] = r["iou"]
                    rec["scales"]["all:" + f] = r["scale"]
            else:
                print("SCORES note: cmp_all summary is for another asset, not recorded")
        else:
            print("SCORES note: cmp_all failed (rc=%s), its values were NOT recorded" % results["cmp_all"][2])
    warns = scores.append(os.path.join("work", "chk", "scores.json"), rec)
    for w in warns:
        print("SCORES " + w)
    print("SCORES %s (%d values recorded -> work/chk/scores.json)" % ("REGRESS %d" % len(warns) if warns else "ok", len(rec["shots"]) + (1 if "lod" in rec else 0)))
    verdict = ("FAST-FAIL" if fail else "FAST") if a.fast else ("FAIL" if fail else "PASS")
    print("VERIFY %s  total %.0fs  asset=%s%s" % (verdict, time.time() - t0, asset,
          "  (quick LOD, no preview: NOT valid for report - run without --fast)" if a.fast else ""))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
