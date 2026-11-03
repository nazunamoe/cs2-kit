# elevstat.py - 스캔 정사영(elevation) 그림 한 장을 줄·열·띠로 읽는 작은 통계 4종 (옛 wincols.py / profile.py / runs.py / rows.py 를 합침)
#
#   python tools/facade/elevstat.py cols    <png> <ppm> <x_origin> <x0_m> <x1_m> <z0_m> <z1_m> <z_top_of_image> [thr=105]
#       z 구간 평균 밝기로 가로 방향 어두운(창)/밝은(벽) 구간 목록 (m)                      [옛 wincols.py]
#   python tools/facade/elevstat.py profile <png> <row|col> <index> <ppm> <origin_m> [min_run_px=4]
#       한 줄(행 또는 열)의 색 클래스 구간 W 흰 / K 어두움·유리 / B 갈색 / G 회색 + 평균색   [옛 profile.py]
#   python tools/facade/elevstat.py runs    <png> <a0> <z_list,comma> <z_wall> [ztop=141]
#       20 px/m 정사영의 여러 높이 z 에서 어두운 구간(창)과 벽 색 구간                      [옛 runs.py]
#   python tools/facade/elevstat.py rows    <png> <h0> <z1> <ppm> <x0> <x1> [thr=0.5]
#       벽 열 x0..x1 안의 어두운 가로 줄(창 줄) 목록과 층 간격                              [옛 rows.py]
import sys

import numpy as np
from PIL import Image


def cols(argv):
    f, ppm, xorg = argv[0], float(argv[1]), float(argv[2])
    x0, x1, z0, z1, ztop = [float(v) for v in argv[3:8]]
    thr = float(argv[8]) if len(argv) > 8 else 105.0
    im = np.array(Image.open(f).convert("RGB")).astype(int)
    ya = int((ztop - max(z0, z1)) * abs(ppm))
    yb = int((ztop - min(z0, z1)) * abs(ppm))
    pa, pb = sorted(int((v - xorg) * ppm) for v in (x0, x1))
    band = im[ya:yb, pa:pb]
    lum = band.mean(axis=2).mean(axis=0)
    dark = lum < thr
    runs = []
    s = 0
    for i in range(1, len(dark) + 1):
        if i == len(dark) or dark[i] != dark[s]:
            runs.append((s + pa, i + pa, dark[s]))
            s = i
    print("cols in m (x = xorg + px/ppm):")
    for a, b, d in runs:
        if (b - a) >= 12:
            print("  %7.2f..%7.2f  %5.2f m  %s" % (xorg + a / ppm, xorg + b / ppm, abs((b - a) / ppm), "WINDOW" if d else "wall"))


def _cls(c):
    r, g, b = c
    if r < 25 and g < 25 and b < 25:
        return "."
    if r - b > 22 and r > 70:
        return "B"
    mx, mn = max(r, g, b), min(r, g, b)
    lum = 0.3 * r + 0.6 * g + 0.1 * b
    if lum < 95:
        return "K"
    if lum > 172 and mx - mn < 30:
        return "W"
    return "G"


def profile(argv):
    f, mode, idx, ppm, origin = argv[0], argv[1], int(argv[2]), float(argv[3]), float(argv[4])
    minrun = int(argv[5]) if len(argv) > 5 else 4
    im = np.array(Image.open(f).convert("RGB")).astype(int)
    line = im[idx] if mode == "row" else im[:, idx]
    labels = [_cls(c) for c in line]
    runs = []
    s = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[s]:
            runs.append((s, i, labels[s]))
            s = i
    merged = []
    for a, b, k in runs:
        # (옛 profile.py 는 배경 '.' 을 튜플로 돌려줘 앞 구간에 합치는 분기가 한 번도 실행되지 않았다 → 같은 결과를 내도록 그 분기를 뺐다)
        if merged and (b - a) < minrun:
            continue
        else:
            merged.append((a, b, k))
    for a, b, k in merged:
        seg = line[a:b]
        c = seg.mean(axis=0).astype(int)
        print("%7.2f..%7.2f m  %5.2f  %s  #%02x%02x%02x" % (origin + a / ppm, origin + b / ppm, abs((b - a) / ppm), k, c[0], c[1], c[2]))


def runs(argv):
    f, a0, zs, zw = argv[0], float(argv[1]), [float(v) for v in argv[2].split(",")], float(argv[3])
    ztop = float(argv[4]) if len(argv) > 4 else 141.0
    im = np.asarray(Image.open(f).convert("RGB")).astype(float)
    L = im.mean(2)

    def row(z):
        y = int((ztop - z) * 20)
        return L[y - 2:y + 3].mean(0), im[y - 2:y + 3].mean(0)

    for z in zs:
        l, _ = row(z)
        d = l < 85
        out = []
        s = None
        for x, v in enumerate(list(d) + [False]):
            if v and s is None:
                s = x
            if not v and s is not None:
                if x - s >= 6:
                    out.append("%.2f..%.2f" % (a0 + s / 20, a0 + x / 20))
                s = None
        print("WIN z%.1f:" % z, " ".join(out))
    l, c = row(zw)
    seg = []
    s = 0

    def cls(p):
        r, g, b = p
        m = (r + g + b) / 3
        if m < 20:
            return "-"
        if m < 70:
            return "K"
        if m < 140:
            return "G"
        return "W"

    k = [cls(p) for p in c]
    for x in range(1, len(k) + 1):
        if x == len(k) or k[x] != k[s]:
            if x - s >= 8:
                seg.append("%s %.2f..%.2f #%02x%02x%02x" % ((k[s], a0 + s / 20, a0 + x / 20) + tuple(int(v) for v in c[s:x].mean(0))))
            s = x
    print("WALL z%.1f:" % zw)
    print("\n".join(seg))


def rows(argv):
    f, h0, z1, ppm, x0, x1 = argv[0], *map(float, argv[1:6])
    thr = float(argv[6]) if len(argv) > 6 else 0.5
    a = np.asarray(Image.open(f).convert("L")).astype(float)
    c0, c1 = int((x0 - h0) * ppm), int((x1 - h0) * ppm)
    col = a[:, c0:c1]
    dark = (col < np.median(col[col < 250]) * thr).mean(1)  # fraction of dark pixels per row
    on = dark > 0.25
    rr, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if j - i >= 3:
                rr.append((z1 - j / ppm, z1 - i / ppm))
            i = j
        else:
            i += 1
    print("rows (z0..z1 m):", len(rr))
    for r in rr:
        print("  %.2f..%.2f  h %.2f" % (r[0], r[1], r[1] - r[0]))
    if len(rr) > 2:
        tops = [r[1] for r in rr]
        d = np.diff(tops)
        print("pitch median %.3f  mean %.3f" % (np.median(-d), np.mean(-d)))


CMDS = {"cols": cols, "profile": profile, "runs": runs, "rows": rows}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        sys.exit(__doc__.split("\n\n")[0] if False else "usage: elevstat.py cols|profile|runs|rows ... (헤더 주석 참고)")
    CMDS[sys.argv[1]](sys.argv[2:])
