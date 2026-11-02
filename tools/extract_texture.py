# -*- coding: utf-8 -*-
"""
extract_texture.py — 사진(로드뷰 등)에서 재질 조각을 반듯하게 펴서 텍스처 소스로 만듦 → textures_src/

사용:
  python tools/extract_texture.py refs/a.jpg --pts 812,402,1290,380,1302,905,806,930 --size 3.0x2.9 -o textures_src/stone
      --pts   사진 속 사각형 네 점 (왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래) 픽셀 좌표
      --size  그 사각형의 실제 크기 (가로 m x 세로 m)
  옵션
      --px 768         결과 가로 px (기본: 사진 해상도를 넘지 않는 최대값 → 업스케일 없음)
      --max-ppm 256    px/m 상한 (기본 256)
      --flatten 0.8    조명 평탄화 세기 (0 = 끔). 큰 그림자·빛 번짐을 흐린 밝기로 나눠 없앰
      --tile 0.15      이음매 없는 타일로 (가장자리 교차 블렌드 비율, 기본 0 = 끔).
                       줄눈·패널처럼 규칙 무늬는 쓰지 말고, 네 점을 줄눈 한 주기에 정확히 맞출 것.
                       콘크리트·아스팔트·자갈처럼 불규칙한 면에만 사용
      --sharpen 0.6    언샤프 마스크 세기
      --target-ppm 256 사진 해상도보다 높게 뽑기 (사진 색은 그대로, 미세한 결만 합성해 확대해도 뭉개져 보이지 않게). json 에 synthesized=true
      --paint          도색 벽면용: 경계(색 띠)는 살리고 잡티·압축 노이즈·나뭇잎을 지운 뒤 결만 입힘. 창·간판은 피하거나 --clean
      (출력 시 팔레트 = 주요 색 4개 hex 와 비율도 출력/json 에 저장)
      --clean x0,y0,x1,y1[;...]  결과 이미지에서 지울 영역(간판·사람·전선) → 주변으로 채움 (px, 결과 기준)
      --normal 3.0     노멀맵 세기 (고주파 밝기 → 높이)
      --grid 3x5       미리보기에 줄눈 칸 표시만 (출력에는 영향 없음)
      --show           원본 위에 네 점과 결과를 나란히 그린 확인용 PNG 도 저장
출력: <o>_albedo.png, <o>_normal.png, <o>_gloss.png, <o>.json (원본·점·실제 크기·px/m), (--show) <o>_check.png
cs2kit 에서:  atlas.add("stone", px=768, tile=(3.0, 2.9), image="textures_src/stone_albedo.png",
                      normal_image="textures_src/stone_normal.png", gloss_image="textures_src/stone_gloss.png")
주의: 간판·로고·글자·사람·차량은 --clean 으로 지우거나 그 부분을 피해서 고를 것 (상표 금지).
"""
import argparse
import json
import os

import sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, Vt = np.linalg.svd(np.array(A, float))
    H = Vt[-1].reshape(3, 3)
    return H / H[2, 2]


def warp(img, pts, W, H):
    """결과 (W,H) 픽셀 → 사진 좌표 역변환 후 바이큐빅 (PIL PERSPECTIVE)."""
    Hm = homography([(0, 0), (W, 0), (W, H), (0, H)], pts)   # 결과 → 사진
    coeffs = (Hm / Hm[2, 2]).flatten()[:8]
    return img.transform((W, H), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)


def src_resolution(pts):
    p = np.array(pts, float)
    w = max(np.linalg.norm(p[1] - p[0]), np.linalg.norm(p[2] - p[3]))
    h = max(np.linalg.norm(p[3] - p[0]), np.linalg.norm(p[2] - p[1]))
    return w, h


def flatten(a, strength, radius):
    lum = a.mean(2, keepdims=True)
    blur = np.asarray(Image.fromarray(np.clip(lum[..., 0], 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius)), np.float32)[..., None]
    mean = lum.mean()
    gain = (mean / np.maximum(blur, 1.0)) ** strength
    return np.clip(a * gain, 0, 255)


