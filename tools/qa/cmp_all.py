"""모든 meta 사진을 같은 카메라로 한꺼번에 비교한다 (cmp_cam 을 사진마다 부르는 대신: Blender 한 번, 표 하나, 접촉 시트).

검증 도구(tools/qa/). 한 면만 보고 다른 면의 틀림을 놓치는 일을 막는다. 모델을 바꾼 뒤 보고 전에 한 번.
  python tools/qa/cmp_all.py --asset output/<에셋> --meta photos/101_meta.json --ground 74.51 [--only 1,3,5] [--label 단계]

하는 일
  1. meta["shots"] 의 사진마다 카메라(거리 dist_m, fov_v_deg, 높이 = pos[1]*100 - ground, 방위 az = (az_offset + angle) mod 360)를
     만들어 tools/qa/multicam.py 로 Blender 한 번에(--workers 개로 나눠 병렬) 렌더한다. 배경은 투명.
  2. 사진 실루엣(배경색 제외)과 모델 실루엣(alpha)이 가장 겹치도록 크기(1±0.10)·위치를 찾고(FFT) 실루엣 겹침도(IoU)를 잰다.
     (옛 cmp_cam 은 bbox 가로폭에 맞췄다 -> 낮은 카메라 사진의 바닥 녹지 원반에 속아 틀렸다. IoU 는 모델 밑변 아래 줄을 뺀다.)
  3. 결과: <out>/<사진>/model.png(렌더 원본, RGBA) pair.png(사진 | 정렬된 모델, 건물 부분만 잘라 긴 변 --max-side 이하)
     <out>/sheet_1.png, sheet_2.png … (사진 8장씩 접촉 시트: 위 줄 사진 | 모델 쌍), <out>/summary.json
  마지막 줄: CMPALL DONE shots=N low_iou(<0.80)=K iou_min=… iou_mean=… -> <out>
     (OK/WARN 판정은 하지 않는다: 낮은 카메라 사진은 실제 구조 차이로 늘 낮다. 판단은 점수 기록 대비 회귀(verify.py)와 눈으로.)

읽는 법
  - scale 이 1.0 에서 많이 벗어나면(±0.08) 이 사진의 카메라 가정(방위·높이·거리)이 틀렸을 수 있다 -> 표의 flag 열.
  - iou 는 실루엣이라 거의 대칭인 건물에서는 반대 면도 비슷하게 나온다. **IoU 는 회귀 감시용이지 "맞다"의 증거가 아니다.**
    표에서 낮은 사진은 pair.png 를 열어 눈으로 확인하고, 시트로 8방위 구조(날개·옥상)를 훑는다.
  - 방위 규칙 az = 180 + angle (mod 360)은 한 건물(101동)의 8방위 모두 육안 확인. 다른 건물·다른 캡처는
    처음에 시트를 보고 확인하고 안 맞으면 --az-offset 으로 고친다. 옛 방식(후보 두 개 중 IoU 높은 쪽)은 --az-auto.
    (angle 270 은 옛 방식이 같은 카메라 후보 -90 을 골라 90 도 사진과 같은 면을 렌더하는 오류가 있었다.)
  - --frame 으로 틀이 회전된 건물은 이 도구가 아직 지원하지 않는다. cmp_cam.py --frame 을 쓴다.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> 키트 루트
sys.path.insert(0, os.path.join(KIT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj  # noqa: E402,F401  (작업 폴더 = 활성 프로젝트)
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from cmp_cam import blender_exe, mask, bbox  # noqa: E402

MULTICAM = os.path.join(KIT, "tools", "qa", "multicam.py")
IOU_WARN = 0.80
SCALE_WARN = 0.08


def render_jobs(blend, jobs, workers):
    """jobs 를 workers 개 Blender 세션에 나눠 렌더. 만들어지지 않은 파일 목록을 돌려준다."""
    parts = [jobs[i::workers] for i in range(workers) if jobs[i::workers]]
    tmp = tempfile.mkdtemp(prefix="cmpall_")

    def run(i):
        jf = os.path.join(tmp, "jobs%d.json" % i)
        json.dump(parts[i], open(jf, "w", encoding="utf-8"))
        r = subprocess.run([blender_exe(), "-b", blend, "-P", MULTICAM, "--", jf],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (r.stdout + r.stderr)[-600:]
    with cf.ThreadPoolExecutor(max_workers=len(parts)) as ex:
        logs = list(ex.map(run, range(len(parts))))
    miss = [j["out"] for j in jobs if not os.path.exists(j["out"])]
    if miss:
        raise SystemExit("CMPALL FAIL blender did not write %d file(s); last log:\n%s" % (len(miss), "\n".join(logs)[-800:]))


def _small(m, c, s=1.0):
    """bool 마스크를 1/c 로 줄이고(BOX 평균) s 배 확대·축소한 float32 0/1 배열."""
    h, w = m.shape
    im = Image.fromarray(m.astype(np.uint8) * 255)
    return (np.asarray(im.resize((max(1, int(round(w * s / c))), max(1, int(round(h * s / c)))), Image.BOX)) > 90).astype(np.float32)


def _fftcorr(P, M):
    """P 위에 M 의 왼쪽 위를 (ox, oy) 에 놓았을 때 겹치는 넓이 배열. 반환: (배열, 높이Hf, 너비Wf)"""
    Hf, Wf = P.shape[0] + M.shape[0] - 1, P.shape[1] + M.shape[1] - 1
    c = np.fft.irfft2(np.fft.rfft2(P, s=(Hf, Wf)) * np.conj(np.fft.rfft2(M, s=(Hf, Wf))), s=(Hf, Wf))
    return c, Hf, Wf


def _overlap(P, M, ox, oy):
    """M(왼쪽 위 = ox, oy)을 P 에 얹었을 때 겹침 넓이."""
    y0, x0 = max(0, oy), max(0, ox)
    y1, x1 = min(P.shape[0], oy + M.shape[0]), min(P.shape[1], ox + M.shape[1])
    if y1 <= y0 or x1 <= x0:
        return 0.0
    return float((P[y0:y1, x0:x1] * M[y0 - oy:y1 - oy, x0 - ox:x1 - ox]).sum())


def align_alpha(model_rgba, photo_size, pm, scale_range=0.10):
    """모델(RGBA)을 사진 실루엣에 맞춘다: 크기 s(1±scale_range)와 위치를 실루엣 IoU 가 최대가 되게(FFT 상관, 거친 1/8 -> 1/4; 먼저 s=1 로 위치, 그다음 밑변 아래 바닥 원반을 잘라내고 s 탐색).
    카메라 가정이 맞으면 s ≈ 1 이다(카메라 거리·화각을 이미 meta 로 맞춰 렌더하므로). 사진 가로폭에 맞추던 옛 방식은
    낮은 카메라 사진에서 바닥 녹지 원반이 실루엣 폭을 부풀려 틀렸다.
    IoU 는 모델 밑변보다 아래 줄(바닥 원반)을 빼고 잰다(모델 밑이 사진 밖이면 전체).
    반환: (캔버스 RGBA, scale, iou, 모델이 놓인 bbox)"""
    W, H = photo_size
    mm = np.asarray(model_rgba)[:, :, 3] > 127
    if not mm.any() or not pm.any():
        return Image.new("RGBA", (W, H), (0, 0, 0, 0)), float("nan"), 0.0, (0, 0, W - 1, H - 1)
    mx0, my0, mx1, my1 = bbox(mm)
    mcrop = mm[my0:my1 + 1, mx0:mx1 + 1]
    rgba = model_rgba.crop((mx0, my0, mx1 + 1, my1 + 1))

    def fit(P_full, scales):
        """거친 1/8 FFT 상관으로 (s, 위치) 를 찾고 1/4 에서 +-3 칸 다듬는다. 반환 (s, ox4, oy4)"""
        P8 = _small(P_full, 8)
        best = None
        for s in scales:
            M8 = _small(mcrop, 8, s)
            c, Hf, Wf = _fftcorr(P8, M8)
            iou = c / np.maximum(P8.sum() + M8.sum() - c, 1.0)
            iy, ix = np.unravel_index(int(np.argmax(iou)), iou.shape)
            oy = iy if iy <= P8.shape[0] - 1 else iy - Hf
            ox = ix if ix <= P8.shape[1] - 1 else ix - Wf
            if best is None or iou[iy, ix] > best[0]:
                best = (float(iou[iy, ix]), s, ox, oy)
        _, s, ox8, oy8 = best
        P4, M4 = _small(P_full, 4), _small(mcrop, 4, s)
        bo = None
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                ox, oy = 2 * ox8 + dx, 2 * oy8 + dy
                inter = _overlap(P4, M4, ox, oy)
                v = inter / max(1.0, P4.sum() + M4.sum() - inter)
                if bo is None or v > bo[0]:
                    bo = (v, ox, oy)
        return s, bo[1], bo[2]

    # 1단계: 크기 1.0 고정으로 대략 위치. 2단계: 모델 밑변(지면) 아래 사진 줄(바닥 녹지 원반)을 잘라내고 크기 탐색.
    s, ox4, oy4 = fit(pm, [1.0])
    yb = (oy4 + int(round(mcrop.shape[0] * s / 4))) * 4              # 1단계에서 모델 밑변이 놓인 사진 줄
    P2 = pm
    if yb < H - 8:
        P2 = pm.copy()
        P2[min(H, yb + int(0.02 * H)):] = False
    n = 17 if scale_range > 0 else 1
    scales = [1.0 + scale_range * (2.0 * i / (n - 1) - 1.0) for i in range(n)] if n > 1 else [1.0]
    s, ox4, oy4 = fit(P2, scales)
    sm = rgba.resize((max(1, int(round(rgba.width * s))), max(1, int(round(rgba.height * s)))))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(sm, (ox4 * 4, oy4 * 4))
    am = np.asarray(canvas)[:, :, 3] > 127
    ys = np.where(am.any(1))[0]
    lim = int(ys.max()) + 1 if len(ys) and ys.max() < H - 1 else H     # 모델 밑이 사진 안이면 그 아래(바닥 원반)는 뺀다
    a_, p_ = am[:lim], pm[:lim]
    iou = float((a_ & p_).sum()) / max(1, int((a_ | p_).sum()))
    ys2, xs2 = np.where(am) if am.any() else (np.array([0]), np.array([0]))
    return canvas, s, iou, (int(xs2.min()), int(ys2.min()), int(xs2.max()), int(ys2.max()))


def make_pair(photo, canvas, box, max_side):
    """모델이 놓인 bbox(여백 6%)를 잘라 사진 | 모델 한 장으로. 모델은 사진 배경색 위에 얹는다."""
    px0, py0, px1, py1 = box
    mx, my = int((px1 - px0) * 0.06) + 4, int((py1 - py0) * 0.03) + 4
    crop = (max(0, px0 - mx), max(0, py0 - my), min(photo.width, px1 + mx), min(photo.height, py1 + my))
    bg = Image.new("RGBA", photo.size, tuple(photo.getpixel((0, 0))) + (255,))
    bg.alpha_composite(canvas)
    A, B = photo.crop(crop), bg.convert("RGB").crop(crop)
    pair = Image.new("RGB", (A.width * 2 + 8, A.height), (255, 0, 0))
    pair.paste(A, (0, 0))
    pair.paste(B, (A.width + 8, 0))
    z = min(1.0, max_side / float(max(pair.size)))
    return pair.resize((max(1, int(pair.width * z)), max(1, int(pair.height * z))), Image.LANCZOS)


def contact_sheets(items, out, max_side, cols=4, per_sheet=8):
    """items = [(라벨, pair 이미지)]. 한 장 = cols 열 x (per_sheet/cols) 줄, 가로 max_side."""
    cw = max_side // cols
    paths = []
    for k in range(0, len(items), per_sheet):
        chunk = items[k:k + per_sheet]
        ch = min(int(cw * 1.4), max(int((cw - 4) * im.height / im.width) for _, im in chunk) + 2)   # 셀 높이 = 가장 큰 그림에 맞춤
        rows = (len(chunk) + cols - 1) // cols
        S = Image.new("RGB", (cw * cols, (ch + 14) * rows), (255, 255, 255))
        d = ImageDraw.Draw(S)
        for i, (label, im) in enumerate(chunk):
            z = min((cw - 4) / im.width, ch / im.height)
            t = im.resize((max(1, int(im.width * z)), max(1, int(im.height * z))), Image.LANCZOS)
            x, y = (i % cols) * cw, (i // cols) * (ch + 14)
            S.paste(t, (x + (cw - t.width) // 2, y + 14))
            d.text((x + 3, y + 1), label, fill=(200, 0, 0))
        p = os.path.join(out, "sheet_%d.png" % (k // per_sheet + 1))
        S.save(p)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asset", required=True, help="output/<에셋> 폴더 또는 .blend")
    ap.add_argument("--meta", required=True)
    ap.add_argument("--photo-dir", default=None, help="사진 폴더 (기본 = meta 파일이 있는 폴더)")
    ap.add_argument("--ground", type=float, default=74.51)
    ap.add_argument("--az-offset", type=float, default=180.0, help="az = (az_offset + angle) mod 360 (기본 180)")
    ap.add_argument("--az-auto", action="store_true", help="옛 방식: az = 180±angle 두 후보 중 IoU 높은 쪽")
    ap.add_argument("--only", default=None, help="쉼표로 구분한 사진 번호/이름 조각 (예 1,3,5 -> 이름에 side1/side3/side5 가 든 사진)")
    ap.add_argument("--scale-range", type=float, default=0.10, help="크기 탐색 범위 1±값 (0 = 크기 1.0 고정). 기본 0.10")
    ap.add_argument("--workers", type=int, default=2, help="동시에 띄울 Blender 수 (기본 2)")
    ap.add_argument("--max-side", type=int, default=1000, help="pair/시트 그림의 긴 변 상한 px (토큰 절약, 기본 1000)")
    ap.add_argument("--out", default="work/chk_all")
    a = ap.parse_args()

    t0 = time.time()
    blend = a.asset if a.asset.endswith(".blend") else (glob.glob(os.path.join(a.asset, "*.blend")) or [None])[0]
    if not blend or not os.path.exists(blend):
        raise SystemExit("CMPALL FAIL no .blend in " + a.asset)
    blend = os.path.abspath(blend)
    meta = json.load(open(a.meta, encoding="utf-8"))
    pdir = a.photo_dir or os.path.dirname(os.path.abspath(a.meta))
    shots = meta["shots"]
    if a.only:
        keys = [k.strip() for k in a.only.split(",") if k.strip()]
        shots = [s for s in shots if any(("side" + k) == os.path.splitext(s["file"])[0].split("_")[-1] or k == s["file"] for k in keys)]
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)

    todo, skipped = [], []
    for s in shots:
        pf = os.path.join(pdir, s["file"])
        (todo if os.path.exists(pf) else skipped).append((s, pf))
    if skipped:
        print("note: photo file missing, skipped: " + ", ".join(s["file"] for s, _ in skipped))
    if not todo:
        raise SystemExit("CMPALL FAIL no photo found for meta shots (photo dir %s)" % pdir)

    dist, fov = meta["dist_m"], meta["fov_v_deg"]
    jobs, cand = [], {}
    for s, pf in todo:
        ang = s["angle_deg"]
        azs = sorted({(180.0 - ang) % 360, (180.0 + ang) % 360}) if a.az_auto else [(a.az_offset + ang) % 360]
        W, H = Image.open(pf).size
        base = os.path.splitext(s["file"])[0]
        os.makedirs(os.path.join(out, base), exist_ok=True)
        cand[s["file"]] = []
        for az in azs:
            o = os.path.join(out, base, "model_az%g.png" % az)
            jobs.append(dict(az=az, cam_h=s["cam"]["pos"][1] * 100 - a.ground, dist=dist, fov=fov, rx=W, ry=H, out=o))
            cand[s["file"]].append((az, o))
        for _, o in cand[s["file"]]:
            if os.path.exists(o):
                os.remove(o)
    t1 = time.time()
    render_jobs(blend, jobs, max(1, min(a.workers, len(jobs))))
    t2 = time.time()

    def evaluate(item):
        s, pf = item
        base = os.path.splitext(s["file"])[0]
        photo = Image.open(pf).convert("RGB")
        pm = mask(photo)
        best = None
        for az, o in cand[s["file"]]:
            m = Image.open(o).convert("RGBA")
            canvas, sc_, iou, box = align_alpha(m, photo.size, pm, a.scale_range)
            if best is None or iou > best[2]:
                best = (az, o, iou, sc_, canvas, box)
        az, o, iou, sc_, canvas, box = best
        final = os.path.join(out, base, "model.png")
        if os.path.exists(final):
            os.remove(final)
        os.replace(o, final)
        for _, other in cand[s["file"]]:
            if os.path.exists(other):
                os.remove(other)
        pair = make_pair(photo, canvas, box, a.max_side)
        pair.save(os.path.join(out, base, "pair.png"))
        return dict(file=s["file"], angle=s["angle_deg"], az=az, iou=round(iou, 3), scale=round(float(sc_), 3)), pair
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(evaluate, todo))

    rows = [r for r, _ in res]
    print("%-18s %5s %5s %6s %6s  flag" % ("shot", "angle", "az", "iou", "scale"))
    for r in rows:
        flag = []
        if r["iou"] < IOU_WARN:
            flag.append("LOW_IOU")
        if r["scale"] == r["scale"] and abs(r["scale"] - 1.0) > SCALE_WARN:
            flag.append("SCALE")
        print("%-18s %5g %5g %6.3f %6.3f  %s" % (r["file"], r["angle"], r["az"], r["iou"], r["scale"], " ".join(flag)))
    sheets = contact_sheets([("%s a%g iou %.2f" % (os.path.splitext(r["file"])[0].split("_")[-1], r["angle"], r["iou"]), p) for r, p in res],
                            out, a.max_side)
    ious = [r["iou"] for r in rows]
    worst = rows[int(np.argmin(ious))]
    summary = dict(asset=os.path.basename(blend), meta=os.path.basename(a.meta), az_offset=a.az_offset, az_auto=a.az_auto,
                   time=time.strftime("%Y-%m-%d %H:%M:%S"), shots={r["file"]: r for r in rows})
    json.dump(summary, open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), indent=1)
    low = sum(1 for r in rows if r["iou"] < IOU_WARN)
    print("CMPALL DONE shots=%d low_iou(<%.2f)=%d iou_min=%.3f (%s) iou_mean=%.3f render %.0fs total %.0fs sheets=%s -> %s" % (
        len(rows), IOU_WARN, low, min(ious), worst["file"], float(np.mean(ious)), t2 - t1, time.time() - t0,
        ",".join(os.path.basename(p) for p in sheets), os.path.relpath(out)))


if __name__ == "__main__":
    main()
