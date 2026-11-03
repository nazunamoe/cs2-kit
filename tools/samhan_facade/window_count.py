import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB  # noqa: E402,F401
import sys, collections
import importlib
B = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('FACADE_GEN', 'ResidentialHighSamhanGoldenviewA_cs2'))
TA = getattr(B, 'TA', B)
calls = collections.Counter(); kinds = collections.Counter()
orig = TA.window_unit
def wu(main, wins, e, cm, w, z0, h, f, cols, low_h=0.0):
    calls[f] += 1
    return orig(main, wins, e, cm, w, z0, h, f, cols, low_h)
TA.window_unit = wu
A = TA.make_atlas()
TA.build_tower(A, B.FLOORS, getattr(B, 'MIRROR', False))
for f in range(25, 34): print(f, calls[f])
print("REFUGE", TA.REFUGE_FLOOR, "DETAIL", TA.DETAIL)