def clean(a, rects, iters=200):
    """지울 영역을 주변 색으로 확산 채움 (간단 인페인트) + 노이즈 보존용 블러 결."""
    m = np.zeros(a.shape[:2], bool)
    for x0, y0, x1, y1 in rects:
        m[int(y0):int(y1), int(x0):int(x1)] = True
    out = a.copy()
    known = ~m
    for _ in range(iters):
        if known.all():
            break
        acc = np.zeros_like(out); cnt = np.zeros(out.shape[:2], np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            k = np.roll(np.roll(known, dy, 0), dx, 1)
            acc += np.roll(np.roll(out, dy, 0), dx, 1) * k[..., None]
            cnt += k
        new = (~known) & (cnt > 0)
        out[new] = acc[new] / cnt[new][:, None]
        known = known | new
    return out


def make_tileable(a, frac):
    """가장자리 frac 만큼을 반대편과 교차 블렌드 → 반복해도 이음매 없음."""
    H, W = a.shape[:2]
    out = a.copy()
    bw, bh = max(1, int(W * frac)), max(1, int(H * frac))
    sh = np.roll(np.roll(a, W // 2, 1), H // 2, 0)            # 가운데로 옮긴 판 (이음매가 가운데)
    wx = np.ones(W); r = np.linspace(0, 1, bw)
    wx[:bw] = r; wx[-bw:] = r[::-1]
    wy = np.ones(H); r = np.linspace(0, 1, bh)
    wy[:bh] = r; wy[-bh:] = r[::-1]
    w = np.minimum(wx[None, :], wy[:, None])[..., None]
    # 가장자리(w 작음)는 shifted 판 가운데 부분(이음매 없는 곳)으로 채움
    out = a * w + sh * (1 - w)
    return out


def sharpen(a, amount, radius=1.2):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    bl = np.asarray(im.filter(ImageFilter.GaussianBlur(radius)), np.float32)
    return np.clip(a + amount * (a - bl), 0, 255)


def normal_from(a, strength, hp_radius=6):
    lum = a.mean(2)
    im = Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8))
    low = np.asarray(im.filter(ImageFilter.GaussianBlur(hp_radius)), np.float32)
    h = (lum - low) / 255.0
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    gy = -(np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    nz = 1 / np.sqrt(gx * gx + gy * gy + 1)
    return np.stack([-gx * nz, -gy * nz, nz], -1) * 127.5 + 127.5


def gloss_from(a, base=0.25, var=0.15):
    lum = a.mean(2) / 255.0
    g = base + var * (lum - lum.mean()) / (lum.std() + 1e-6) * 0.5
    return np.clip(g, 0, 1) * 255


def hex_of(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(v)))) for v in c)


