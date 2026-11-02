# -*- coding: utf-8 -*-
"""
sat_grid.py — 사진·위성(옥상) 사진에 좌표 격자를 그려 픽셀 위치를 읽고, 픽셀 → 미터 변환

1) 격자 그리기 (점 좌표를 눈으로 읽을 때)
   python tools/sat_grid.py grid refs/roof.jpg -o previews/roof_grid.png --step 50
   python tools/sat_grid.py grid refs/roof.jpg -o previews/roof_zoom.png --crop 400,300,800,600 --zoom 3 --step 10
     --crop x0,y0,x1,y1 일부만, --zoom 확대 배율, --step 격자 간격(원본 px). 눈금 숫자는 원본 픽셀 좌표

2) 축척 (두 점 거리 = 실제 m)
   python tools/sat_grid.py scale --p 102,330 --q 912,318 --meters 74
     → px/m 와 m/px 출력

3) 건물 로컬 좌표 (네 모서리 → 미터)
   python tools/sat_grid.py frame --corners 120,90,880,96,872,770,114,764 --size 74x89 --pts 300,200;450,610
     corners = 건물 외곽 (정면 왼쪽, 정면 오른쪽, 후면 오른쪽, 후면 왼쪽) 순서 픽셀, size = 실제 가로 x 깊이 m
     pts 를 건물 중심 기준 (x 오른쪽, y 후면 쪽 = +Y) 미터로 변환 → 생성기 좌표에 바로 사용 (정면 = -Y)
     --show out.png 를 주면 변환 격자(2 m 간격, 10 m 굵게)를 사진 위에 그림
"""
import argparse
import math
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)
from extract_texture import homography  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass


def cmd_grid(a):
    im = Image.open(a.image).convert("RGB")
    x0, y0, x1, y1 = (0, 0, im.size[0], im.size[1])
    if a.crop:
        x0, y0, x1, y1 = (int(t) for t in a.crop.split(","))
        im = im.crop((x0, y0, x1, y1))
    z = a.zoom
    im = im.resize((int(im.size[0] * z), int(im.size[1] * z)), Image.NEAREST if z >= 2 else Image.LANCZOS)
    d = ImageDraw.Draw(im)
    step = a.step
    gx = math.ceil(x0 / step) * step
    while gx < x1:
        X = (gx - x0) * z
        major = (gx // step) % 5 == 0
        d.line([(X, 0), (X, im.size[1])], fill=(255, 0, 0) if major else (255, 160, 160), width=1)
        if major:
            d.text((X + 2, 2), str(gx), fill=(255, 255, 0))
        gx += step
    gy = math.ceil(y0 / step) * step
    while gy < y1:
        Y = (gy - y0) * z
        major = (gy // step) % 5 == 0
        d.line([(0, Y), (im.size[0], Y)], fill=(0, 120, 255) if major else (150, 190, 255), width=1)
        if major:
            d.text((2, Y + 2), str(gy), fill=(255, 255, 0))
        gy += step
    im.save(a.out)
    print(f"[grid] {a.out}  {im.size[0]}x{im.size[1]}  (source area {x0},{y0}-{x1},{y1}, grid {step}px, bold every {step * 5}px; labels = source pixels)")


def cmd_scale(a):
    p = np.array([float(t) for t in a.p.split(",")]); q = np.array([float(t) for t in a.q.split(",")])
    dpx = np.linalg.norm(q - p)
    print(f"[scale] {dpx:.1f} px = {a.meters} m -> {dpx / a.meters:.3f} px/m, {a.meters / dpx:.4f} m/px")


def cmd_frame(a):
    v = [float(t) for t in a.corners.replace(";", ",").split(",")]
    C = [(v[i], v[i + 1]) for i in range(0, 8, 2)]
    W, D = (float(t) for t in a.size.lower().split("x"))
    # 정면 왼쪽(-W/2,-D/2), 정면 오른쪽(W/2,-D/2), 후면 오른쪽(W/2,D/2), 후면 왼쪽(-W/2,D/2)
    M = [(-W / 2, -D / 2), (W / 2, -D / 2), (W / 2, D / 2), (-W / 2, D / 2)]
    H = homography(C, M)
    Hi = np.linalg.inv(H)

    def to_m(x, y):
        r = H @ [x, y, 1]
        return r[0] / r[2], r[1] / r[2]

    def to_px(x, y):
        r = Hi @ [x, y, 1]
        return r[0] / r[2], r[1] / r[2]
    if a.pts:
        for tok in a.pts.split(";"):
            x, y = (float(t) for t in tok.split(","))
            mx, my = to_m(x, y)
            print(f"[frame] px ({x:g},{y:g}) -> x {mx:+.2f} m, y {my:+.2f} m")
    if a.show:
        im = Image.open(a.image).convert("RGB") if a.image else None
        if im is None:
            raise SystemExit("--show needs --image")
        d = ImageDraw.Draw(im)
        xs = np.arange(math.ceil(-W / 2 / 2) * 2, W / 2 + 1e-6, 2.0)
        ys = np.arange(math.ceil(-D / 2 / 2) * 2, D / 2 + 1e-6, 2.0)
        for x in xs:
            col = (255, 0, 0) if abs(x % 10) < 1e-6 else (255, 170, 170)
            d.line([to_px(x, -D / 2), to_px(x, D / 2)], fill=col, width=2 if col[1] == 0 else 1)
            if abs(x % 10) < 1e-6:
                d.text(to_px(x, -D / 2), f"x{x:g}", fill=(255, 255, 0))
        for y in ys:
            col = (0, 120, 255) if abs(y % 10) < 1e-6 else (160, 200, 255)
            d.line([to_px(-W / 2, y), to_px(W / 2, y)], fill=col, width=2 if col[0] == 0 else 1)
            if abs(y % 10) < 1e-6:
                d.text(to_px(-W / 2, y), f"y{y:g}", fill=(255, 255, 0))
        d.text(to_px(0, -D / 2), "FRONT (-Y)", fill=(255, 255, 255))
        im.save(a.show)
        print(f"[frame] {a.show}  (2 m grid, bold 10 m, building center = 0,0)")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("grid"); g.add_argument("image"); g.add_argument("-o", "--out", required=True)
    g.add_argument("--step", type=int, default=50); g.add_argument("--crop"); g.add_argument("--zoom", type=float, default=1.0)
    s = sp.add_parser("scale"); s.add_argument("--p", required=True); s.add_argument("--q", required=True)
    s.add_argument("--meters", type=float, required=True)
    f = sp.add_parser("frame"); f.add_argument("--corners", required=True); f.add_argument("--size", required=True)
    f.add_argument("--pts"); f.add_argument("--image"); f.add_argument("--show")
    a = ap.parse_args()
    {"grid": cmd_grid, "scale": cmd_scale, "frame": cmd_frame}[a.cmd](a)


if __name__ == "__main__":
    main()
