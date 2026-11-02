# -*- coding: utf-8 -*-
"""
example_curtainwall_cs2.py - cs2kit example: 14-floor curtain-wall-look apartment (glass skin on all 4 sides).
Copy this file to start a curtain wall building. Run: python tools/cycle.py example_curtainwall_cs2.py --label cw
Values to take from TASK.md / photos: module width, spandrel height, glass colour, vent (louver) panels, floors.
Comments must stay ASCII/English.
"""
import os
import sys

def _find_kit():
    """generators live in projects/<name>/ ; cs2kit.py is in the kit root (one or two folders up)"""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, "cs2kit.py")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(os.path.abspath(__file__))


sys.path.insert(0, _find_kit())
import cs2kit as K  # noqa: E402

NAME = "ResidentialHighKExampleCw01"
LEVEL = 1
W, D = 24.0, 16.0
FLOORS = 14
FH = 3.0
BASE_H = 5.0           # lobby / commercial base (stone), curtain wall starts above it
PARAPET = 1.2
MODULE_W = 1.5         # estimated: typical apartment curtain wall module 1.2~1.8 m
SPANDREL_H = 0.95      # estimated: opaque band at the slab (slab 0.25 + 0.7 panel)


def make_atlas(size=2048):
    A = K.Atlas(size=size, pad=8)
    A.add("stone", color=(120, 114, 108), gloss=0.35, px=512, tile=(3.0, 2.9), painter=lambda c: (c.joints(3, 5, 0.012, darken=0.35), c.grain(amp=5)))
    A.add("wall", color=(205, 208, 210), gloss=0.2, px=256, tile=(4.0, 4.0), painter=lambda c: c.grain(amp=3, height=0.1))
    A.add("frame", color=(58, 62, 68), metal=0.8, gloss=0.6, px=32)
    A.add("spandrel", color=(92, 104, 112), metal=0.3, gloss=0.7, px=64)
    A.add("louver", color=(150, 154, 156), metal=0.6, gloss=0.4, px=64)
    A.add("roof", color=(128, 134, 138), gloss=0.1, px=256, tile=(4.0, 4.0), painter=lambda c: c.grain(amp=8))
    A.add("led", color=(250, 246, 236), emissive=(255, 236, 200), px=32)
    return A


def vent(i, f):
    """every 4th module on every floor is a louver (vent) panel, ground-facing modules stay glass"""
    return "louver" if i % 4 == 3 else None


def build(A):
    main, lod1 = K.MeshBuilder(A), K.MeshBuilder(A)
    lod2 = K.MeshBuilder(A, split_tiles=False)
    gls, lod1_gls = K.MeshBuilder(A), K.MeshBuilder(A)
    wins = K.WindowSet()
    x0, x1, y0, y1 = -W / 2, W / 2, 0.0, D
    top = BASE_H + FLOORS * FH
    for mb in (main, lod1):
        mb.box(x0, x1, y0, y1, 0, BASE_H, "stone", skip=("bottom", "top"))
        mb.box(x0, x1, y0, y1, BASE_H, top, dict(default="wall", top="roof"), skip=("bottom",))
    lod2.box(x0, x1, y0, y1, 0, top + PARAPET, dict(default="wall", top="roof"), skip=("bottom",))
    t = 0.25
    for mb in (main, lod1):
        mb.box(x0, x1, y0, y0 + t, top, top + PARAPET, "wall", skip=("bottom",))
        mb.box(x0, x1, y1 - t, y1, top, top + PARAPET, "wall", skip=("bottom",))
        mb.box(x0, x0 + t, y0 + t, y1 - t, top, top + PARAPET, "wall", skip=("bottom", "front", "back"))
        mb.box(x1 - t, x1, y0 + t, y1 - t, top, top + PARAPET, "wall", skip=("bottom", "front", "back"))
    # curtain wall on the 4 faces. Corners: front/back faces keep both end mullions, side faces drop theirs;
    # a corner post (0.12 m) closes the corner.
    kw = dict(fh=FH, module_w=MODULE_W, spandrel_h=SPANDREL_H, cell=vent)
    for mb_l1, mb_l2 in ((lod1, lod2),):
        K.curtainwall(main, "y", y0, -1, x0, x1, BASE_H, top, wins=wins, lod1=mb_l1, lod2=mb_l2, **kw)
        K.curtainwall(main, "y", y1, 1, x0, x1, BASE_H, top, wins=wins, **kw)
        K.curtainwall(main, "x", x0, -1, y0, y1, BASE_H, top, wins=wins, ends=(False, False), unit0=10, **kw)
        K.curtainwall(main, "x", x1, 1, y0, y1, BASE_H, top, wins=wins, ends=(False, False), unit0=20, **kw)
    # side faces have no end mullions, so close the four corners with posts
    for (cx, cy, sx, sy) in ((x0, y0, -1, -1), (x1, y0, 1, -1), (x0, y1, -1, 1), (x1, y1, 1, 1)):
        K.corner_post(main, cx, cy, sx, sy, 0.12, BASE_H, top)
    return dict(main=main, lod1=lod1, lod2=lod2, gls=gls, lod1_gls=lod1_gls, windows=wins)


if __name__ == "__main__":
    out = K.out_dir_from_argv("output")
    A = make_atlas()
    meshes = build(A)
    K.export_asset(NAME, LEVEL, meshes, A, out, lod2_tex=512, notes=dict(dims="example - estimated", lot="auto"))
