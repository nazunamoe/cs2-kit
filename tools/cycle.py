# -*- coding: utf-8 -*-
"""Shared build/check/render/photo/LOD gate.

Modes: quick = OBJ + geometry checks; visual = OBJ + preview + photo checks;
final = FBX + preview + photo + tiles + LOD + strict JSON gate.
Legacy --no-render/--tiles/--full options remain accepted.
PASS applies only to checks that ran. NOT_CHECKED is not PASS; NOT_APPLICABLE means no photo refs exist.
Strict exit codes: 0 PASS, 1 FAIL, 2 INCOMPLETE. Non-strict RESULT keeps the legacy geometry-only meaning.
Use tools/agent.py for compact next_action JSON, resume state, and visual-review recording.
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
from agent_actions import agent_summary  # noqa: E402


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
    ap.add_argument("--mode", choices=("quick", "visual", "final"), help="quick=OBJ/check, visual=OBJ/render/photo, final=FBX/full checks")
    ap.add_argument("--strict", action="store_true", help="fail or mark incomplete when a required final check did not run")
    a = ap.parse_args()
    mode = a.mode or ("final" if a.full else "quick" if a.no_render else "visual")
    if mode == "quick":
        a.no_render = True
    if mode == "final":
        a.full = True
        a.strict = True
        if a.json is None:
            a.json = ""
    py = sys.executable
    out = os.path.join(ROOT, a.out)

    # 1) 생성
    build_cmd = [py, os.path.join(HERE, "run_blender.py")]
    if mode != "final":
        build_cmd.append("--obj")
    build_cmd += [os.path.abspath(a.generator), "--", "--out", out]
    code, log = run(build_cmd)
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

    lod = dict(checked=False, status="NOT_CHECKED", line=None, notes=[])
    lod_future = None
    lod_executor = None
    if a.full:
        lscript = os.path.join(KIT, "tools", "qa", "lod_check.py")
        if not os.path.exists(lscript):
            lod["notes"].append("tools/qa/lod_check.py not found")
            print("[lod] NOT_CHECKED - tools/qa/lod_check.py not found")
        else:
            import concurrent.futures as cf
            lod_executor = cf.ThreadPoolExecutor(max_workers=1)
            lod_future = lod_executor.submit(run, [py, lscript, os.path.join(out, asset), "--res", "512"])

    # 3) preview
    prev = None
    ok = not r["errors"]
    preview_status = "NOT_CHECKED"
    if not a.no_render:
        prev = os.path.join(ROOT, "previews", asset + ".png")
        code, log = run([py, os.path.join(HERE, "render.py"), os.path.join(out, asset), "-o", prev, "--views", a.views, "--size", a.size])
        if code != 0:
            preview_status = "FAIL"
            print(f"[3/3 preview] FAILED: {log.strip().splitlines()[-1] if log.strip() else '?'}")
            prev = None
        else:
            preview_status = "PASS"
            hist = save_progress(prev, asset, ok, len(r["errors"]), a.label)
            print(f"[3/3 preview] {os.path.relpath(prev, ROOT)}  (history: {os.path.relpath(hist, ROOT)})")

    refs_exist = os.path.exists(os.path.join(ROOT, "photo_refs.json"))
    mism = None
    photo_lines = []
    photo_status = "NOT_APPLICABLE" if not refs_exist else "NOT_CHECKED"
    tiles = dict(checked=False, status="NOT_APPLICABLE" if not refs_exist else "NOT_CHECKED",
                 simplified=[], detail=[], detail_color=[], color_off=[], tiles_off=0, tiles_total=0)
    if not a.no_render and refs_exist:
        visual_cmd = [py, os.path.join(HERE, "visual_check.py"), os.path.join(out, asset)]
        if a.tiles or a.full:
            visual_cmd += ["--tiles", "--top", "3"]
            tiles["checked"] = True
        visual_code, log = run(visual_cmd)
        section = ""
        summary = ""
        for raw in log.splitlines():
            s = raw.strip()
            if s.startswith("[photo]"):
                section = "photo"
                continue
            if s.startswith("[tiles]"):
                section = "tiles"
                continue
            if s.startswith("[visual]"):
                summary = s
                continue
            if section == "photo" and s.startswith(("MISMATCH", "MATCH", "INFO")):
                item = s.replace("MISMATCH", "PHOTO_MISMATCH", 1)
                photo_lines.append(item)
                print("   " + item)
            elif section == "tiles" and s.startswith(("TILE", "DETAIL", "COLOR", "ZONES", "INFO")):
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
        mism = sum(1 for l in log.splitlines() if l.strip().startswith("MISMATCH"))
        pm = re.search(r"photo_status=(\w+)", summary)
        tm = re.search(r"tile_status=(\w+)", summary)
        photo_status = pm.group(1) if pm else "FAIL" if visual_code else "PASS"
        if tm:
            tiles["status"] = tm.group(1)
        elif tiles["checked"]:
            tiles["status"] = "FAIL"
        print(f"[photo] status={photo_status} mismatch={mism}; [tiles] status={tiles['status']}")

    if lod_future is not None:
        code, log = lod_future.result()
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
            print("[lod] NOT_CHECKED - needs FBX/.blend and Blender" + (f" ({why})" if why else ""))
    if lod_executor is not None:
        lod_executor.shutdown()

    reasons = []
    incomplete = []
    if r["errors"]:
        reasons.append(f"check_errors={len(r['errors'])}")
    if preview_status == "FAIL":
        reasons.append("preview=FAIL")
    if mism:
        reasons.append(f"photo_mismatch={mism}")
    if photo_status == "FAIL" and not mism:
        reasons.append("photo=FAIL")
    if tiles["status"] == "FAIL":
        reasons.append("tiles=FAIL")
    if lod["status"] == "FAIL":
        reasons.append("lod=FAIL")
    if a.strict:
        if mode == "final" and not fbx:
            incomplete.append("fbx=NOT_CREATED")
        for name, status in (("preview", preview_status), ("photo", photo_status),
                             ("tiles", tiles["status"]), ("lod", lod["status"])):
            if status == "NOT_CHECKED":
                incomplete.append(f"{name}=NOT_CHECKED")
    gate = "FAIL" if reasons else "INCOMPLETE" if incomplete else "PASS"
    agent = agent_summary(r)
    if r["errors"]:
        next_action = dict(command=f"python tools/cycle.py {a.generator} --mode quick --json",
                           reason=agent["exact_fix_instruction"])
    elif mism:
        next_action = dict(command=f"python tools/cycle.py {a.generator} --mode visual --json",
                           reason="Fix only PHOTO_MISMATCH items; do not change geometry for INFO-only weak patterns")
    elif incomplete:
        next_action = dict(command=f"python tools/cycle.py {a.generator} --mode final --strict --json",
                           reason="Required checks missing: " + ", ".join(incomplete))
    elif reasons:
        next_action = dict(command=f"python tools/cycle.py {a.generator} --mode {mode} --json",
                           reason="Fix the failed check shown in this report")
    else:
        next_action = dict(command=None, reason="no fix needed")

    tstat = (f"tiles_off={tiles['tiles_off']}/{tiles['tiles_total']} simplified={len(tiles['simplified'])}"
             if tiles["checked"] else f"tiles={tiles['status']}")
    pstat = f"photo_mismatch={mism}" if mism is not None else f"photo={photo_status}"
    print(f"GATE {gate}" + (f" reasons={','.join(reasons)}" if reasons else "")
          + (f" incomplete={','.join(incomplete)}" if incomplete else "")
          + f" lod={lod['status']} {tstat} {pstat}")
    if a.json is not None:
        jp = a.json or os.path.join(out, asset, "_check", "gate.json")
        jp = jp if os.path.isabs(jp) else os.path.join(ROOT, jp)
        parent = os.path.dirname(jp)
        if parent:
            os.makedirs(parent, exist_ok=True)
        checks = dict(build="PASS", geometry="FAIL" if r["errors"] else "PASS", preview=preview_status,
                      photo=photo_status, tiles=tiles["status"], lod=lod["status"], fbx="PASS" if fbx else "NOT_CREATED")
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(dict(status=gate, project=NAME, generator=os.path.basename(a.generator), mode=mode,
                           checks=checks, errors=r["errors"], next_action=next_action,
                           artifacts=dict(preview=os.path.relpath(prev, ROOT) if prev else None,
                                          report=os.path.relpath(rep, ROOT)),
                           asset=asset, label=a.label, time=time.strftime("%Y-%m-%d %H:%M:%S"),
                           build=dict(asset=asset, fbx=fbx, warnings=build_warns),
                           check=dict(errors=[e["msg"] for e in r["errors"]],
                                      warnings=[e["msg"] for e in r["warnings"]], info=i,
                                      report=os.path.relpath(rep, ROOT)),
                           photo=dict(checked=mism is not None, mismatch=mism, lines=photo_lines, status=photo_status),
                           tiles=tiles, lod=lod, agent=agent,
                           gate=dict(status=gate, reasons=reasons, incomplete=incomplete)), f, ensure_ascii=False, indent=1)
        print(f"[json] {os.path.relpath(jp, ROOT)}")
    print(f"RESULT {'PASS' if ok else 'FAIL'} errors={len(r['errors'])} warnings={len(r['warnings'])}"
          + (f" photo_mismatch={mism}" if mism is not None else "") + f" asset={asset} "
          f"preview={os.path.relpath(prev, ROOT) if prev else None} verification={gate}")
    if a.strict:
        sys.exit(0 if gate == "PASS" else 1 if gate == "FAIL" else 2)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
