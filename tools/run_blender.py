# -*- coding: utf-8 -*-
"""
run_blender.py — Blender 를 찾아서 생성기를 백그라운드로 실행 (PATH 설정과 무관하게 동작)

사용:
  python tools/run_blender.py --find                              찾기만 (찾은 경로를 tools/blender_path.txt 에 저장)
  python tools/run_blender.py my_building_cs2.py -- --out output    생성기 실행 (-- 뒤는 생성기 인자)
  python tools/run_blender.py --fbx2obj output/<asset>             FBX → _check/*.obj (check.py·render.py 용)
  python tools/run_blender.py --set "D:\\Blender\\blender.exe"       경로 직접 지정·저장

찾는 순서: 환경변수 BLENDER → tools/blender_path.txt → PATH(blender) → Windows 레지스트리·Program Files·Steam
           → macOS /Applications → Linux /usr/bin, /snap, ~/blender*
Blender 가 없으면 생성기를 일반 python 으로 실행 (cs2kit 은 OBJ 로 내보냄 → 검사·미리보기는 가능, FBX 는 안 나옴)
"""
import glob
import os
import shutil
import subprocess
import sys
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(HERE, "blender_path.txt")


def _ver_key(p):
    import re
    m = re.findall(r"(\d+)\.(\d+)", p)
    return tuple(int(x) for x in m[-1]) if m else (0, 0)


def candidates():
    env = os.environ.get("BLENDER")
    if env:
        yield env.strip().strip('"')
    if os.path.exists(SAVE):
        with open(SAVE, encoding="utf-8") as f:
            yield f.read().strip().strip('"')
    for n in ("blender", "blender.exe"):
        w = shutil.which(n)
        if w:
            yield w
    if os.name == "nt":
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for key in (r"SOFTWARE\Classes\blendfile\shell\open\command", r"SOFTWARE\Classes\Applications\blender.exe\shell\open\command"):
                    try:
                        with winreg.OpenKey(root, key) as k:
                            cmd = winreg.QueryValue(k, None)
                            exe = cmd.split('"')[1] if cmd.startswith('"') else cmd.split()[0]
                            yield exe.replace("blender-launcher.exe", "blender.exe")
                    except OSError:
                        pass
        except ImportError:
            pass
        pats = []
        for base in {os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", ""), r"D:\Program Files", r"C:\Blender", r"D:\Blender"}:
            if base:
                pats += [os.path.join(base, "Blender Foundation", "*", "blender.exe"), os.path.join(base, "Blender*", "blender.exe"),
                         os.path.join(base, "Programs", "Blender Foundation", "*", "blender.exe")]
        pats += [r"C:\Program Files\WindowsApps\BlenderFoundation.Blender*\Blender\blender.exe"]   # MS Store
        for drive in "CDEFG":
            pats += [fr"{drive}:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
                     fr"{drive}:\SteamLibrary\steamapps\common\Blender\blender.exe"]
        found = []
        for p in pats:
            found += glob.glob(p)
        for p in sorted(set(found), key=_ver_key, reverse=True):
            yield p
    elif sys.platform == "darwin":
        for p in sorted(glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender") +
                        glob.glob(os.path.expanduser("~/Applications/Blender*.app/Contents/MacOS/Blender")), key=_ver_key, reverse=True):
            yield p
    else:
        for p in ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"] + \
                 sorted(glob.glob(os.path.expanduser("~/blender*/blender")) + glob.glob("/opt/blender*/blender"), key=_ver_key, reverse=True):
            yield p


def find_blender(verbose=True):
    for c in candidates():
        if c and os.path.isfile(c):
            try:
                out = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=120).stdout
                ver = out.splitlines()[0] if out else "?"
            except Exception as e:  # noqa
                if verbose:
                    print(f"[blender] cannot run {c}: {e}")
                continue
            with open(SAVE, "w", encoding="utf-8") as f:
                f.write(c)
            if verbose:
                print(f"[blender] {c}  ({ver})  -> saved to {SAVE}")
            return c
    if verbose:
        print("[blender] NOT FOUND. Set it: python tools/run_blender.py --set \"C:\\...\\blender.exe\"")
    return None


FBX2OBJ = r'''
import bpy, glob, os, sys
folder = sys.argv[sys.argv.index("--") + 1]
out = os.path.join(folder, "_check"); os.makedirs(out, exist_ok=True)
for fbx in sorted(glob.glob(os.path.join(folder, "*.fbx"))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if "fbx_import" in dir(bpy.ops.wm):      # Blender 4.5+/5.x 새 FBX 임포터
        bpy.ops.wm.fbx_import(filepath=fbx)
    else:
        bpy.ops.import_scene.fbx(filepath=fbx)
    name = os.path.splitext(os.path.basename(fbx))[0]
    p = os.path.join(out, name + ".obj")
    if "obj_export" in dir(bpy.ops.wm):
        bpy.ops.wm.obj_export(filepath=p, export_selected_objects=False, export_materials=False, export_normals=False,
                              forward_axis="NEGATIVE_Z", up_axis="Y", apply_modifiers=True, export_triangulated_mesh=False)
    else:
        bpy.ops.export_scene.obj(filepath=p, use_materials=False, use_normals=False, axis_forward="-Z", axis_up="Y")
    print("[fbx2obj]", p)
'''


def main():
    argv = sys.argv[1:]
    gen_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, gen_args = argv[:i], argv[i + 1:]
    if "--set" in argv:
        p = argv[argv.index("--set") + 1].strip('"')
        if not os.path.isfile(p):
            raise SystemExit(f"file not found: {p}")
        with open(SAVE, "w", encoding="utf-8") as f:
            f.write(p)
        print(f"[blender] saved: {p}")
        return
    if "--find" in argv:
        sys.exit(0 if find_blender() else 1)
    if "--fbx2obj" in argv:
        folder = os.path.abspath(argv[argv.index("--fbx2obj") + 1])
        bl = find_blender()
        if not bl:
            raise SystemExit("cannot read FBX without Blender (cs2kit generators also write _check/*.obj)")
        tmp = os.path.join(HERE, "_fbx2obj.py")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(FBX2OBJ)
        r = subprocess.run([bl, "--background", "--factory-startup", "--python", tmp, "--", folder])
        sys.exit(r.returncode)
    if not argv:
        print(__doc__)
        return
    script = os.path.abspath(argv[0])
    bl = find_blender(verbose=True)
    if bl:
        cmd = [bl, "--background", "--factory-startup", "--python-exit-code", "1", "--python", script, "--"] + gen_args
    else:
        print("[blender] Blender not found -> running with plain python (OBJ only, NO FBX)")
        cmd = [sys.executable, script] + gen_args
    print("[run] " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    r = subprocess.run(cmd, cwd=os.path.dirname(script))
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
