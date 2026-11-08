# -*- coding: utf-8 -*-
"""
run_blender.py — Blender(또는 bpy 모듈) 를 찾아서 생성기를 백그라운드로 실행

사용:
  python tools/run_blender.py --find                              찾기만 (경로를 tools/blender_path.txt / blender_py.txt 에 저장)
  python tools/run_blender.py my_building_cs2.py -- --out output       FBX 까지 생성 (bpy 모듈 → Blender 앱 순)
  python tools/run_blender.py --obj my_building_cs2.py -- --out output  일반 Python 으로 OBJ 만 생성 (반복용)
  python tools/run_blender.py --fbx2obj output/<asset>                FBX → _check/*.obj (check.py·render.py 용)
  python tools/run_blender.py --set "D:\\Blender\\blender.exe"       Blender 앱 경로 직접 지정·저장
  python tools/run_blender.py --set-py ".venv-bpy\\Scripts\\python.exe"  bpy 모듈이 설치된 Python 지정·저장

찾는 순서(FBX): BLENDER_PY 환경변수 → tools/blender_py.txt → .venv-bpy → 현재 python(import bpy)
                → BLENDER → tools/blender_path.txt → PATH(blender) → 레지스트리·Program Files·Steam …
엔진 선택: RUN_BLENDER_ENGINE=py|exe|obj (기본: bpy 모듈이 있으면 py, 없으면 exe, 둘 다 없으면 obj)
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
ROOT = os.path.dirname(HERE)
SAVE = os.path.join(HERE, "blender_path.txt")
SAVE_PY = os.path.join(HERE, "blender_py.txt")


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


def py_candidates():
    """bpy 모듈이 설치된 Python 후보. (Blender 앱 없이 FBX 를 쓰기 위한 경로)"""
    env = os.environ.get("BLENDER_PY")
    if env:
        yield env.strip().strip('"')
    if os.path.exists(SAVE_PY):
        with open(SAVE_PY, encoding="utf-8") as f:
            yield f.read().strip().strip('"')
    for p in (os.path.join(ROOT, ".venv-bpy", "Scripts", "python.exe"),
              os.path.join(ROOT, ".venv-bpy", "bin", "python")):
        if os.path.isfile(p):
            yield p
    yield sys.executable                      # 현재 인터프리터에 bpy 가 있을 수도


def bpy_version(py):
    """bpy 를 import 해서 버전 문자열을 돌려준다. 실패하면 None."""
    try:
        r = subprocess.run([py, "-c", "import bpy; print(bpy.app.version_string)"],
                           capture_output=True, text=True, timeout=180)
    except Exception:                          # noqa: BLE001
        return None
    out = (r.stdout or "").strip().splitlines()
    return out[-1] if (r.returncode == 0 and out) else None


def find_bpy(verbose=True):
    for p in py_candidates():
        if p and os.path.isfile(p):
            ver = bpy_version(p)
            if not ver:
                continue
            with open(SAVE_PY, "w", encoding="utf-8") as f:
                f.write(p)
            if verbose:
                print(f"[bpy] {p}  (Blender {ver} module)  -> saved to {SAVE_PY}")
            return p
    return None


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
    force_obj = "--obj" in argv
    if force_obj:
        argv.remove("--obj")
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
    if "--set-py" in argv:
        p = argv[argv.index("--set-py") + 1].strip('"')
        if not os.path.isfile(p):
            raise SystemExit(f"file not found: {p}")
        ver = bpy_version(p)
        if not ver:
            raise SystemExit(f"this python has no bpy module: {p}")
        with open(SAVE_PY, "w", encoding="utf-8") as f:
            f.write(p)
        print(f"[bpy] saved: {p}  (Blender {ver} module)")
        return
    if "--find" in argv:
        py = find_bpy()
        bl = find_blender()
        sys.exit(0 if (py or bl) else 1)
    if "--fbx2obj" in argv:
        folder = os.path.abspath(argv[argv.index("--fbx2obj") + 1])
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "_cs2kit_fbx2obj.py")   # 저장소를 더럽히지 않는다
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(FBX2OBJ)
        py = find_bpy(verbose=False)
        if py:                                  # bpy 모듈: Blender 앱 없이 FBX 읽기
            r = subprocess.run([py, tmp, "--", folder])
            sys.exit(r.returncode)
        bl = find_blender()
        if not bl:
            raise SystemExit("cannot read FBX without Blender or bpy "
                             "(cs2kit generators also write _check/*.obj)")
        r = subprocess.run([bl, "--background", "--factory-startup", "--python", tmp, "--", folder])
        sys.exit(r.returncode)
    if not argv:
        print(__doc__)
        return
    script = os.path.abspath(argv[0])
    engine = (os.environ.get("RUN_BLENDER_ENGINE") or "").strip().lower()
    py = bl = None
    if not force_obj:
        if engine in ("", "py"):
            py = find_bpy(verbose=True)
        if not py and engine in ("", "exe", "blender"):
            bl = find_blender(verbose=True)
    if py:
        cmd = [py, script] + gen_args          # bpy 모듈: 일반 python 처럼 실행
    elif bl:
        cmd = [bl, "--background", "--factory-startup", "--python-exit-code", "1", "--python", script, "--"] + gen_args
    else:
        if not force_obj:
            print("[blender] no bpy module / Blender -> running with plain python (OBJ only, NO FBX)")
        cmd = [sys.executable, script] + gen_args
    print("[run] " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    r = subprocess.run(cmd, cwd=os.path.dirname(script))
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
