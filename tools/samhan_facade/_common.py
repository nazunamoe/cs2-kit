"""shared settings for tools/samhan_facade.
Run every tool from the project root (folder with the generator, photos, tools/ and previews/) or set FACADE_ROOT.
FACADE_GEN = generator module of the type A tower (default: *A_cs2.py found in the project root),
FACADE_GLB = scan file name in the project root (default 3dview.glb),
FACADE_MESHES = comma list of scan mesh names, reference first. Comments ASCII only."""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("FACADE_ROOT") or os.getcwd())


def _find_gen():
    """FACADE_GEN, else the type A generator in ROOT (*A_cs2.py, else the only *_cs2.py besides the example)"""
    if os.environ.get("FACADE_GEN"):
        return os.environ["FACADE_GEN"]
    fs = sorted(f for f in os.listdir(ROOT) if f.endswith("_cs2.py") and f != "example_building_cs2.py")
    pick = [f for f in fs if f.endswith("A_cs2.py")] or fs
    return pick[0][:-3] if pick else "example_building_cs2"


GEN = _find_gen()
GLB = os.path.join(ROOT, os.environ.get("FACADE_GLB", "3dview.glb"))
# scan mesh name parts (glb_measure.py --list): first = reference tower, the others are compared with it
MESHES = tuple(os.environ.get("FACADE_MESHES", "981188,981185,981186").split(","))
for p in (ROOT, os.path.join(ROOT, "tools"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.makedirs(os.path.join(ROOT, "previews"), exist_ok=True)


def gen():
    return importlib.import_module(GEN)
