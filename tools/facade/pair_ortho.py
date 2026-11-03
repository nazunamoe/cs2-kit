# -*- coding: utf-8 -*-
"""스캔 정사영 | 모델 정사영을 같은 축척으로 나란히 (또는 위아래로) 놓는다. 면 하나를 고칠 때마다 쓴다.

  python tools/facade/pair_ortho.py --blend output/<에셋>/<에셋>.blend --scan work/e101/s_y000_v000.png \
      --view 0 --a0 -24.1 --a1 24.1 --z0 -1 --z1 97 --rows 1150,1450 --cols 480,960 -o work/cmp/front.png [--auto-shift] [--zoom 4]

- 모델 그림은 modelelev.py(Blender)로 만든다. --view = 카메라 yaw(0: -Y 쪽에서, 180: +Y 쪽, 회전한 동체는 -45 처럼).
  view 180 은 가로 범위의 부호가 월드 x 와 반대다(월드 x = -a): 뒷면은 --a0 -(x최대) --a1 -(x최소).
- 스캔 그림과 모델 그림의 가로 어긋남은 열 점유 프로파일 상관으로 찾는다(--auto-shift): 회전한 동체에서 30 px(1.5 m) 어긋났던 적이 있다.
  --shift N 으로 직접 줄 수도 있다. 출력에 shift 와 상관값이 나온다(상관 0.7 이상이면 같은 면).
- 스캔 그림 위 끝 z 는 FACADE_ZTOP(기본 97), 축척은 --ppm(기본 20). 그림 높이 = (z1-z0)*ppm 이 스캔 그림과 같아야 한다.
- 비교 그림은 항상 '왼쪽 = 스캔, 오른쪽 = 모델'. 눈으로 창 수·높이·띠 위치를 본다.

여러 면 일괄 (--frames) — 옛 pairE.py / pair.py / pair2.py / cmp.py 를 대체
  python tools/facade/pair_ortho.py --blend output/<에셋>/<에셋>.blend --frames work/scanframe_105.json --dong 105 [--views 0,90,180,270] [--z0 -1 --z1 97]
  scanframe 파일(JSON): {"0": [a0, a1] 또는 [a0, a1, ia0], "90": ..., "180": ..., "270": ...,
                        "ymin": 모델 앞면 y(기본 0), "dz": 생성기 z = 스캔 z - dz(기본 0), "ztop": 스캔 그림 위 끝 z(기본 97),
                        "z0": 모델 z 시작(기본 -1), "z1": 모델 z 끝(기본 ztop)}
  ia0 = 스캔 그림 왼쪽 끝의 a (없으면 스캔 그림 가로 = a0..a1 전체). 스캔 그림은 --scan-dir(기본 work/e<dong>)/v<view>.png.
  결과: <outdir 기본 work>/m<dong>_<view>.png (모델), pair<dong>_<view>.png (왼쪽 스캔 | 오른쪽 모델).
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import proj  # noqa: E402,F401  (작업 폴더 = 활성 프로젝트: work/, output/ 상대 경로)


def find_blender():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    for p in (os.path.join(HERE, "..", "..", "tools", "blender_path.txt"),):
        if os.path.exists(p):
            t = open(p, encoding="utf-8").read().strip()
            if t and os.path.exists(t):
                return t
    for p in (r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
              r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
              r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"):
        if os.path.exists(p):
            return p
    return "blender"


def occupancy(a):
    bg = a[5, 5]
    return (np.abs(a - bg) > 12).sum(axis=0).astype(float)


def best_shift(model, scan, span=400):
    pm, ps = occupancy(model), occupancy(scan)
    w = min(len(pm), len(ps))
    best, bk = -2.0, 0
    for k in range(-span, span):
        r = np.roll(pm, k)[:w]
        if r.std() < 1e-6 or ps[:w].std() < 1e-6:
            continue
        c = np.corrcoef(r, ps[:w])[0, 1]
        if c > best:
            best, bk = c, k
    return bk, best


def run_frames(a):
    """여러 면 일괄: scanframe JSON 의 면마다 모델 정사영을 렌더하고 스캔 정사영(v<view>.png)과 좌우로 붙인다."""
    import json
    fr = json.load(open(a.frames, encoding="utf-8"))
    dz, ztop, ymin = fr.get("dz", 0.0), fr.get("ztop", 97.0), fr.get("ymin", 0.0)
    z0 = a.z0 if a.z0 is not None else fr.get("z0", -1.0)
    z1 = a.z1 if a.z1 is not None else fr.get("z1", ztop)
    sdir = a.scan_dir or os.path.join("work", "e" + a.dong)
    os.makedirs(a.outdir, exist_ok=True)
    ppm = a.ppm
    for v in a.views.split(","):
        rng = fr[v]
        a0, a1 = rng[0], rng[1]
        mo = os.path.abspath(os.path.join(a.outdir, "m%s_%s.png" % (a.dong, v)))
        cmd = [find_blender(), "-b", os.path.abspath(a.blend), "-P", os.path.join(HERE, "modelelev.py"), "--",
               v, str(ppm), str(a0), str(a1), str(z0), str(z1), mo, str(ymin)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if not os.path.exists(mo):
            sys.exit("model render failed for view %s (Blender path? set env BLENDER)" % v)
        s_img = Image.open(os.path.join(sdir, "v%s.png" % v)).convert("RGB")
        x0, x1 = 0, s_img.width
        if len(rng) > 2:
            x0, x1 = int((a0 - rng[2]) * ppm), int((a1 - rng[2]) * ppm)
        sc = s_img.crop((x0, int((ztop - z1 - dz) * ppm), x1, int((ztop - z0 - dz) * ppm)))
        m = Image.open(mo).convert("RGB")
        out = Image.new("RGB", (sc.width + m.width + 12, max(sc.height, m.height)), "white")
        out.paste(sc, (0, 0))
        out.paste(m, (sc.width + 12, 0))
        op = os.path.join(a.outdir, "pair%s_%s.png" % (a.dong, v))
        out.save(op)
        print("view", v, out.size, "->", op, "(left = scan, right = model)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--scan")
    ap.add_argument("--view", type=float)
    ap.add_argument("--ppm", type=float, default=20.0)
    ap.add_argument("--a0", type=float)
    ap.add_argument("--a1", type=float)
    ap.add_argument("--z0", type=float, default=None)
    ap.add_argument("--z1", type=float, default=None)
    ap.add_argument("--frames", help="scanframe JSON: 여러 면 일괄 모드 (위 설명)")
    ap.add_argument("--dong", default="")
    ap.add_argument("--views", default="0,90,180,270")
    ap.add_argument("--scan-dir", default=None)
    ap.add_argument("--outdir", default="work")
    ap.add_argument("--rows", help="r0,r1 : 비교할 그림 행 범위 (위 끝 = 0)")
    ap.add_argument("--cols", help="c0,c1 : 비교할 열 범위")
    ap.add_argument("--auto-shift", action="store_true")
    ap.add_argument("--shift", type=int, default=0)
    ap.add_argument("--zoom", type=int, default=1)
    ap.add_argument("--stack", action="store_true", help="위아래로 (기본은 좌우)")
    ap.add_argument("--yoff", type=float, default=0.0)
    ap.add_argument("-o")
    a = ap.parse_args()
    if a.frames:
        return run_frames(a)
    for k in ("scan", "view", "a0", "a1", "o"):
        if getattr(a, k) is None:
            sys.exit("--%s is required (or use --frames)" % k)
    if a.z0 is None:
        a.z0 = -1.0
    if a.z1 is None:
        a.z1 = float(os.environ.get("FACADE_ZTOP", 97))
    tmp = os.path.abspath(a.o) + ".model.png"
    cmd = [find_blender(), "-b", os.path.abspath(a.blend), "-P", os.path.join(HERE, "modelelev.py"), "--",
           str(int(a.view)) if a.view == int(a.view) else str(a.view), str(a.ppm), str(a.a0), str(a.a1), str(a.z0), str(a.z1), tmp,
           str(a.yoff)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if not os.path.exists(tmp):
        sys.exit("model render failed (Blender path? set env BLENDER)")
    model = Image.open(tmp).convert("RGB")
    scan = Image.open(a.scan).convert("RGB")
    sh = a.shift
    if a.auto_shift:
        sh, c = best_shift(np.asarray(model.convert("L"), float), np.asarray(scan.convert("L"), float))
        print("auto shift %d px (%.2f m) correlation %.3f%s" % (sh, sh / a.ppm, c, "" if c >= 0.7 else "  <- low: other face / wrong range?"))
    canvas = Image.new("RGB", scan.size, (0, 0, 0))
    canvas.paste(model, (sh, 0))
    r0, r1 = (int(v) for v in a.rows.split(",")) if a.rows else (0, scan.height)
    c0, c1 = (int(v) for v in a.cols.split(",")) if a.cols else (0, scan.width)
    A = scan.crop((c0, r0, c1, r1))
    B = canvas.crop((c0, r0, c1, r1))
    if a.zoom != 1:
        A = A.resize((A.width * a.zoom, A.height * a.zoom), Image.LANCZOS)
        B = B.resize((B.width * a.zoom, B.height * a.zoom), Image.LANCZOS)
    if a.stack:
        o = Image.new("RGB", (A.width, A.height * 2 + 10), (255, 0, 0))
        o.paste(A, (0, 0)); o.paste(B, (0, A.height + 10))
    else:
        o = Image.new("RGB", (A.width * 2 + 10, A.height), (255, 0, 0))
        o.paste(A, (0, 0)); o.paste(B, (A.width + 10, 0))
    o.save(a.o)
    os.remove(tmp)
    print("WROTE", a.o, o.size, "(left = scan, right = model)")


if __name__ == "__main__":
    main()
