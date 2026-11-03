# -*- coding: utf-8 -*-
"""
cycle.py — 한 번에: 생성기 실행 → check → 미리보기. 출력은 짧게 (작은 모델·에이전트용)

  python tools/cycle.py my_building_cs2.py --label windows   생성 + 검사 + 미리보기
      previews/<에셋>.png                         최신 (위에 #번호·시각·PASS/FAIL·label 띠)
      previews/progress/latest.png                항상 같은 파일 = 최신 (이미지 뷰어로 열어 두기)
      previews/progress/<에셋>/NNN_HHMMSS_label.png  실행할 때마다 쌓이는 진행 기록
  python tools/cycle.py my_building_cs2.py --no-render     생성 + 검사만 (이미지 없음)
  python tools/cycle.py my_building_cs2.py --views front,iso --list 3
  python tools/cycle.py my_building_cs2.py --full          검사 + 사진 + 타일 + LOD 를 한 번에 (보고 전 최종 확인용)
  python tools/cycle.py my_building_cs2.py --full --json   위 결과를 output/<에셋>/_check/gate.json 에 저장
photo_refs.json 이 있으면 사진 비교(tools/photo_check.py)도 함께 → PHOTO_MISMATCH 줄, previews/photo_check/*.png
--full 은 tools/tile_compare.py 와 tools/qa/lod_check.py 도 실행한다(lod_check 는 .blend 필요, 없으면 SKIP).
마지막 줄: RESULT PASS|FAIL errors=N warnings=M [photo_mismatch=K] asset=<이름> preview=<경로>
그 위 GATE 줄: 검사 오류·사진 불일치·LOD 구멍을 합친 요약 (RESULT 의 종료 코드는 예전과 같이 검사 오류만 봄)
종료 코드: 실행 실패 2, 검사 오류 1, 통과 0
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
from proj import ROOT, KIT, NAME  # noqa: E402,F401


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def save_progress(img_path, asset, ok, n_err, label):
    """Stamp a banner (step number, time, PASS/FAIL, label) and keep a numbered copy in previews/progress/<asset>/."""
    import re
    import time
    from PIL import Image, ImageDraw
    d = os.path.join(ROOT, "previews", "progress", asset)
    os.makedirs(d, exist_ok=True)
    nums = [int(m.group(1)) for f in os.listdir(d) for m in [re.match(r"(\d{3})_", f)] if m]
    n = max(nums) + 1 if nums else 1
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", label)[:30].strip("-")
    stamp = time.strftime("%H%M%S")
    im = Image.open(img_path).convert("RGB")
    bar = Image.new("RGB", (im.size[0], 28), (40, 160, 70) if ok else (190, 50, 40))
    try:
        from PIL import ImageFont
        font = ImageFont.load_default(size=18)
    except Exception:
        font = None
    ImageDraw.Draw(bar).text((8, 4), f"#{n:03d}  {time.strftime('%H:%M:%S')}  {'PASS' if ok else 'FAIL errors=%d' % n_err}  {label}", fill=(255, 255, 255), font=font)
    out = Image.new("RGB", (im.size[0], im.size[1] + 28))
    out.paste(bar, (0, 0)); out.paste(im, (0, 28))
    out.save(img_path)                                            # latest (with banner)
    hist = os.path.join(d, f"{n:03d}_{stamp}{'_' + label if label else ''}.png")
    out.save(hist)
    out.save(os.path.join(ROOT, "previews", "progress", "latest.png"))   # one fixed file to keep open
    return hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("generator")
    ap.add_argument("--out", default="output")
    ap.add_argument("--views", default="front,iso2,back,iso")
    ap.add_argument("--size", default="700x520")
    ap.add_argument("--list", type=int, default=3)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--tiles", action="store_true", help="also run tools/tile_compare.py (tile-by-tile detail check vs photos)")
    ap.add_argument("--full", action="store_true", help="also run tiles + tools/qa/lod_check.py and print one GATE line")
    ap.add_argument("--json", nargs="?", const="", default=None, metavar="PATH",
                    help="write every result to one JSON (default: output/<asset>/_check/gate.json)")
    ap.add_argument("--label", default="", help="short step name for the progress image, e.g. windows")
    a = ap.parse_args()
    py = sys.executable
    out = os.path.join(ROOT, a.out)

    # 1) 생성
    code, log = run([py, os.path.join(HERE, "run_blender.py"), os.path.abspath(a.generator), "--", "--out", out])
    lines = [l for l in log.splitlines() if l.strip()]
    asset = None
    for l in lines:
        if l.startswith("[cs2kit] ") and "_L" in l and "tris" not in l:
            asset = l.split()[1]
    fbx = any("FBX + .blend" in l for l in lines)
    if code != 0 or not asset:
        print("[1/3 build] FAILED - last output:")
        for l in lines[-25:]:
            print("   " + l)
        print(f"RESULT FAIL errors=generator asset=None preview=None")
        sys.exit(2)
    print(f"[1/3 build] {asset}  ({'FBX written' if fbx else 'NO FBX - Blender not found, checking OBJ'})")
    build_warns = [l.strip() for l in lines if "[WARN]" in l]
    for l in lines:
        if "[WARN]" in l or l.startswith("[cs2kit] tris"):
            print("   " + l)

    # 2) 검사
    rep = os.path.join(out, asset, "_check", "report.json")
    code, log = run([py, os.path.join(HERE, "check.py"), os.path.join(out, asset), "--list", str(a.list), "--json", rep])
    try:
        r = json.load(open(rep, encoding="utf-8"))[0]
    except Exception:
        print("[2/3 check] check.py FAILED:")
        print("\n".join("   " + l for l in log.splitlines()[-20:]))
        print("RESULT FAIL errors=checker asset=%s preview=None" % asset)
        sys.exit(2)
    i = r["info"]
    print(f"[2/3 check] errors {len(r['errors'])}, warnings {len(r['warnings'])} | size {i.get('size')} m | tris {i.get('tris', {}).get('main')}"
          f"/LOD1 {i.get('tris', {}).get('lod1')}/LOD2 {i.get('tris', {}).get('lod2')} | windows {i.get('windows')}")
    print(f"   coplanar {i.get('coplanar')} win_blocked {i.get('win_blocked')} texel {i.get('texel_px_per_m')}")
    for tag, lst in (("ERROR", r["errors"]), ("WARN", r["warnings"])):
        for e in lst:
            ex = "; ".join(str(x) for x in e["examples"][:a.list])
            print(f"   {tag} {e['msg']}" + (f"  e.g. {ex}" if ex else ""))

    # 3) preview: previews/<asset>.png (latest) + previews/progress/<asset>/NNN_HHMMSS_<label>.png (history)
    prev = None
    ok = not r["errors"]
    if not a.no_render:
        prev = os.path.join(ROOT, "previews", asset + ".png")
        code, log = run([py, os.path.join(HERE, "render.py"), os.path.join(out, asset), "-o", prev, "--views", a.views, "--size", a.size])
        if code != 0:
            print(f"[3/3 preview] FAILED: {log.strip().splitlines()[-1] if log.strip() else '?'}")
            prev = None
        else:
            hist = save_progress(prev, asset, ok, len(r["errors"]), a.label)
            print(f"[3/3 preview] {os.path.relpath(prev, ROOT)}  (history: {os.path.relpath(hist, ROOT)})")
    # 4) photo comparison (only if photo_refs.json exists and images are rendered)
    mism = None
    photo_lines = []
    if not a.no_render and os.path.exists(os.path.join(ROOT, "photo_refs.json")):
        code, log = run([py, os.path.join(HERE, "photo_check.py"), os.path.join(out, asset)])
        mism = sum(1 for l in log.splitlines() if l.strip().startswith("MISMATCH"))
        print(f"[photo] {mism} mismatch(es) vs photos - sheets in previews/photo_check/")
        for l in log.splitlines():
            if l.strip().startswith(("MISMATCH", "MATCH", "INFO")):
                s = l.strip().replace("MISMATCH", "PHOTO_MISMATCH", 1)
                photo_lines.append(s)
                print("   " + s)
    # 5) tile-by-tile detail comparison (opt-in or --full) -> where is the model too simple?
    tiles = dict(checked=False, simplified=[], detail=[], detail_color=[], color_off=[], tiles_off=0, tiles_total=0)
    if (a.tiles or a.full) and not a.no_render and os.path.exists(os.path.join(ROOT, "photo_refs.json")):
        code, log = run([py, os.path.join(HERE, "tile_compare.py"), os.path.join(out, asset), "--top", "3"])
        tiles["checked"] = True
        print("[tiles] detail vs photos (SIMPLIFIED = model lacks detail the photo has) - open previews/tiles/*_map.png")
        for l in log.splitlines():
            s = l.strip()
            if s.startswith(("TILE", "DETAIL", "COLOR", "ZONES", "INFO")):
                print("   " + s)
            if "SIMPLIFIED" in s and s.startswith("TILE "):
                tiles["simplified"].append(s)
            elif s.startswith("DETAIL_COLOR "):
                tiles["detail_color"].append(s)
                m = re.search(r"tiles_off\s+(\d+)/(\d+)", s)
                if m:
                    tiles["tiles_off"] += int(m.group(1))
                    tiles["tiles_total"] += int(m.group(2))
            elif s.startswith("DETAIL "):
                tiles["detail"].append(s)
            elif "COLOR_OFF" in s:
                tiles["color_off"].append(s)
    # 6) LOD see-through gate (--full; needs Blender and a .blend)
    lod = dict(checked=False, status="SKIP", line=None, notes=[])
    if a.full:
        lscript = os.path.join(KIT, "tools", "qa", "lod_check.py")
        if not os.path.exists(lscript):
            lod["notes"].append("tools/qa/lod_check.py not found")
            print("[lod] SKIP - tools/qa/lod_check.py not found")
        else:
            code, log = run([py, lscript, os.path.join(out, asset), "--res", "512"])
            lines_l = [l.strip() for l in log.splitlines() if l.strip()]
            line = next((l for l in reversed(lines_l) if l.startswith("LODCHECK")), None)
            if line:
                lod["checked"] = True
                lod["line"] = line
                lod["status"] = "PASS" if "LODCHECK PASS" in line else "FAIL"
                print(f"[lod] {line}")
                for l in lines_l:
                    if l.startswith(("HOLE", "NO_TEXTURE", "at gen")):
                        print("   " + l)
            else:
                why = next((l for l in reversed(lines_l) if ".blend" in l or "Blender" in l), "")
                lod["notes"].append(why or (lines_l[-1] if lines_l else "no output"))
                print("[lod] SKIP - needs FBX/.blend and Blender" + (f" ({why})" if why else ""))
    # 7) one GATE line + optional JSON (RESULT/exit code keep the old meaning: check errors only)
    reasons = []
    if r["errors"]:
        reasons.append(f"check_errors={len(r['errors'])}")
    if mism:
        reasons.append(f"photo_mismatch={mism}")
    if lod["status"] == "FAIL":
        reasons.append("lod=FAIL")
    gate = "PASS" if not reasons else "FAIL"
    tstat = (f"tiles_off={tiles['tiles_off']}/{tiles['tiles_total']} simplified={len(tiles['simplified'])}"
             if tiles["checked"] else "tiles=off")
    pstat = f"photo_mismatch={mism}" if mism is not None else "photo=off"
    print(f"GATE {gate}" + (f" reasons={','.join(reasons)}" if reasons else "")
          + f" lod={lod['status']} {tstat} {pstat}")
    if a.json is not None:
        jp = a.json or os.path.join(out, asset, "_check", "gate.json")
        jp = jp if os.path.isabs(jp) else os.path.join(ROOT, jp)
        parent = os.path.dirname(jp)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(dict(asset=asset, label=a.label, time=time.strftime("%Y-%m-%d %H:%M:%S"),
                           build=dict(asset=asset, fbx=fbx, warnings=build_warns),
                           check=dict(errors=[e["msg"] for e in r["errors"]],
                                      warnings=[e["msg"] for e in r["warnings"]], info=i,
                                      report=os.path.relpath(rep, ROOT)),
                           photo=dict(checked=mism is not None, mismatch=mism, lines=photo_lines),
                           tiles=tiles, lod=lod,
                           gate=dict(status=gate, reasons=reasons)), f, ensure_ascii=False, indent=1)
        print(f"[json] {os.path.relpath(jp, ROOT)}")
    print(f"RESULT {'PASS' if ok else 'FAIL'} errors={len(r['errors'])} warnings={len(r['warnings'])}"
          + (f" photo_mismatch={mism}" if mism is not None else "") + f" asset={asset} "
          f"preview={os.path.relpath(prev, ROOT) if prev else None}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
