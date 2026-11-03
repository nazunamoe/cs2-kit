# 스캔 정사영의 "대표 주기"에서 창(어두운 유리) 목록 -> 생성기 wa 형식. 연결 영역마다 감싸는 상자, 층 경계에서 나눔.
# 사용: python scripts/winlist.py <ortho.png> <img_a0> <frame.json> <A0> <A1> <f0> <f1> <period> [thr=82] [flip=0]
#   flip=1: 뒷면·서쪽 면 (생성기 좌표 = -a). 출력: 주기 안 층 순서마다 [(a0, a1, (sill, head)), ...]
import sys, json
import numpy as np
from PIL import Image
img, ia0, frame = sys.argv[1], float(sys.argv[2]), sys.argv[3]
A0, A1 = float(sys.argv[4]), float(sys.argv[5]); f0, f1, P = int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
thr = float(sys.argv[9]) if len(sys.argv) > 9 else 82.0
flip = len(sys.argv) > 10 and sys.argv[10] == "1"
import os
PPM, ZTOP = float(os.environ.get("FACADE_PPM", "20")), float(os.environ.get("FACADE_ZTOP", "97"))   # ortho scale (px/m) and z of the image top
lv = json.load(open(frame))["levels"]; fh = lv[2] - lv[1]
im = np.asarray(Image.open(img).convert("L"), dtype=np.float32)
c0, c1 = int(round((A0 - ia0) * PPM)), int(round((A1 - ia0) * PPM))
H = int(round(P * fh * PPM)); stack = []
for f in range(f0, f1 + 1, P):
    r1 = (ZTOP - lv[f - 1]) * PPM
    rows = np.clip(np.round(r1 - np.arange(H)[::-1] - 0.5).astype(int), 0, im.shape[0] - 1)
    stack.append(im[rows, c0:c1])
med = np.median(np.stack(stack), axis=0)
mask = med < thr
Hf = fh * PPM
def comps(m):                                  # 4-connectivity flood fill
    seen = np.zeros_like(m, bool); out = []
    for y, x in zip(*np.nonzero(m)):
        if seen[y, x]: continue
        st = [(y, x)]; seen[y, x] = True; ys, xs = [], []
        while st:
            cy, cx = st.pop(); ys.append(cy); xs.append(cx)
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < m.shape[0] and 0 <= nx < m.shape[1] and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; st.append((ny, nx))
        out.append((min(xs), max(xs) + 1, min(ys), max(ys) + 1, len(xs)))
    return out
for j in range(P):                             # floor j of the period (0 = first)
    y0 = int(round(H - (j + 1) * Hf)); y1 = int(round(H - j * Hf))
    sub = mask[max(y0, 0):y1]
    wins = []
    for x0, x1, yy0, yy1, n in comps(sub):
        w, h = (x1 - x0) / PPM, (yy1 - yy0) / PPM
        if w < 0.45 or h < 0.35 or w > 6.0 or h > fh - 0.15 or n < 0.45 * (x1 - x0) * (yy1 - yy0):
            continue                           # specks, full-height dark strips, frames
        a0, a1 = A0 + x0 / PPM, A0 + x1 / PPM
        sill, head = (sub.shape[0] - yy1) / PPM, (sub.shape[0] - yy0) / PPM
        if flip: a0, a1 = -a1, -a0
        wins.append((round(a0, 2), round(a1, 2), (round(sill, 2), round(head, 2))))
    wins.sort()
    print(f"# floor {j + 1}/{P} of period (floors {f0 + j}, {f0 + j + P}, ...): {len(wins)} windows")
    print("    wa=[" + ", ".join(f"({a}, {b}, ({s}, {h}))" for a, b, (s, h) in wins) + "],")