def band_noise(shape, lo_sigma, hi_sigma, seed=7):
    """White noise limited to detail sizes between lo_sigma and hi_sigma pixels (zero mean, unit std)."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(shape).astype(np.float32)
    im = Image.fromarray(((n - n.min()) / (n.max() - n.min()) * 255).astype(np.uint8))
    a = np.asarray(im.filter(ImageFilter.GaussianBlur(float(max(lo_sigma, 0.3)))), np.float32)
    b = np.asarray(im.filter(ImageFilter.GaussianBlur(float(max(hi_sigma, lo_sigma + 0.5)))), np.float32)
    d = a - b
    return (d - d.mean()) / (d.std() + 1e-6)


def detail_std(a, sigma):
    lum = a.mean(2)
    bl = np.asarray(Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(float(sigma))), np.float32)
    return float((lum - bl).std())


def paint_mode(a, ppm):
    """Painted wall: edge-preserving smoothing (median, keeps paint-band borders) + grain with the photo's own strength.
    Removes JPEG noise, leaves, dirt specks and window reflections; the colour comes from the photo."""
    H, W = a.shape[:2]
    k = 4 if min(W, H) >= 64 else 1
    small = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((max(8, W // k), max(8, H // k)), Image.BOX)
    size = 9 if min(small.size) >= 40 else 5
    med = small.filter(ImageFilter.MedianFilter(size)).resize((W, H), Image.BICUBIC)
    low = np.asarray(med, np.float32)
    std = min(5.0, max(1.5, detail_std(a, max(1.0, ppm * 0.02))))
    g = band_noise((H, W), 0.6, max(2.0, ppm * 0.02)) * std
    return np.clip(low + g[..., None], 0, 255), std


def add_detail(a, ppm, ppm_src):
    """Photo has fewer px/m than requested: keep its colours, add band-limited fine grain (same strength as the photo's own
    fine detail) and sharpen. NOT real information - only avoids a blurry look up close."""
    f = float(ppm / max(ppm_src, 1.0))
    H, W = a.shape[:2]
    std = min(6.0, max(1.5, detail_std(a, max(1.0, f * 1.5)) * 0.8))
    g = band_noise((H, W), 0.5, max(1.5, f * 1.5)) * std
    return np.clip(a + g[..., None], 0, 255)


def palette(a, k=4, iters=12):
    """Dominant colours (hex, share) by a tiny k-means on a subsample."""
    px = a.reshape(-1, 3)
    rng = np.random.default_rng(1)
    px = px[rng.choice(len(px), size=min(20000, len(px)), replace=False)]
    cen = px[rng.choice(len(px), size=k, replace=False)]
    for _ in range(iters):
        lab = np.argmin(((px[:, None, :] - cen[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                cen[j] = px[lab == j].mean(0)
    share = np.bincount(lab, minlength=k) / len(lab)
    order = np.argsort(-share)
    return [(hex_of(cen[j]), float(share[j])) for j in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--pts", required=True)
    ap.add_argument("--size", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--px", type=int)
    ap.add_argument("--max-ppm", type=float, default=256)
    ap.add_argument("--flatten", type=float, default=0.8)
    ap.add_argument("--tile", type=float, default=0.0)
    ap.add_argument("--sharpen", type=float, default=0.6)
    ap.add_argument("--clean")
    ap.add_argument("--normal", type=float, default=3.0)
    ap.add_argument("--gloss", type=float, default=0.25)
    ap.add_argument("--target-ppm", type=float, default=0.0,
                    help="output at this px/m even if the photo has less (adds fine grain, marked synthesized). e.g. 256")
    ap.add_argument("--paint", action="store_true",
                    help="painted/plain wall: edge-preserving smoothing + grain, keeps colour bands; best for coloured paint")
    ap.add_argument("--grid")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    v = [float(t) for t in a.pts.replace(";", ",").split(",")]
    pts = [(v[i], v[i + 1]) for i in range(0, 8, 2)]
    wm, hm = (float(t) for t in a.size.lower().split("x"))
    img = Image.open(a.photo).convert("RGB")
    sw, sh = src_resolution(pts)
    ppm_src = min(sw / wm, sh / hm)                     # 사진이 가진 실제 해상도
    ppm = min(a.target_ppm if a.target_ppm > 0 else ppm_src, a.max_ppm)
    if a.px:
        ppm = min(ppm, a.px / wm)
    W, H = max(8, int(round(wm * ppm))), max(8, int(round(hm * ppm)))
    out = np.asarray(warp(img, pts, W, H), np.float32)
    if a.clean:
        rects = [tuple(float(t) for t in r.split(",")) for r in a.clean.split(";")]
        out = clean(out, rects)
    if a.flatten > 0:
        out = flatten(out, a.flatten, radius=max(W, H) / 6)
    synth = ppm > ppm_src * 1.15
    note = ""
    if a.paint:
        out, gstd = paint_mode(out, ppm)
        note = f"paint mode (grain {gstd:.1f})"
    elif synth:
        out = add_detail(out, ppm, ppm_src)
        note = "synthesized fine detail"
    if a.tile > 0:
        out = make_tileable(out, a.tile)
    if a.sharpen > 0 and not a.paint:
        out = sharpen(out, a.sharpen)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    Image.fromarray(out.astype(np.uint8)).save(a.out + "_albedo.png")
    Image.fromarray(normal_from(out, a.normal).astype(np.uint8)).save(a.out + "_normal.png")
    Image.fromarray(gloss_from(out, a.gloss).astype(np.uint8), "L").save(a.out + "_gloss.png")
    meta = dict(source=os.path.basename(a.photo), pts=pts, size_m=[wm, hm], px=[W, H], px_per_m=round(ppm, 1),
                source_px_per_m=round(ppm_src, 1), flatten=a.flatten, tile=a.tile, clean=a.clean,
                synthesized=bool(synth or a.paint), paint=a.paint, palette=palette(out))
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[extract] {a.out}_albedo.png  {W}x{H}px  {ppm:.0f} px/m (photo has {ppm_src:.0f} px/m)" + (f"  [{note}]" if note else ""))
    print("[extract] palette: " + "  ".join(f"{h} {s * 100:.0f}%" for h, s in meta["palette"]))
    if ppm_src < 64:
        print("[extract][WARN] photo below 64 px/m - blurry up close. Use a closer photo or mix with a painter texture")
    if a.show:
        prev = img.copy()
        d = ImageDraw.Draw(prev)
        d.line(pts + [pts[0]], fill=(255, 0, 0), width=max(2, img.size[0] // 400))
        for i, p in enumerate(pts):
            d.text((p[0] + 4, p[1] + 4), str(i + 1), fill=(255, 255, 0))
        k = 600 / prev.size[1]
        prev = prev.resize((int(prev.size[0] * k), 600))
        res = Image.fromarray(out.astype(np.uint8))
        if a.grid:
            gc, gr = (int(t) for t in a.grid.split("x"))
            dd = ImageDraw.Draw(res)
            for i in range(1, gc):
                dd.line([(W * i / gc, 0), (W * i / gc, H)], fill=(255, 0, 0))
            for j in range(1, gr):
                dd.line([(0, H * j / gr), (W, H * j / gr)], fill=(255, 0, 0))
        tiled = Image.new("RGB", (W * 2, H * 2))
        for i in range(2):
            for j in range(2):
                tiled.paste(res, (i * W, j * H))
        tiled = tiled.resize((int(600 * W / H), 600))
        sheet = Image.new("RGB", (prev.size[0] + tiled.size[0], 600), "white")
        sheet.paste(prev, (0, 0)); sheet.paste(tiled, (prev.size[0], 0))
        sheet.save(a.out + "_check.png")
        print(f"[extract] check image {a.out}_check.png (left: chosen 4 points, right: 2x2 repeat)")


if __name__ == "__main__":
    main()
