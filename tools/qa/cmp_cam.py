"""사진(VR meta 카메라) ↔ 모델을 같은 카메라로 렌더해 나란히 놓는다 — "눈으로 따로 보기" 대신 쓰는 비교 도구.

검증 도구(tools/qa/). 옥상·창·띠 등 사진과 맞는지 확인하는 모든 때에, 보고 전에 쓴다.
  python tools/qa/cmp_cam.py --asset output/<에셋> --photo photos/101_side1.png --meta photos/101_meta.json \
        --crop roofL:1260,300,1760,640 --crop roofR:1780,600,2540,900
  (--shot 파일이름  meta 의 shots[].file, 기본 = 사진 파일 이름)

하는 일
  1. meta 카메라(거리 dist_m, fov_v_deg, 높이 = pos[1]*100 - ground)로 에셋 .blend 를 렌더 (tools/facade/model_photo_cam.py)
  2. 사진 실루엣(배경색 제외)과 모델 실루엣의 bbox 를 맞춰 크기·위치 정렬 (사진이 배경 제거된 VR 캡처일 때)
  3. 결과: work/chk/<shot>/  model.png(원본 렌더) aligned.png(사진 크기로 정렬) pair_<crop>.png(사진 | 모델) blend_<crop>.png(50% 겹침)
  마지막 줄: CMPCAM OK|WARN iou=… scale=… (iou < 0.80 이면 카메라 가정·az·ground 가 틀렸을 수 있음 → --az / --ground 로 고쳐 다시)

주의
  - az 규칙: az = (180 + angle) mod 360 이 101동 8방위 모두 육안으로 확인됨. 이 도구는 아직 az = 180-angle / 180+angle 두 후보 중
    실루엣이 더 맞는 쪽을 자동 선택하며, 고른 값이 180+angle 과 다르면 WARN 을 낸다(angle 270 은 반대 면을 골랐었음 -> --az 로 고정).
    16장 전부를 올바른 az 로 한 번에 보려면 tools/qa/cmp_all.py.
  - --max-side N : pair/blend 그림의 긴 변을 N px 이하로 저장(토큰 절약, 기본 줄이지 않음).
  - ground = 지면 표고(스캔 좌표 m, 101동 74.51). 건물마다 다르다.
  - 사진이 배경 제거 캡처가 아니면 --no-align (정렬 없이 같은 크기로만 놓는다).

--frame work/frame_<동>.json  (생성기 틀이 스캔에서 회전·이동된 건물)
  frame = {yaw, ox, oy, oz}. meta 카메라(스캔 좌표 cm)를 틀로 옮겨(생성기 좌표) 에셋 좌표(= 생성기 + manifest.json 의 pivot_shift)에서
  tools/qa/modcam.py 로 같은 세로 화각(렌즈 = 18/(tan(fov_v/2)·W/H), 센서 36 mm 가 가로에 걸리므로)을 렌더한다. 정렬 없이 사진과 같은 크기로 놓고 iou 만 참고로 낸다.
  (에셋 좌표 오프셋은 코드에 박지 않고 manifest.json 의 pivot_shift 에서 읽는다)
"""
import argparse
import os
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/qa/ -> 키트 루트
sys.path.insert(0, os.path.join(KIT, "tools"))
import proj  # noqa: E402,F401  (작업 폴더 = 활성 프로젝트)
import json  # noqa: E402
import glob  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

CAMSCRIPT = os.path.join(KIT, "tools", "facade", "model_photo_cam.py")


def cap(im, max_side):
    """긴 변이 max_side(>0)보다 길면 줄인다 (토큰 절약용, 기본 꺼짐)."""
    if not max_side or max(im.size) <= max_side:
        return im
    z = max_side / float(max(im.size))
    return im.resize((max(1, int(im.width * z)), max(1, int(im.height * z))))


def blender_exe():
    if os.environ.get("BLENDER"):
        return os.environ["BLENDER"]
    p = os.path.join(KIT, "tools", "blender_path.txt")
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else "blender"


