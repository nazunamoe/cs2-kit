# -*- coding: utf-8 -*-
"""Report IFC -> GLB conversion routes and emit a Blender conversion script.

The kit does not read IFC/DWG directly. Convert the model to GLB first, then use
`tools/agent.py glb-mass` for the simplified mass.

  python tools/ifc_to_glb.py --check --json
  python tools/ifc_to_glb.py --plan
  python tools/ifc_to_glb.py --emit-script ifc_to_glb_blender.py
  python tools/ifc_to_glb.py --run --ifc photos/model.ifc --glb photos/model.glb
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def find_blender():
    saved = os.path.join(HERE, "blender_path.txt")
    try:
        with open(saved, encoding="utf-8") as f:
            p = f.read().strip()
        if p and os.path.isfile(p):
            return p
    except OSError:
        pass
    try:
        import run_blender
        return run_blender.find_blender(verbose=False)
    except Exception:
        return shutil.which("blender")


def find_blenderbim():
    roots = [os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender"),
             os.path.expanduser("~/.config/blender")]
    hits = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for pat in ("*/scripts/addons/*", "*/extensions/*/*", "*/scripts/addons/*/*"):
            for p in glob.glob(os.path.join(root, pat)):
                low = os.path.basename(p).lower()
                if "blenderbim" in low or "bonsai" in low or low.startswith("ifc"):
                    hits.append(p)
    return hits[0] if hits else None


def probe():
    blender = find_blender()
    ifcopenshell = None
    try:
        import ifcopenshell  # noqa: F401
        ifcopenshell = "python module"
    except Exception:
        pass
    return {
        "blender": blender,
        "blenderbim": find_blenderbim(),
        "ifcopenshell": ifcopenshell,
        "ifcconvert": shutil.which("IfcConvert") or shutil.which("ifcconvert"),
        "freecad": shutil.which("FreeCADCmd") or shutil.which("FreeCADCmd.exe"),
    }


BLENDER_SCRIPT = r'''import bpy, os, sys

def arg(i, default=""):
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        return rest[i] if i < len(rest) else default
    return default

ifc = arg(0)
glb = arg(1)
if not ifc or not glb:
    raise SystemExit("usage: blender --background --python this.py -- <input.ifc> <output.glb>")
if not os.path.isfile(ifc):
    raise SystemExit("no such IFC: " + ifc)

bpy.ops.wm.read_factory_settings(use_empty=True)
loaded = False
if hasattr(bpy.ops, "bim") and hasattr(bpy.ops.bim, "load_project"):
    bpy.ops.bim.load_project(filepath=ifc)
    loaded = True
elif hasattr(bpy.ops, "import_scene") and hasattr(bpy.ops.import_scene, "ifc"):
    bpy.ops.import_scene.ifc(filepath=ifc)
    loaded = True
if not loaded:
    raise SystemExit("no IFC importer: install BlenderBIM/Bonsai or the IfcOpenShell Blender add-on")

os.makedirs(os.path.dirname(os.path.abspath(glb)) or ".", exist_ok=True)
if hasattr(bpy.ops.wm, "gltf_export"):
    bpy.ops.wm.gltf_export(filepath=glb, export_format="GLB")
else:
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=False)
print("[ifc_to_glb] wrote", glb)
'''


def emit_script(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(BLENDER_SCRIPT)
    return os.path.abspath(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report converters found on this machine")
    ap.add_argument("--plan", action="store_true", help="print the recommended conversion routes")
    ap.add_argument("--emit-script", default="", help="write the Blender IFC -> GLB script")
    ap.add_argument("--run", action="store_true", help="convert with IfcConvert or Blender when available")
    ap.add_argument("--ifc", default="", help="input IFC for --run")
    ap.add_argument("--glb", default="", help="output GLB for --run")
    ap.add_argument("--blender", default="", help="Blender executable for --run")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    found = probe()
    if a.blender:
        found["blender"] = a.blender

    if a.emit_script:
        path = emit_script(a.emit_script)
        print(json.dumps({"status": "OK", "script": path}, ensure_ascii=False) if a.json else
              f"[ifc] wrote {path}")

    if a.check:
        has_converter = bool(found["ifcconvert"] or found["freecad"]
                             or (found["blender"] and (found["blenderbim"] or found["ifcopenshell"])))
        found["status"] = "OK" if has_converter else "MISSING"
        found["install"] = None if has_converter else "install BlenderBIM/Bonsai (Blender), IfcConvert or FreeCAD"
        print(json.dumps(found, ensure_ascii=False) if a.json else
              "\n".join(f"[ifc] {k}: {v or '-'}" for k, v in found.items()))
        return 0 if has_converter else 2

    if a.plan:
        print("IFC -> GLB routes (pick one):")
        print("1. Blender + BlenderBIM/Bonsai: install the add-on, then")
        print("   python tools/ifc_to_glb.py --emit-script ifc_to_glb_blender.py")
        print("   blender --background --python ifc_to_glb_blender.py -- model.ifc model.glb")
        print("2. IfcConvert (IfcOpenShell CLI): IfcConvert model.ifc model.glb")
        print("3. FreeCAD: import IFC, export GLB (mesh), then run glb-mass")
        print("Then: python tools/agent.py glb-mass --project P --json -- photos/model.glb --list")
        print("Check units, ground z, front direction and hidden meshes before facade work.")
        return 0

    if a.run:
        if not a.ifc or not a.glb:
            raise SystemExit("--run needs --ifc <input> --glb <output>")
        if not os.path.isfile(a.ifc):
            raise SystemExit(f"no such IFC: {a.ifc}")
        if found["ifcconvert"]:
            cmd = [found["ifcconvert"], a.ifc, a.glb]
        elif found["blender"] and (found["blenderbim"] or found["ifcopenshell"]):
            script = emit_script(os.path.join(os.path.dirname(os.path.abspath(a.glb)) or ".", "_ifc_to_glb_blender.py"))
            cmd = [found["blender"], "--background", "--python", script, "--", a.ifc, a.glb]
        else:
            raise SystemExit("no IFC converter found - run --check, --plan, and install BlenderBIM or IfcConvert")
        print("[ifc] " + " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(a.glb):
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            raise SystemExit("conversion failed: " + (detail[-1] if detail else f"exit {r.returncode}"))
        print(json.dumps({"status": "OK", "ifc": a.ifc, "glb": a.glb}, ensure_ascii=False) if a.json else
              f"[ifc] wrote {a.glb}")
        return 0

    if not (a.check or a.plan or a.emit_script):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
