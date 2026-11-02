# -*- coding: utf-8 -*-
"""
example_building_cs2.py - cs2kit example (small 8-floor slab apartment). Copy this file to start a new generator.

Run:     python tools/cycle.py example_building_cs2.py          (build + check + preview)
         python tools/run_blender.py example_building_cs2.py -- --out output   (FBX if Blender found, else OBJ)
         python example_building_cs2.py --out output                           (no Blender: OBJ + textures only)
Check:   python tools/check.py output/<asset folder>
Preview: python tools/render.py output/<asset folder> -o previews/example.png

Layout: (1) dimension constants (2) atlas = material cells (3) geometry build() -> MeshBuilders (4) export_asset()
Comments must stay ASCII/English (Windows shells may break Korean text).
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

# (1) Dimensions in m. Values not given in the task: write the reason in a comment
NAME = "ResidentialHighKExample01"
LEVEL = 1
W = 22.0            # width (2 units x 11 m)
D = 11.0            # depth
FLOORS = 8
FH = 2.9            # floor height
BASE_H = 3.6        # ground floor (tall, no piloti)
PARAPET = 1.2
WIN_W, WIN_H, SILL = 1.8, 1.5, 0.9
BAL_D = 1.2         # balcony slab projection


# (2) Atlas: bigger px for big faces and materials seen up close
def stone_painter(c):
    c.joints(cols=3, rows=5, width_m=0.012, stagger=0.0, darken=0.35, tone=6)
    c.grain(amp=5)
    c.stains(amount=0.06, scale_px=48, streaks=0.4)


def wall_painter(c):
    c.grain(amp=3, height=0.1)
    c.stains(amount=0.05, scale_px=96, streaks=0.6)


def make_atlas(size=2048):
    A = K.Atlas(size=size, pad=8)
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures_src", "stone_albedo.png")
    if os.path.exists(src):   # use the photo material if it exists (extract_texture.py)
        A.add("stone", ctrl=(0, 0, 255), gloss=0.35, px=768, tile=(3.0, 2.9), image=src,
              normal_image=src.replace("_albedo", "_normal"), gloss_image=src.replace("_albedo", "_gloss"))
    else:
        A.add("stone", color=(122, 116, 110), ctrl=(0, 0, 255), gloss=0.35, px=768, tile=(3.0, 2.9), painter=stone_painter)
    A.add("wall", color=(236, 234, 228), ctrl=(0, 255, 0), gloss=0.2, px=512, tile=(4.0, 4.0), painter=wall_painter)
    A.add("accent", color=(62, 66, 72), ctrl=(255, 0, 0), gloss=0.3, px=64)
    A.add("slab", color=(210, 210, 206), gloss=0.2, px=64)
    A.add("frame", color=(70, 74, 80), metal=0.8, gloss=0.6, px=32)
    A.add("roof", color=(128, 134, 138), gloss=0.1, px=256, tile=(4.0, 4.0), painter=lambda c: c.grain(amp=8))
    A.add("door", color=(40, 42, 46), metal=0.6, gloss=0.5, px=64)
    A.add("led", color=(250, 246, 236), emissive=(255, 236, 200), px=32)
    return A


# (3) Geometry
def build(A):
    main, lod1 = K.MeshBuilder(A), K.MeshBuilder(A)
    lod2 = K.MeshBuilder(A, split_tiles=False)   # LOD2: one quad per face (<= 500 tris)
    gls, lod1_gls = K.MeshBuilder(A), K.MeshBuilder(A)
    wins = K.WindowSet()
    x0, x1, y0, y1 = -W / 2, W / 2, 0.0, D
    top = BASE_H + FLOORS * FH
    # body: stone ground floor + walls above (no bottom faces)
    for mb in (main, lod1):
        mb.box(x0, x1, y0, y1, 0, BASE_H, "stone", skip=("bottom", "top"))
        mb.box(x0, x1, y0, y1, BASE_H, top, dict(default="wall", top="roof"), skip=("bottom",))
    lod2.box(x0, x1, y0, y1, 0, top + PARAPET, dict(default="wall", top="roof"), skip=("bottom",))
    # parapet (0.25 thick) - no bottom face so it does not overlap the roof face
    t = 0.25
    for mb in (main, lod1):
        mb.box(x0, x1, y0, y0 + t, top, top + PARAPET, "wall", skip=("bottom",))
        mb.box(x0, x1, y1 - t, y1, top, top + PARAPET, "wall", skip=("bottom",))
        mb.box(x0, x0 + t, y0 + t, y1 - t, top, top + PARAPET, "wall", skip=("bottom", "front", "back"))
        mb.box(x1 - t, x1, y0 + t, y1 - t, top, top + PARAPET, "wall", skip=("bottom", "front", "back"))
    # accent bands at both front ends (paint) + LED strip (paint on paint -> layer 2)
    for a0, a1 in ((x0, x0 + 1.4), (x1 - 1.4, x1)):
        for mb in (main, lod1, lod2):
            K.paint(mb, "y", y0, -1, a0, a1, BASE_H, top + PARAPET, "accent")
        K.paint(main, "y", y0, -1, a0 + 0.6, a0 + 0.8, BASE_H, top + PARAPET, "led", layer=2)
    # per floor: balcony slab + windows (front), windows (back)
    bays = [(-9.5, -9.5 + WIN_W * 2), (-4.0, -4.0 + WIN_W), (1.5, 1.5 + WIN_W * 2), (7.0, 7.0 + WIN_W)]
    for f in range(FLOORS):
        zf = BASE_H + f * FH
        K.axbox(main, "y", y0, -1, x0 + 1.5, x1 - 1.5, 0, BAL_D, zf - 0.2, zf, "slab")        # o0=0 -> wall-side face removed automatically
        K.axbox(lod1, "y", y0, -1, x0 + 1.5, x1 - 1.5, 0, BAL_D, zf - 0.2, zf, "slab")
        # glass railing (_Gls, no material)
        gls.rect(K.face_pts("y", y0 - BAL_D + 0.05, -1, x0 + 1.5, x1 - 1.5, zf, zf + 1.1), "slab")
        lod1_gls.rect(K.face_pts("y", y0 - BAL_D + 0.05, -1, x0 + 1.5, x1 - 1.5, zf, zf + 1.1), "slab")
        for i, (a0, a1) in enumerate(bays):
            unit = 0 if a1 <= 0 else 1
            # window frame (real mesh). Side posts sit between top/bottom rails -> no overlapping faces
            m = 0.07
            K.axbox(main, "y", y0, -1, a0 - m, a1 + m, 0, 0.08, zf + SILL - m, zf + SILL, "frame")
            K.axbox(main, "y", y0, -1, a0 - m, a1 + m, 0, 0.08, zf + SILL + WIN_H, zf + SILL + WIN_H + m, "frame")
            for s0 in (a0 - m, a1):
                K.axbox(main, "y", y0, -1, s0, s0 + m, 0, 0.08, zf + SILL, zf + SILL + WIN_H, "frame")
            wins.add_face("y", y0, -1, a0, a1, zf + SILL, zf + SILL + WIN_H, floor=f, unit=unit)
            # back window (same x)
            wins.add_face("y", y1, 1, a0, a1, zf + SILL, zf + SILL + WIN_H, floor=f, unit=unit)
    # ground floor door (paint) + canopy
    K.paint(main, "y", y0, -1, -1.0, 1.0, 0.0, 2.4, "door")
    K.paint(lod1, "y", y0, -1, -1.0, 1.0, 0.0, 2.4, "door")
    K.axbox(main, "y", y0, -1, -1.6, 1.6, 0, 1.5, 2.8, 3.0, "accent")
    return dict(main=main, lod1=lod1, lod2=lod2, gls=gls, lod1_gls=lod1_gls, windows=wins)


# (4) Export
if __name__ == "__main__":
    out = K.out_dir_from_argv("output")
    A = make_atlas()
    meshes = build(A)
    folder, summary = K.export_asset(NAME, LEVEL, meshes, A, out, lod2_tex=512,
                                     notes=dict(dims="example - estimated", lot="auto"))