def render(blend, az, cam_h, dist, fov, rx, ry, out):
    cmd = [blender_exe(), "-b", blend, "-P", CAMSCRIPT, "--", str(az), str(cam_h), str(dist), str(fov), str(rx), str(ry), "0", "0", os.path.abspath(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        raise SystemExit("CMPCAM FAIL blender render failed:\n" + (r.stdout + r.stderr)[-600:])


def mask(im, tol=60):
    a = np.asarray(im.convert("RGB")).astype(int)
    bg = a[0, 0]
    return (np.abs(a - bg).sum(2) > tol)


def bbox(m):
    ys, xs = np.where(m)
    return xs.min(), ys.min(), xs.max(), ys.max()


def align(model, photo_size, pm, no_align):
    """모델 이미지를 사진 크기 캔버스로 옮긴다. 반환: (이미지, scale, iou)"""
    W, H = photo_size
    if no_align:
        return model.resize((W, H)), 1.0, float("nan")
    mm = mask(model)
    px0, py0, px1, py1 = bbox(pm)
    mx0, my0, mx1, my1 = bbox(mm)
    s = (px1 - px0) / max(1, (mx1 - mx0))
    sm = model.resize((int(model.width * s), int(model.height * s)))
    ox, oy = int(mx0 * s) - px0, int(my0 * s) - py0
    bgc = tuple(np.asarray(model.convert("RGB"))[0, 0])
    canvas = Image.new("RGB", (W, H), bgc)
    canvas.paste(sm, (-ox, -oy))
    am = mask(canvas)
    inter, union = (am & pm).sum(), (am | pm).sum()
    return canvas, s, inter / max(1, union)


def frame_mode(a, blend, meta, shot, name):
    import math
    F = json.load(open(a.frame, encoding="utf-8"))
    man = json.load(open(os.path.join(os.path.dirname(blend), "manifest.json"), encoding="utf-8"))
    px, py = man.get("pivot_shift", [0.0, 0.0])
    cam = shot["cam"]
    yaw = math.radians(F["yaw"])
    mx, my, mz = cam["pos"][0] * 100, -cam["pos"][2] * 100, cam["pos"][1] * 100
    gx = math.cos(yaw) * mx + math.sin(yaw) * my - F["ox"]
    gy = -math.sin(yaw) * mx + math.cos(yaw) * my - F["oy"]
    gz = mz - F["oz"]
    md = [cam["dir"][0], -cam["dir"][2], cam["dir"][1]]
    gdx = math.cos(yaw) * md[0] + math.sin(yaw) * md[1]
    gdy = -math.sin(yaw) * md[0] + math.cos(yaw) * md[1]
    dist = meta["dist_m"]
    photo = Image.open(a.photo).convert("RGB")
    W, H = photo.size
    # Blender 센서 36 mm 는 긴 변(가로)에 걸리므로, 세로 화각 fov_v 가 되는 렌즈 = 18 / (tan(fov_v/2) * W/H)
    lens = 18.0 / (math.tan(math.radians(meta["fov_v_deg"]) / 2) * W / H)
    od = os.path.join(a.out, os.path.splitext(name)[0])
    os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "model.png")
    # 에셋 좌표 = 생성기 좌표 + pivot_shift (키트가 피벗을 바닥 가운데로 옮긴 만큼)
    cmd = [blender_exe(), "-b", blend, "-P", os.path.join(KIT, "tools", "qa", "modcam.py"), "--", os.path.abspath(out),
           "%f" % (gx + px), "%f" % (gy + py), "%f" % gz, "%f" % (gx + gdx * dist + px), "%f" % (gy + gdy * dist + py), "%f" % gz,
           "%f" % lens, str(W), str(H)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        raise SystemExit("CMPCAM FAIL modcam render failed: " + (r.stdout + r.stderr)[-600:])
    model = Image.open(out).convert("RGB")
    pm = mask(photo)
    am = mask(model)
    iou = (am & pm).sum() / max(1, (am | pm).sum())
    model.save(os.path.join(od, "aligned.png"))
    for c in a.crop:
        nm, box = c.split(":")
        box = tuple(int(v) for v in box.split(","))
        A, B = photo.crop(box), model.crop(box)
        pair = Image.new("RGB", (A.width * 2 + 10, A.height), (255, 0, 0))
        pair.paste(A, (0, 0))
        pair.paste(B, (A.width + 10, 0))
        z = min(1.5, 1500.0 / pair.width)
        cap(pair.resize((int(pair.width * z), int(pair.height * z))), a.max_side).save(os.path.join(od, "pair_%s.png" % nm))
        cap(Image.blend(A, B, 0.5).resize((int(A.width * z), int(A.height * z))), a.max_side).save(os.path.join(od, "blend_%s.png" % nm))
    print("CMPCAM %s shot=%s frame cam_gen=(%.1f,%.1f,%.2f) dir=(%.3f,%.3f) iou(bg-differs)=%.3f -> %s" % ("OK" if iou >= 0.5 else "WARN", name, gx, gy, gz, gdx, gdy, iou, od))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asset", required=True, help="output/<에셋> 폴더 또는 .blend")
    ap.add_argument("--photo", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--shot", default=None)
    ap.add_argument("--ground", type=float, default=74.51)
    ap.add_argument("--az", type=float, default=None)
    ap.add_argument("--crop", action="append", default=[], help="이름:x0,y0,x1,y1 (사진 픽셀)")
    ap.add_argument("--no-align", action="store_true")
    ap.add_argument("--max-side", type=int, default=0, help="pair/blend 그림의 긴 변 상한 px (토큰 절약; 기본 0 = 줄이지 않음, 1000 권장)")
    ap.add_argument("--frame", default=None, help="frame_<동>.json (yaw, ox, oy, oz): 틀이 회전된 건물용")
    ap.add_argument("--out", default="work/chk")
    a = ap.parse_args()

    blend = a.asset if a.asset.endswith(".blend") else (glob.glob(os.path.join(a.asset, "*.blend")) or [None])[0]
    if not blend or not os.path.exists(blend):
        raise SystemExit("CMPCAM FAIL no .blend in " + a.asset)
    meta = json.load(open(a.meta, encoding="utf-8"))
    name = a.shot or os.path.basename(a.photo)
    shot = next((s for s in meta["shots"] if s["file"] == name), None)
    if shot is None:
        raise SystemExit("CMPCAM FAIL shot %s not in meta (%s)" % (name, ", ".join(s["file"] for s in meta["shots"][:6])))
    ang = shot["angle_deg"]
    if a.frame:
        return frame_mode(a, blend, meta, shot, name)
    cam_h = shot["cam"]["pos"][1] * 100 - a.ground
    dist, fov = meta["dist_m"], meta["fov_v_deg"]
    photo = Image.open(a.photo).convert("RGB")
    W, H = photo.size
    pm = mask(photo)
    od = os.path.join(a.out, os.path.splitext(name)[0])
    os.makedirs(od, exist_ok=True)
    cands = [a.az] if a.az is not None else sorted({180.0 - ang, 180.0 + ang})
    best = None
    for az in cands:                                   # 후보가 둘 이상이면 작은 해상도로 실루엣 비교
        out = os.path.join(od, "model_az%g.png" % az)
        rx, ry = (W, H) if len(cands) == 1 else (W // 4, H // 4)
        render(blend, az, cam_h, dist, fov, rx, ry, out)
        im = Image.open(out).convert("RGB")
        small = photo.resize((rx, ry))
        _, s, iou = align(im, (rx, ry), mask(small), a.no_align)
        if best is None or (iou == iou and iou > best[1]):
            best = (az, iou, out, rx)
    az = best[0]
    exp = (180.0 + ang) % 360
    if az % 360 != exp:
        print("CMPCAM WARN chosen az %g differs from 180+angle=%g (visually confirmed rule on tower 101; at angle 270 this auto-choice picked "
              "the opposite face). Retry: --az %g, or use cmp_all.py" % (az, exp, exp))
    out = os.path.join(od, "model.png")
    if len(cands) > 1 or best[3] != W:
        render(blend, az, cam_h, dist, fov, W, H, out)
    else:
        os.replace(best[2], out)
    model = Image.open(out).convert("RGB")
    canvas, s, iou = align(model, (W, H), pm, a.no_align)
    canvas.save(os.path.join(od, "aligned.png"))
    for c in a.crop:
        nm, box = c.split(":")
        box = tuple(int(v) for v in box.split(","))
        A, B = photo.crop(box), canvas.crop(box)
        pair = Image.new("RGB", (A.width * 2 + 10, A.height), (255, 0, 0))
        pair.paste(A, (0, 0))
        pair.paste(B, (A.width + 10, 0))
        z = min(1.5, 1500.0 / pair.width)
        cap(pair.resize((int(pair.width * z), int(pair.height * z))), a.max_side).save(os.path.join(od, "pair_%s.png" % nm))
        cap(Image.blend(A, B, 0.5).resize((int(A.width * z), int(A.height * z))), a.max_side).save(os.path.join(od, "blend_%s.png" % nm))
    ok = a.no_align or iou >= 0.80
    print("CMPCAM %s shot=%s az=%g cam_h=%.1f scale=%.3f iou=%.3f -> %s%s" % ("OK" if ok else "WARN", name, az, cam_h, s, iou, od,
          ("  AZ_DIFFERS_FROM_180+ANGLE(%g)" % exp) if az % 360 != exp else ""))


if __name__ == "__main__":
    main()
