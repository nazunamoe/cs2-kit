# -*- coding: utf-8 -*-
"""
facade_engine.py - shared facade generator for slab / tower apartment blocks (heightfield walls + zone tables + LOD).

A building = ONE data module (<name>_data.py) + a 6-line launcher (<name>_cs2.py). The engine knows nothing about a
particular building; the data module returns a tower dict (see `tower()` below) and may add atlas materials:

    # <name>_cs2.py (launcher)
    import os, sys
    sys.path.insert(0, <kit root>); import facade_engine as E
    import <name>_data as D
    E.run(D.tower, atlas=D.atlas_extra)

Tower dict keys (see projects/*/..._data.py for full examples):
    name, dong, gf (2F floor z), fh (floor pitch), floors, base_floors,
    blocks   [(x0, x1, y0, y1, roof_slab_z)]   plan rectangles, parapet is added PARAPET above the slab
    zones    [Z(side F/B/L/R, c=(c0, c1) wall plane range, a=(a0, a1) along the wall, "W", mat=, f=(first, last floor),
               wa=[(a0, a1, (sill, head[, "louver"]) | kind)], wf=[white frame rects], paints=[...], z=(z0, z1), wsets=[...])]
    parts    [dict(blocks=, zones=, canopies=, solids=, rot=deg, move=(dx, dy))]  rotated sub-bodies (own plan frame)
    kinds    window kind table, base_stone (podium stone material), canopies / solids (extra boxes), roofbox
Globals the data module may set before building: facade_engine.PARAPET, BASE_TONE[dong], ROOF_RAILS[dong], RAIL_DIM[dong].
Zone rules learned the hard way: paints over a window block it (WIN_BLOCKED) - use the zone `mat` as the base and put the
light frames on top (`wf`); window sill >= 0.12 above the zone floor; windows closer than 5 cm to a wall piece end vanish.
"""
import math
import os
import sys

# Windows dropped because they are within 0.05 m of a wall-piece end. cs2kit.export_asset
# copies this into manifest metadata so check.py can report the loss instead of it being silent.
DROPPED_WINDOWS = []
_DROPPED_KEYS = set()


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

SHOW_DONG = os.environ.get("SHOW_DONG", "0") == "1"   # False: no dong numbers (wall text + lattice number plates); SHOW_DONG=1 brings them back
LEVEL = 1
PARAPET = 1.6       # parapet height above the roof slab; building data may set facade_engine.PARAPET
PT = 0.3            # parapet thickness
WIN_IN = 0.20       # window glass set back from the wall face (reveal depth); the light line under a window in the photos is this reveal, NOT a sill bar
CREAM_BAND = False  # the scan's cream parapet band is a steel railing -> ROOF_RAILS / build_roof_rails
MIRROR_Y = False    # facade_engine.MIRROR_Y = True mirrors the finished tower front<->back (source data may be mirrored)
SASH = False        # building data may set facade_engine.SASH = True: 1.0-1.8 m windows become 2-sash sliders
CW_IN = 0.12      # glass set back in curtain-wall-look (black) zones

# ---------------------------------------------------------------- (1) towers
# blocks: (x0, x1, y0, y1, roof_slab_z)  - scan plan rectangles (glb strips at z>60 m)
# zones:  (side, c_min, c_max, a0, a1, type, z0, z1)  side F/B/L/R, c = wall plane coordinate range,
#         a = range along the wall, z range (None = whole height). Later rows win. Default type "W".
TOWERS = {}
ATLAS_HOOK = None   # fn(A) set by the building data: adds its own atlas materials



GF, FH = 4.2, 2.9                                  # same storey heights as 101 (estimated)


def Z(s, c, a, t, **kw):
    return dict(s=s, c=c, a=a, t=t, **kw)


def slab_of(top):
    """scan parapet top -> roof slab on a whole floor"""
    return GF + round((top - PARAPET - GF) / FH) * FH


def flip180(b, ymax):
    """rotate a scan rectangle 180 deg about the plan centre (so the long bar is the front)"""
    x0, x1, y0, y1 = b[:4]
    return (-x1, -x0, ymax - y1, ymax - y0) + tuple(b[4:])


def mk(dong, blocks, zones, base, flip=None, **kw):
    """tower config from scan blocks (x0, x1, y0, y1, scan_top). flip = ymax -> 180 deg turn"""
    if flip is not None:
        blocks = [flip180(b, flip) for b in blocks]
        for k in ("canopies", "roofbox", "crowns"):
            kw[k] = [flip180(b, flip) for b in kw.get(k, [])]
    bl = [(b[0], b[1], b[2], b[3], slab_of(b[4]) if b[4] > 20 else b[4]) for b in blocks]
    tops = [b[4] for b in bl] + [b[4] for p in kw.get("parts", []) for b in p["blocks"]]
    n = 1 + max(round((t - GF) / FH) for t in tops)
    kw["crowns"] = [(c[0], c[1], c[2], c[3], slab_of(c[4]) + PARAPET, c[5]) for c in kw.get("crowns", [])]
    return dict(name="ResidentialHighKCoastTower" + dong, dong=dong, gf=GF, fh=FH, floors=n, base_floors=base,
                blocks=bl, zones=zones, auto=True, **kw)




# ---- towers of this complex: see the _tNNN() functions below (added per tower)
# Frames (scripts/frame.py): scan mesh turned by -yaw, x centred, y = 0 at the front (min y), z = scan z - mesh minimum.
# Floors from the VR viewer (photos/data.xrx.json floor.range): 1F at +1.14, pitch 2.83 -> gf = 2F floor, fh = 2.83.




# ---- slab tower facade helpers. Paint layers: brown strips 1, white bands 2, white piers 3 (flat, nothing stands out).
FH_ = 2.83


def piers_(lst, f, p=1):
    return dict(r=[(a, b, 0.0, FH_) for a, b in lst], f=f, p=p, out=3)


def bands_(lst, f):
    return dict(r=[(a, b, -0.3, 0.0) for a, b in lst], f=f, p=3, out=2)


def brown_(lst, f, mat="bstrip"):
    return [(a, b, 0.0, FH_, dict(mat=mat, f=f)) for a, b in lst]


def dots_(a0, a1, f, dz=2.25):
    """three small light marks on the wide back units (105_side9, photo 15)"""
    c = (a0 + a1) / 2
    return [(c + d - 0.06, c + d + 0.06, dz, dz + 0.12, dict(mat="lgstrip", f=f, layer=2)) for d in (-0.45, 0.0, 0.45)]


def panes_(a0, a1, w=1.4, gap=0.12):
    """lobby glazing: panes <= 1.8 m with mullion gaps"""
    n = max(1, round((a1 - a0) / w))
    step = (a1 - a0) / n
    return [(a0 + i * step + gap / 2, a0 + (i + 1) * step - gap / 2) for i in range(n)]


LOUV = (0.25, 2.55, "louver")


LOBBY_KINDS = dict(DE=(0.08, 2.96), DL1=(0.16, 2.96), DLU=(3.26, 5.46), DLS=(0.16, 5.46))


def lobby_(x0, x1, y0, yb, top, dc):
    """glass entrance lobby behind a core (photo of the 105 lobby): outer face = a door in a dark portal at
    the centre (dc), glass panes beside it below and one glass row above, a thick dark fascia along the top; the two
    side faces glazed. Returns (zones, canopies, solids). DL* / DE kinds start with D: kept under the fascia"""
    zones = [
        Z("B", (yb - 0.1, yb + 0.1), (x0, x1), "W", mat="dline", nobase=True, z=(0.0, top + 0.1), f=(1, 1),
          wa=[(dc - 1.45, dc + 1.45, "DE")] + [(a, b, "DL1") for a, b in panes_(x0 + 0.25, dc - 1.85)]
             + [(a, b, "DL1") for a, b in panes_(dc + 1.85, x1 - 0.25)] + [(a, b, "DLU") for a, b in panes_(x0 + 0.25, x1 - 0.25)]),
        Z("L", (x0 - 0.1, x0 + 0.1), (y0, yb), "W", mat="dline", nobase=True, z=(0.0, top + 0.1), f=(1, 1),
          wa=[(a, b, "DLS") for a, b in panes_(y0 + 0.2, yb - 0.25)]),
        Z("R", (x1 - 0.1, x1 + 0.1), (y0, yb), "W", mat="dline", nobase=True, z=(0.0, top + 0.1), f=(1, 1),
          wa=[(a, b, "DLS") for a, b in panes_(y0 + 0.2, yb - 0.25)]),
    ]
    canopies = [(x0 - 0.05, x1 + 0.05, yb, yb + 0.45, top - 0.75, top + 0.05),       # dark fascia
                (dc - 1.75, dc + 1.75, yb, yb + 0.3, 4.25, 4.55)]                     # portal head
    solids = [(dc - 1.75, dc - 1.5, yb, yb + 0.3, 0.0, 4.25, "canopy"), (dc + 1.5, dc + 1.75, yb, yb + 0.3, 0.0, 4.25, "canopy")]
    return zones, canopies, solids






# podium (base floors) stone per wall piece: (side, wall c, a0, a1, material). Read on the textured scan elevations
# between window rows of floors 2-4 and sorted into dark polished / dark grey / light grey granite (photos
# low_detail*.png: the podium is NOT one stone - neighbouring wall blocks use different granite)
BASE_TONE = {}


def base_mat(T, w, am):
    for s_, c, a0, a1, m in BASE_TONE.get(T.get("dong"), []):
        if s_ == side_of(w) and abs(c - w["c"]) < 0.08 and a0 - 0.05 <= am <= a1 + 0.05:
            return m
    return T.get("base_stone", "stone")          # this complex: one podium stone per tower (scan elevation)


# ---------------------------------------------------------------- (2) atlas


def wall_painter(c):
    c.grain(amp=3, height=0.1)
    c.stains(amount=0.04, scale_px=96, streaks=0.5)


def stone_painter(c):
    c.joints(cols=2, rows=2, width_m=0.008, stagger=0.0, darken=0.3)
    c.grain(amp=4)


def vstripe_painter(c):
    """grey wall panels: VERTICAL stripes (all vertical-striped panels are one colour)"""
    c.joints(cols=18, rows=1, width_m=0.015, stagger=0.0, darken=0.25)
    c.grain(amp=2)


def stripe_painter(c):
    """grey wall panels of this complex: horizontal stripes every ~0.22 m (window_down.png: 5 stripes per 1.1 m panel)"""
    c.joints(cols=1, rows=18, width_m=0.015, stagger=0.0, darken=0.25)
    c.grain(amp=2)


def wstripe_painter(c):
    """white end walls of this complex: fine horizontal panel joints (~0.3 m, real photo of 106)"""
    c.joints(cols=1, rows=13, width_m=0.01, stagger=0.0, darken=0.12)
    c.grain(amp=2)


def picket_painter(c):
    """steel railing pickets: 2 cm bars every 0.11 m (10 per 1.1 m tile), alpha 0 between them (alpha cut)"""
    import numpy as np
    u = (c.u * 10.0) % 1.0
    c.alpha[:] = np.where(np.abs(u - 0.5) < 0.09, 255, 0).astype(c.alpha.dtype)


def panel_painter(c):
    """metal wall panels behind the 104 screen: 1.2 m wide, one storey high, thin dark joints"""
    c.joints(cols=1, rows=1, width_m=0.012, stagger=0.0, darken=0.35)
    c.grain(amp=3)


def stone_painter_dk(c):
    c.joints(cols=2, rows=2, width_m=0.006, stagger=0.0, darken=0.35)
    c.grain(amp=3)


def stone_painter_lt(c):
    c.joints(cols=2, rows=2, width_m=0.01, stagger=0.0, darken=0.32)     # podium granite grid 0.9 x 0.6 (window_down.png)
    c.grain(amp=4)          # keep low: 12 reads as white dots from a distance


def make_atlas(size=4096):
    A = K.Atlas(size=size, pad=8)
    # colours = photo medians (wall, CW, base, taupe panels)
    A.add("white", color=(190, 196, 199), gloss=0.25, px=512, tile=(4.0, 4.0), painter=wall_painter)   # #c4c5cd
    # curtain-wall-look glass panels: smooth (no grain / no normal noise), high gloss, slightly metallic   #151720
    # tone pulled toward the in-game window (_Win) colour (kit preview #54738f) so the openings merge into one glass
    # skin; photo panel colour #151720
    A.add("black", color=(58, 78, 100), metal=0.6, gloss=0.95, px=64)           # #3a4e64
    A.add("taupe", color=(93, 90, 94), metal=0.2, gloss=0.4, px=256, tile=(4.0, 4.0), painter=wall_painter)   # #5d5a5e (lit core)
    A.add("stone", color=(74, 75, 78), gloss=0.45, px=512, tile=(1.2, 0.9), painter=stone_painter)   # #4a4b4e (front base)
    # podium granites (low_detail*.png, scan medians lifted to daylight): 0.9 x 0.6 m panels
    A.add("stone_dk", color=(52, 55, 62), gloss=0.65, px=512, tile=(1.8, 1.2), painter=stone_painter_dk)   # polished blue-black
    A.add("stone_md", color=(78, 79, 85), gloss=0.45, px=512, tile=(1.8, 1.2), painter=stone_painter)      # dark grey granite
    A.add("stone_lt", color=(104, 104, 108), gloss=0.35, px=512, tile=(1.8, 1.2), painter=stone_painter_lt)  # speckled grey
    A.add("cornice", color=(48, 50, 55), metal=0.3, gloss=0.5, px=64)          # stepped podium cornice
    A.add("panel104", color=(138, 141, 148), metal=0.2, gloss=0.35, px=256, tile=(1.2, 2.866), painter=panel_painter)
    A.add("screen", color=(204, 205, 210), gloss=0.2, px=128, tile=(3.6, 4.0), painter=make_screen_painter)
    A.add("lattice", color=(214, 215, 218), gloss=0.25, px=128, tile=(3.0, 5.8), painter=make_lattice_painter)
    A.add("sill", color=(236, 236, 234), gloss=0.3, px=32)
    # measured median over floors 12-34
    A.add("gray4", color=(120, 126, 133), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)    # #787e85 front bands
    A.add("lgray4", color=(147, 152, 159), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)   # #93989f east part
    A.add("gray4d", color=(97, 102, 107), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)    # #61666b recess / C1
    A.add("gray102", color=(112, 114, 119), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)   # #6c6e73 (grey bands)
    A.add("cream", color=(215, 207, 183), gloss=0.2, px=128, tile=(4.0, 4.0), painter=wall_painter)   # #d7cfb7 parapet band
    for dn, col in (("101", (62, 62, 68)), ("102", (70, 72, 78)), ("104", (60, 61, 66)), ("107", (64, 64, 70)), ("108", (62, 63, 68))):   # stair stripe paint (scan, between windows)
        A.add("stripe" + dn, color=col, gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)
    A.add("reliefdk", color=(52, 54, 62), metal=0.3, gloss=0.5, px=256, tile=(3.6, 4.0), painter=make_relief_painter)   # dark triangle relief
    A.add("platetop", color=(162, 161, 158), gloss=0.2, px=64, tile=(1.0, 1.0),
          painter=lambda c: (c.joints(1, 1, width_m=0.04, darken=0.35), c.grain(amp=3)))   # crown plate tops: light grey, 1 m joints
    A.add("pergtop", color=(60, 54, 51), metal=0.3, gloss=0.4, px=128, tile=(1.6, 1.6), painter=make_pergtop_painter)   # black frame top grid
    A.add("mint106", color=(222, 234, 227), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)   # #d4e3db (west strip)
    A.add("stripe105", color=(70, 69, 74), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)   # #46454a (front stair stripe)
    for nm, hh in (("rel105a", 1.428), ("rel105b", 2.856), ("rel105c", 5.712)):   # west black relief, diamonds 1.24 m wide
        A.add(nm, color=(56, 54, 62), metal=0.3, gloss=0.5, px=128, tile=(2.475, hh), painter=make_diamond_painter(2, 1))
    A.add("sfgrid", color=(24, 26, 30), metal=0.4, gloss=0.4, px=128, tile=(3.6, 4.0), painter=make_sfgrid_painter)   # roof plate underside
    A.add("brownfr", color=(66, 58, 54), metal=0.3, gloss=0.4, px=128, tile=(4.0, 4.0), painter=wall_painter)   # brown-charcoal frame round the black CW
    A.add("rel106", color=(52, 54, 62), metal=0.3, gloss=0.5, px=128, tile=(4.0, 4.0), painter=wall_painter)   # west relief panel base
    A.add("rib106", color=(78, 80, 90), metal=0.4, gloss=0.55, px=32)          # its raised creases / joints (lit edges)
    A.add("stripe108d", color=(44, 46, 52), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)   # east core stair stripe (0.75 x core)
    A.add("pave107", color=(56, 56, 60), gloss=0.3, px=128, tile=(1.2, 1.2), painter=stone_painter_dk)   # back terrace deck (dark)
    A.add("char105", color=(40, 42, 48), gloss=0.35, px=256, tile=(4.0, 4.0), painter=wall_painter)   # #23252a (front-left podium, lifted)
    A.add("char", color=(58, 60, 63), metal=0.2, gloss=0.4, px=128, tile=(4.0, 4.0), painter=wall_painter)  # #3a3c3f cores
    A.add("fin", color=(214, 215, 222), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)
    # grey panels behind the white frames, light sill panels, dark slits / stair strip
    # horizontal stripe pattern (~0.22 m pitch, estimated)
    # grey panels = 0.55 x the white frames, neutral grey (shade photo 0.51 bluish; sunny photo 0.69 clips white)
    # VR photos: frames #b1bac2, panels #52616b (0.5 x frames), podium #4f5562, stair strip #404f68
    A.add("dpanel", color=(100, 110, 120), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)  # #646e78, plain (no stripes)
    A.add("dpanelh", color=(100, 110, 120), gloss=0.3, px=256, tile=(4.0, 4.0), painter=stripe_painter)  # back: same colour, horizontal stripes (photo)
    # (dsill below: the only HORIZONTAL-striped panels, lighter, under the small windows)
    A.add("dsill", color=(120, 132, 144), gloss=0.3, px=256, tile=(4.0, 4.0), painter=stripe_painter)    # under the small windows: 1.2 x panel
    A.add("cstripe", color=(200, 205, 211), gloss=0.25, px=256, tile=(4.0, 4.0), painter=wstripe_painter)  # cores: grey, horizontal grooves (photo)
    A.add("wstripe", color=(196, 200, 206), gloss=0.25, px=256, tile=(4.0, 4.0), painter=wstripe_painter)  # end walls: white, fine horizontal joints
    A.add("stone106", color=(112, 116, 126), gloss=0.35, px=512, tile=(1.8, 1.2), painter=stone_painter_lt)  # podium: VR #4f5562 x 1.17
    A.add("dslit", color=(72, 84, 105), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)      # VR #404f68 stair strips
    # brown vertical strips + roof boxes, brown striped east end walls, dark west faces of the west cores
    A.add("bstrip", color=(155, 140, 126), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)
    A.add("bend", color=(170, 153, 143), gloss=0.3, px=256, tile=(4.0, 4.0), painter=stripe_painter)
    A.add("cside", color=(110, 120, 135), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wstripe_painter)
    A.add("lgstrip", color=(160, 168, 176), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)  # light grey strip in the back grid
    A.add("dline", color=(42, 54, 64), gloss=0.3, px=128, tile=(4.0, 4.0), painter=wall_painter)       # #1d2830: lines beside the cores
    A.add("rail", color=(196, 198, 200), metal=0.7, gloss=0.6, px=32)
    A.add("srailbar", color=(58, 62, 68), metal=0.6, gloss=0.4, px=32)          # dark steel railing (photo)
    A.add("srail", color=(58, 62, 68), metal=0.6, gloss=0.4, px=128, tile=(1.1, 1.0), painter=picket_painter)
    A.add("roof", color=(150, 148, 142), gloss=0.1, px=256, tile=(4.0, 4.0), painter=lambda c: c.grain(amp=8))
    A.add("coping", color=(200, 200, 198), gloss=0.2, px=64)
    A.add("frame", color=(60, 64, 70), metal=0.8, gloss=0.6, px=32)
    A.add("truss", color=(66, 54, 48), metal=0.6, gloss=0.5, px=32)           # dark rust-brown steel
    A.add("colgrey", color=(150, 152, 156), metal=0.3, gloss=0.4, px=64)       # grey roof column
    A.add("cwjoint", color=(74, 92, 112), metal=0.6, gloss=0.7, px=32)       # light metal panel joints
    A.add("spandrel", color=(52, 70, 90), metal=0.6, gloss=0.95, px=64)        # #34465a lounge spandrel, same glass tone
    A.add("louver", color=(150, 154, 156), metal=0.6, gloss=0.4, px=64)
    A.add("roofw", color=(236, 234, 228), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)
    A.add("sign", color=(240, 238, 230), emissive=(255, 244, 220), px=64)
    A.add("signw", color=(150, 152, 156), metal=0.5, gloss=0.4, px=32)        # raised metal digits, not lit
    A.add("signd", color=(112, 114, 120), metal=0.3, gloss=0.4, px=32)          # dark digits on white walls
    A.add("canopy", color=(46, 48, 52), metal=0.6, gloss=0.5, px=32)
    if ATLAS_HOOK:
        ATLAS_HOOK(A)                                   # building data adds / overrides materials
    return A


# ---------------------------------------------------------------- (3) heightfield mass

def heightfield(blocks):
    """compressed grid of all block edges -> cell heights (max roof of covering blocks)"""
    xs = sorted(set(round(v, 3) for b in blocks for v in (b[0], b[1])))
    ys = sorted(set(round(v, 3) for b in blocks for v in (b[2], b[3])))
    H = []
    for j in range(len(ys) - 1):
        cy = (ys[j] + ys[j + 1]) / 2
        row = []
        for i in range(len(xs) - 1):
            cx = (xs[i] + xs[i + 1]) / 2
            row.append(max([b[4] for b in blocks if b[0] <= cx <= b[1] and b[2] <= cy <= b[3]] or [0.0]))
        H.append(row)
    return xs, ys, H


def walls_of(xs, ys, H):
    """outer wall pieces: dict(axis, c, s, a0, a1, z0, z1), merged along each grid line"""
    nx, ny = len(xs) - 1, len(ys) - 1
    hget = lambda i, j: H[j][i] if 0 <= i < nx and 0 <= j < ny else 0.0
    out = []
    for i in range(nx + 1):                         # lines x = xs[i]
        run = None
        for j in range(ny + 1):
            seg = None
            if j < ny:
                hl, hr = hget(i - 1, j), hget(i, j)
                if hr > hl + 1e-6:
                    seg = (-1, hl, hr)
                elif hl > hr + 1e-6:
                    seg = (1, hr, hl)
            if run and seg == run[0]:
                run[2] = ys[j + 1]
                continue
            if run:
                out.append(dict(axis="x", c=xs[i], s=run[0][0], a0=run[1], a1=run[2], z0=run[0][1], z1=run[0][2]))
            run = [seg, ys[j], ys[j + 1] if j < ny else None] if seg else None
    for j in range(ny + 1):                         # lines y = ys[j]
        run = None
        for i in range(nx + 1):
            seg = None
            if i < nx:
                hd, hu = hget(i, j - 1), hget(i, j)
                if hu > hd + 1e-6:
                    seg = (-1, hd, hu)
                elif hd > hu + 1e-6:
                    seg = (1, hu, hd)
            if run and seg == run[0]:
                run[2] = xs[i + 1]
                continue
            if run:
                out.append(dict(axis="y", c=ys[j], s=run[0][0], a0=run[1], a1=run[2], z0=run[0][1], z1=run[0][2]))
            run = [seg, xs[i], xs[i + 1] if i < nx else None] if seg else None
    return out


def roofs_of(xs, ys, H):
    """roof caps merged into rectangles: (x0, x1, y0, y1, z)"""
    rects = []
    for j in range(len(ys) - 1):
        i = 0
        while i < len(xs) - 1:
            h = H[j][i]
            k = i
            while k + 1 < len(xs) - 1 and abs(H[j][k + 1] - h) < 1e-6:
                k += 1
            if h > 0:
                rects.append([xs[i], xs[k + 1], ys[j], ys[j + 1], h])
            i = k + 1
    merged = []
    for r in rects:                                 # vertical merge of identical runs
        for m in merged:
            if abs(m[0] - r[0]) < 1e-6 and abs(m[1] - r[1]) < 1e-6 and abs(m[3] - r[2]) < 1e-6 and abs(m[4] - r[4]) < 1e-6:
                m[3] = r[3]
                break
        else:
            merged.append(list(r))
    return merged


# ---- roof railings (the "cream parapet band" of the scan is a steel railing, like the back terrace one).
# Every outer wall piece that ends at a roof + PARAPET was sampled on the textured scan (scripts/rail_edges.py -> rail_survey.py
# -> rail_decide.py -> rail_table.py): railing where the band roof +0.5..+1.4 is yellowish ((r+g)/2-b >= 7, light), white
# solid parapets read <= 5. (part, axis, c, s, a0, a1, roof slab) per tower.
ROOF_RAILS = {}   # (part, axis, c, s, a0, a1, slab) railing runs per dong (filled per tower)
# (upstand above the roof slab, railing height). Upstand = median band bottom of the scan profiles per tower (absorbs the
# per-tower roof slab error); the railing is the same product on every tower: height = mean of the 8 measured band
# heights (1.2, 1.1, 0.8, 1.2, 1.1, 0.9, 1.0, 0.95 -> 1.03) -> 1.05
RAIL_H = 1.05
RAIL_F = 0.012    # rail end past an inner polyline corner; 0.03 keeps the rail end face >1 cm off the corner post face (no COPLANAR)
RAIL_DIM = {}     # dong -> (upstand, railing height)


def with_parapets(blocks, rails=(), up=0.4, out=None, keep=()):
    """add a PT-thick parapet strip (top + PARAPET) inside every roof edge -> no overlapping corner boxes.
    Along the railing runs (ROOF_RAILS) the strip is only an upstand (top + up) and the run goes to out (railing segments);
    short full pieces (< 0.7 m) left between lowered ones (steps of the outline) are lowered too. keep = (x0, x1, y0, y1)
    footprints (crown posts) that stand on the parapet: the full parapet stays under them"""
    xs, ys, H = heightfield(blocks)
    segs = []                                         # (w, a0, a1, low)
    for w in walls_of(xs, ys, H):
        if w["z1"] < 15.0:
            continue                                  # low porch / annex roofs: no parapet pit (avoids protruding faces at the base)
        cuts = sorted((r[4], r[5]) for r in rails if r[1] == w["axis"] and abs(r[2] - w["c"]) < 1e-3 and r[3] == w["s"]
                      and abs(r[6] - w["z1"]) < 1e-3)
        for x0, x1, y0, y1 in keep:                   # a run ending exactly on a post face: 2 cm into the post (no shared face)
            b0, b1, n0, n1 = (x0, x1, y0, y1) if w["axis"] == "y" else (y0, y1, x0, x1)
            if n1 > w["c"] - PT - 1e-3 and n0 < w["c"] + PT + 1e-3:
                cuts = [(q0 - 0.02 if abs(q0 - b1) < 1e-3 else q0, q1 + 0.02 if abs(q1 - b0) < 1e-3 else q1) for q0, q1 in cuts]
        cur, ps = w["a0"], []
        for q0, q1 in cuts:
            q0, q1 = max(q0, w["a0"]), min(q1, w["a1"])
            if q1 - q0 < 1e-3:
                continue
            if q0 - cur > 1e-3:
                ps.append([w, cur, q0, False])
            ps.append([w, q0, q1, True])
            cur = q1
        if w["a1"] - cur > 1e-3:
            ps.append([w, cur, w["a1"], False])
        for i, p in enumerate(ps):                    # a short full piece between two lowered ones on the same edge
            if not p[3] and p[2] - p[1] < 0.7 and 0 < i < len(ps) - 1 and ps[i - 1][3] and ps[i + 1][3]:
                p[3] = True
        segs += ps
    def ends(p):
        w = p[0]
        return [(p[1], w["c"], w["z1"]), (p[2], w["c"], w["z1"])] if w["axis"] == "y" else [(w["c"], p[1], w["z1"]), (w["c"], p[2], w["z1"])]
    low_ends = [e for p in segs if p[3] for e in ends(p)]
    near = lambda e: any(abs(e[0] - f[0]) < 0.05 and abs(e[1] - f[1]) < 0.05 and abs(e[2] - f[2]) < 1e-3 for f in low_ends)
    for p in segs:                                    # short step pieces of the outline touching a lowered run: lowered too,
        if not p[3] and p[2] - p[1] < 0.7 and any(near(e) for e in ends(p)):   # else their corner square splits the wall
            p[3] = True                                                         # below and drops the windows across it
    extra = []
    for w, a0, a1, low in segs:
        top = w["z1"] + (up if low else PARAPET)
        if w["axis"] == "x":
            x0, x1 = (w["c"], w["c"] + PT) if w["s"] < 0 else (w["c"] - PT, w["c"])
            extra.append((x0, x1, a0, a1, top))
        else:
            y0, y1 = (w["c"], w["c"] + PT) if w["s"] < 0 else (w["c"] - PT, w["c"])
            extra.append((a0, a1, y0, y1, top))
        if low and out is not None:
            out.append(dict(axis=w["axis"], c=w["c"], s=w["s"], a0=a0, a1=a1, z0=top, rect=extra[-1][:4], slab=w["z1"]))
    return blocks + extra


def side_of(w):
    if w["axis"] == "y":
        return "F" if w["s"] < 0 else "B"
    return "L" if w["s"] < 0 else "R"


def split_zones(w, T):
    """split one wall into (a0, a1, z0, z1, type) pieces using the tower's zone table"""
    side = side_of(w)
    dflt = dict(t=T.get("default", "W"), a=(w["a0"], w["a1"]))
    if not T.get("auto", False):
        dflt["w"] = []
    pieces = [(w["a0"], w["a1"], w["z0"], w["z1"], dflt)]
    for typ in T["zones"]:
        zs, (c0, c1), (a0, a1) = typ["s"], typ["c"], typ["a"]
        z0, z1 = typ.get("z", (None, None))
        if zs != side or not (c0 - 1e-3 <= w["c"] <= c1 + 1e-3):
            continue
        zz0 = w["z0"] if z0 is None else max(z0, w["z0"])
        zz1 = w["z1"] if z1 is None else min(z1, w["z1"])
        nxt = []
        for p in pieces:
            b0, b1 = max(p[0], a0), min(p[1], a1)
            c_0, c_1 = max(p[2], zz0), min(p[3], zz1)
            if b1 - b0 < 1e-3 or c_1 - c_0 < 1e-3:
                nxt.append(p)
                continue
            for q in ((p[0], b0, p[2], p[3]), (b1, p[1], p[2], p[3]), (b0, b1, p[2], c_0), (b0, b1, c_1, p[3])):
                if q[1] - q[0] > 1e-3 and q[3] - q[2] > 1e-3:
                    nxt.append(q + (p[4],))
            nxt.append((b0, b1, c_0, c_1, typ))
        pieces = nxt
    return pieces


MAT = {"W": "white", "C": "black", "G": "taupe", "S": "stone", "T": "black", "B": "black", "X": "taupe", "P": "white"}
# window kinds: (sill, head) above the floor level. Heads line up (tops of big/small windows level)
KINDS = {"L": (0.75, 2.40), "S": (1.70, 2.40), "H": (1.85, 2.40), "F": (0.15, 2.45), "N": (0.75, 2.40)}


def floor_levels(T):
    """floor bottoms: 1F at 0 (lobby gf tall), 2F.. at gf + (k-2)*fh"""
    return [0.0] + [T["gf"] + k * T["fh"] for k in range(T["floors"] - 1)]


def wpt(w, a, o, z):
    """wall frame -> world point: a along the wall, o outward from the wall face"""
    if w["axis"] == "y":
        return (a, w["c"] + w["s"] * o, z)
    return (w["c"] + w["s"] * o, a, z)


def quad_n(mb, pts, n, region):
    """quad with its face normal turned to n (world vector)"""
    p0, p1, p2 = pts[0], pts[1], pts[2]
    u = [p1[i] - p0[i] for i in range(3)]
    v = [p2[i] - p0[i] for i in range(3)]
    c = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    if c[0] * n[0] + c[1] * n[1] + c[2] * n[2] < 0:
        pts = pts[::-1]
    mb.rect(list(pts), region)


def out_vec(w, sign=1.0):
    return (0.0, w["s"] * sign, 0.0) if w["axis"] == "y" else (w["s"] * sign, 0.0, 0.0)


def along_vec(w, sign=1.0):
    return (sign, 0.0, 0.0) if w["axis"] == "y" else (0.0, sign, 0.0)


# window groups measured from reference photos (31.6 px/m) - reused where a tower's own photos are too small
A_UNIT = [(0.6, 3.5, "L"), (4.4, 5.8, "L")]                                       # 6.0 m: living + room
B_UNIT = [(0.75, 1.95, "L"), (2.6, 3.15, "S"), (3.85, 4.45, "S"), (5.05, 6.3, "L"), (7.3, 8.7, "H")]  # 9.4 m
C_UNIT = [(0.15, 0.75, "L"), (1.6, 3.2, "L"), (4.0, 5.5, "L"), (6.3, 9.1, "L")]   # 9.3 m: openings in black CW
UNIT_W = {"A": 6.0, "B": 9.4, "C": 9.3}


def auto_windows(width, typ):
    """fill a wall width with measured window groups (estimated where the photo is not readable)"""
    if typ in ("G", "T", "X") or width < 1.8:
        return []
    if typ == "P":                                   # fin wall: 0.5 m slit between fins, 1.2 m pitch
        n = int((width - 0.2) / 1.2)
        pad = (width - 0.2 - n * 1.2) / 2
        return [(pad + k * 1.2 + 0.55, pad + k * 1.2 + 0.85, "N") for k in range(n)]
    if width < 4.4:
        ww = min(1.8, width - 1.2)
        return [((width - ww) / 2, (width + ww) / 2, "L")]
    seq = ["C"] if typ in ("C", "B") else ["A", "B"]
    groups, used, k = [], 0.0, 0
    while True:
        g = seq[k % len(seq)]
        if used + UNIT_W[g] > width + 0.01:
            break
        groups.append(g)
        used += UNIT_W[g]
        k += 1
    if not groups:
        return [(0.6, width - 0.6, "L")] if width > 3.0 else []
    pad = (width - used) / 2
    out, u = [], pad
    for g in groups:
        out += [(u + a, u + b, kd) for a, b, kd in {"A": A_UNIT, "B": B_UNIT, "C": C_UNIT}[g]]
        u += UNIT_W[g]
    return out


def blockers(T, w):
    """(a0, a1, z0, z1) rectangles on wall w that must stay free of windows: canopies within 1.5 m in
    front (kit rule WIN_BLOCKED) and dong-number signs on the wall"""
    out = []
    for cn_ in T.get("canopies", []):
        x0, x1, y0, y1, cz0, cz1 = cn_[:6]
        n0, n1, b0, b1 = (y0, y1, x0, x1) if w["axis"] == "y" else (x0, x1, y0, y1)
        f0, f1 = sorted((w["c"], w["c"] + w["s"] * 1.6))
        if n1 > f0 + 1e-3 and n0 < f1 - 1e-3:
            out.append((b0 - 0.2, b1 + 0.2, cz0 - 0.4, cz1 + 0.4))
    for F in T.get("frames", []):                   # entrance frames: no ordinary window behind them
        if F["axis"] == w["axis"] and F["s"] == w["s"] and abs(F["c"] - w["c"]) < 1.2:
            out.append((F["a0"] - 0.1, F["a1"] + 0.1, -1.0, F["z1"] + 0.3))
    for sg in T.get("signs", []):
        if sg.get("keep_windows"):                  # number sits between window rows: no window is removed
            continue
        if sg["s"] == side_of(w) and abs(sg["c"] - w["c"]) < 0.15:
            pad = sg.get("pad", 0.4)
            half = (len(T["dong"]) * GW + (len(T["dong"]) - 1) * 0.20) * sg["h"] / 2 + pad
            out.append((sg["a"] - half, sg["a"] + half, sg["z"] - 2 * pad, sg["z"] + sg["h"] + 2 * pad))
    return out


def zone_windows(zone, side, lv, z0, z1, a0, a1, T, w=None):
    """absolute holes (ha0, ha1, hz0, hz1, floor) of a zone inside one wall piece"""
    blk = blockers(T, w) if w is not None else []
    za0, za1 = zone["a"]
    if "w" not in zone and "wa" not in zone:         # no measured list -> fill this wall piece
        za0, za1 = a0, a1
        zone = dict(zone, a=(a0, a1), w=auto_windows(a1 - a0, zone["t"]))
    f0, f1 = zone.get("f", (2, T["floors"]))
    out = []
    kinds = T.get("kinds", KINDS)
    lst = [(za0 + u0, za0 + u1, kd) if side in ("F", "R") else (za1 - u1, za1 - u0, kd) for u0, u1, kd in zone.get("w", [])]
    lst += list(zone.get("wa", []))                  # absolute positions along the wall (measured on the scan elevation)
    sets = [(lst, f0, f1, 1)] + [(S["wa"], S["f"][0], S["f"][1], S.get("p", 1)) for S in zone.get("wsets", [])]
    for lst, f0, f1, step in sets:                   # wsets: window lists on every p-th floor (staggered facades)
        out += _zone_wins(zone, lst, f0, f1, step, lv, z0, z1, a0, a1, T, blk, kinds)
    return out


def _zone_wins(zone, lst, f0, f1, step, lv, z0, z1, a0, a1, T, blk, kinds):
    out = []
    for b0, b1, kind in lst:
        if b0 < a0 + 0.05 or b1 > a1 - 0.05:
            key = (zone.get("id") or zone.get("name") or "zone", round(b0, 3), round(b1, 3),
                   round(a0, 3), round(a1, 3))
            if key not in _DROPPED_KEYS and len(DROPPED_WINDOWS) < 200:
                _DROPPED_KEYS.add(key)
                DROPPED_WINDOWS.append({"zone": key[0], "window_m": [key[1], key[2]],
                                        "zone_m": [key[3], key[4]],
                                        "reason": "within 0.05 m of the wall-piece end"})
            continue
        s0, s1 = kind[:2] if isinstance(kind, tuple) else kinds[kind]   # tuple = measured (sill, head)
        for k in range(f0 - 1, min(f1, len(lv)), step):
            if k + 1 in zone.get("skipf", ()):         # floors without this opening (e.g. a stair window under the cornice)
                continue
            hz0, hz1 = lv[k] + s0, lv[k] + s1
            if k == 0:                         # lobby floor: same openings, raised to the 1F top
                hz0, hz1 = hz0 + T["gf"] - T["fh"], hz1 + T["gf"] - T["fh"]
            if not (isinstance(kind, str) and kind.startswith("D")) and any(b0 < q[1] and b1 > q[0] and hz0 < q[3] and hz1 > q[2] for q in blk):
                continue                               # doors belong inside entrance frames
            if hz0 >= z0 + 0.05 and hz1 <= z1 - 0.05:
                out.append((b0, b1, hz0, hz1, k, kind))
    return out


def punched(mb, w, a0, a1, z0, z1, holes, mat_at, breaks):
    """wall piece with rectangular holes: z sweep -> wall rects, merged vertically"""
    zs = sorted(set([z0, z1] + [h[2] for h in holes] + [h[3] for h in holes] + [b for b in breaks if z0 < b < z1]))
    openr = {}
    for zb0, zb1 in zip(zs[:-1], zs[1:]):
        zm = (zb0 + zb1) / 2
        act = sorted((h[0], h[1]) for h in holes if h[2] <= zm <= h[3])
        ivs, cur = [], a0
        for h0, h1 in act:
            if h0 > cur + 1e-4:
                ivs.append((cur, h0))
            cur = max(cur, h1)
        if a1 > cur + 1e-4:
            ivs.append((cur, a1))
        mat = mat_at(zm)
        nxt = {}
        for iv in ivs:
            key = (round(iv[0], 4), round(iv[1], 4), mat)
            nxt[key] = (openr.pop(key)[0] if key in openr else zb0, zb1)
        for (b0, b1, m), (c0, c1) in openr.items():
            mb.rect(K.face_pts(w["axis"], w["c"], w["s"], b0, b1, c0, c1), m)
        openr = nxt
    for (b0, b1, m), (c0, c1) in openr.items():
        mb.rect(K.face_pts(w["axis"], w["c"], w["s"], b0, b1, c0, c1), m)


def reveal(mb, w, h, region, depth=WIN_IN):
    """4 inner faces of a window hole (depth into the wall)"""
    b0, b1, c0, c1 = h[:4]
    o0, o1 = -depth, 0.0
    quad_n(mb, [wpt(w, b0, o0, c0), wpt(w, b0, o1, c0), wpt(w, b0, o1, c1), wpt(w, b0, o0, c1)], along_vec(w, 1), region)
    quad_n(mb, [wpt(w, b1, o0, c0), wpt(w, b1, o1, c0), wpt(w, b1, o1, c1), wpt(w, b1, o0, c1)], along_vec(w, -1), region)
    quad_n(mb, [wpt(w, b0, o0, c0), wpt(w, b1, o0, c0), wpt(w, b1, o1, c0), wpt(w, b0, o1, c0)], (0, 0, 1), region)
    quad_n(mb, [wpt(w, b0, o0, c1), wpt(w, b1, o0, c1), wpt(w, b1, o1, c1), wpt(w, b0, o1, c1)], (0, 0, -1), region)


def ledge(mb, w, b0, b1, z, out=0.06, h=0.07, region="sill"):
    """window sill drip: disabled - the white line under windows does not exist (it is the inset reveal in the photos)"""
    return
    quad_n(mb, [wpt(w, b0, 0, z), wpt(w, b1, 0, z), wpt(w, b1, out, z), wpt(w, b0, out, z)], (0, 0, 1), region)
    quad_n(mb, [wpt(w, b0, out, z - h), wpt(w, b1, out, z - h), wpt(w, b1, out, z), wpt(w, b0, out, z)], out_vec(w), region)


def glass(wins, w, b0, b1, c0, c1, floor, unit, depth):
    """window glass (_Win). Wider than 1.8 m -> split in 2 panes (facade-divided window) with a mullion gap"""
    c = w["c"] - w["s"] * depth
    ax, s = w["axis"], w["s"]

    def put(p0, p1):
        # main/LOD1: glass in the recess; LOD2 (flat box): in front of the wall face
        wins.add_pts(K.face_pts(ax, c + s * K.WIN_OFF, s, p0, p1, c0, c1),
                     K.face_pts(ax, w["c"] + s * K.LOD2_WIN_OFF, s, p0, p1, c0, c1), p1 - p0, c1 - c0, floor, unit)
    if SASH and 0.95 <= b1 - b0 <= 1.8:
        # sliding window (photo road3): two sashes, glass split at the middle, 7 cm centre mullion
        m = (b0 + b1) / 2
        put(b0, m - 0.035)
        put(m + 0.035, b1)
        return [(m - 0.035, m + 0.035)]
    if b1 - b0 > 1.8:
        m = b0 + (b1 - b0) * 0.4
        put(b0, m - 0.03)
        put(m + 0.03, b1)
        return [(m - 0.03, m + 0.03)]
    put(b0, b1)
    return []


def is_open(h):
    """hole kind (sill, head, "open"): an opening into an empty (non-housing) space - no glass, deep dark recess"""
    return len(h) > 5 and isinstance(h[5], tuple) and len(h[5]) > 2 and h[5][2] == "open"


def backing(mb, w, a0, a1, holes, depth=WIN_IN + 0.04, deep_below=None):
    """one dark plate per floor behind the recessed glass (seen only through the holes)"""
    rows = {}
    for h in holes:
        if len(h) > 5 and (h[5] == "slot" or is_open(h)):
            continue
        r = rows.setdefault(h[4], [h[2], h[3]])
        r[0], r[1] = min(r[0], h[2]), max(r[1], h[3])
    iv = []                                           # rows of different floors may overlap (tall 1F-2F openings):
    for c0, c1 in sorted(rows.values()):              # merge them, else two plates share one plane
        if iv and c0 <= iv[-1][1] + 1e-3:
            iv[-1][1] = max(iv[-1][1], c1)
        else:
            iv.append([c0, c1])
    for c0, c1 in iv:
        d = 0.39 if deep_below is not None and c1 < deep_below else depth
        mb.rect(K.face_pts(w["axis"], w["c"] - w["s"] * d, w["s"], a0, a1, c0, c1), "frame")


def merge_l2(rects, recolor=True):
    """LOD2 wall rects: join side-by-side ones with the same height and material, then stacked ones with the same
    width and material (every sliver is kept so there is no see-through slit, and the count stays in the budget).
    Also used for LOD2 roof cells (key = z, a = x, c = y) with recolor=False"""
    def join(rs, ka, kb):                          # ka = (lo, hi) index of the joined axis, kb = the other one
        out = []
        grp = {}
        for r in rs:
            grp.setdefault((r[0], round(r[kb[0]], 4), round(r[kb[1]], 4), r[5]), []).append(r)
        for g in grp.values():
            g.sort(key=lambda r: r[ka[0]])
            cur = list(g[0])
            for r in g[1:]:
                if abs(r[ka[0]] - cur[ka[1]]) < 1e-3:
                    cur[ka[1]] = r[ka[1]]
                else:
                    out.append(tuple(cur))
                    cur = list(r)
            out.append(tuple(cur))
        return out
    if not recolor:
        return join(join(rects, (1, 2), (3, 4)), (3, 4), (1, 2))
    rows = {}
    for r in rects:
        rows.setdefault((r[0], round(r[3], 4), round(r[4], 4)), []).append(list(r))
    for g in rows.values():                        # a sliver (< 1.5 m) takes its wider neighbour's material (far view only)
        g.sort(key=lambda r: r[1])
        for i, r in enumerate(g):
            if r[2] - r[1] < 1.5:
                nb = [q for q in (g[i - 1] if i > 0 else None, g[i + 1] if i + 1 < len(g) else None)
                      if q is not None and q[2] - q[1] >= 1.5 and (abs(q[2] - r[1]) < 1e-3 or abs(q[1] - r[2]) < 1e-3)]
                if nb:
                    r[5] = max(nb, key=lambda q: q[2] - q[1])[5]
    rects = [list(r) for g in rows.values() for r in g]
    walls_ = {}
    for r in rects:
        walls_.setdefault(r[0], []).append(r)
    for g in walls_.values():                      # a short wall (outline step < 1.5 m): one colour top to bottom
        if max(r[2] for r in g) - min(r[1] for r in g) < 1.5:
            m = max(g, key=lambda r: (r[4] - r[3]) * (r[2] - r[1]))[5]
            for r in g:
                r[5] = m
    rects = [tuple(r) for r in rects]
    return join(join(rects, (1, 2), (3, 4)), (3, 4), (1, 2))


def build_lod2_shell(T, lod2, base_top):
    """LOD2 walls + roofs from the plain blocks raised by the parapet (no parapet strips: no coping ring / inner
    parapet faces, which used most of the 500 tris). Every wall piece is drawn, slivers too: skipping < 1.5 m pieces
    left full-height see-through slits. Zone colours as before, joined per wall (merge_l2)"""
    blocks2 = [tuple(b[:4]) + (b[4] + (PARAPET if b[4] >= 15.0 else 0.0),) + tuple(b[5:]) for b in T["blocks"]]
    xs2, ys2, H2 = heightfield(blocks2)
    walls2 = walls_of(xs2, ys2, H2)
    rects = []
    for wi, w in enumerate(walls2):
        for a0, a1, z0, z1, zone in cream_split(T, split_zones(w, T)):
            if zone.get("lod2_skip"):
                continue
            mat_of = zone.get("mat", MAT[zone["t"]])
            for c0, c1, m in ((z0, min(z1, base_top), base_mat(T, w, (a0 + a1) / 2)), (max(z0, base_top), zone.get("lod2_z1", z1), mat_of)):
                if c1 - c0 > 1e-3 and a1 - a0 > 1e-3:
                    rects.append((wi, a0, a1, c0, c1, m))   # lod2_z1: the piece under a skipped top band covers it
    for wi, a0, a1, c0, c1, m in merge_l2(rects):
        w = walls2[wi]
        lod2.rect(K.face_pts(w["axis"], w["c"], w["s"], a0, a1, c0, c1), m)
    tops = []
    for x0, x1, y0, y1, z in roofs_of(xs2, ys2, H2):
        m = "roof"
        for rx0, rx1, ry0, ry1, rz, rm in T.get("roof_mats", []):
            if rx0 - 1e-3 <= x0 and x1 <= rx1 + 1e-3 and ry0 - 1e-3 <= y0 and y1 <= ry1 + 1e-3 and abs(z - rz) < 0.05:
                m = rm
        tops.append((round(z, 4), x0, x1, y0, y1, m))
    for z, x0, x1, y0, y1, m in merge_l2(tops, recolor=False):
        K.floor_quad(lod2, x0, x1, y0, y1, z, m)


def backing_lod1(mb, w, a0, a1, z0, z1, holes, deep_below=None):
    """LOD1 has the holes but no reveals: one dark plate over the whole wall piece (not one per window row), so a
    ray through any hole at any angle hits it instead of the open inside of the building (seen-through LOD1)"""
    if not holes:
        return
    c0 = max(z0, min(h[2] for h in holes) - 0.8)
    c1 = min(z1, max(h[3] for h in holes) + 0.8)
    d = 0.39 if deep_below is not None and min(h[2] for h in holes) < deep_below else WIN_IN + 0.04
    mb.rect(K.face_pts(w["axis"], w["c"] - w["s"] * d, w["s"], a0, a1, c0, c1), "frame")   # to the piece ends (2 cm inset left slits)
    for h in holes:                                # holes near a piece end: the side jamb, else a slanted look passes the
        for b, edge, sgn in ((h[0], a0, 1), (h[1], a1, -1)):   # plate end into the open inside (all jambs: LOD1 too big)
            if abs(b - edge) < 0.6:
                quad_n(mb, [wpt(w, b, -d, h[2]), wpt(w, b, 0.0, h[2]), wpt(w, b, 0.0, h[3]), wpt(w, b, -d, h[3])], along_vec(w, sgn), "frame")


def make_screen_painter(c):
    """triangle perforated screen (back wing): white lattice, triangle holes alpha 0"""
    import numpy as np
    # cell = 3.6 x 4.0 m: 3 triangle pairs across (1.2 m), 4 rows (1.0 m), every 2nd row shifted half a pair
    u = (c.u * 3.0) % 1.0
    v = (c.v * 4.0) % 1.0
    flip = (np.floor(c.v * 4.0).astype(int) % 2) == 1
    uu = np.where(flip, (u + 0.5) % 1.0, u)
    tri_up = (v > 0.12) & (v < 0.88) & (np.abs(uu - 0.5) < (0.88 - v) * 0.5 - 0.06)
    tri_dn = (v > 0.12) & (v < 0.88) & (np.abs(((uu + 0.5) % 1.0) - 0.5) < (v - 0.12) * 0.5 - 0.06)
    hole = tri_up | tri_dn
    c.alpha[hole] = 0
    c.rgb[hole] = (40, 40, 44)
    c.grain(amp=2)


def plate(mb, P, t, region, bottom=None):
    """sloped roof plate: 4 top corners P (x, y, z), thickness t (top, bottom, 4 edges); bottom = other material underneath"""
    Q = [(p[0], p[1], p[2] - t) for p in P]
    skew = math.hypot(P[0][0] + P[2][0] - P[1][0] - P[3][0], P[0][1] + P[2][1] - P[1][1] - P[3][1])
    warp = abs(P[0][2] + P[2][2] - P[1][2] - P[3][2])
    if skew > 0.05 or warp > 0.02:
        # trapezoid plan (diagonal edge) or warped top: the kit tiler assumes a flat parallelogram and one warped quad
        # splits on either diagonal (bottom poked through the top) -> top AND bottom in the same small bilinear pieces
        tw, th = (mb.atlas.tile_size(region) if mb.atlas.is_tiled(region) and mb.split_tiles else (2.0, 2.0))
        nu = max(1, math.ceil(max(math.dist(P[0], P[1]), math.dist(P[3], P[2])) / tw))
        nv = max(1, math.ceil(max(math.dist(P[0], P[3]), math.dist(P[1], P[2])) / th))
        for S, nz, reg in ((P, 1, region), (Q, -1, bottom or region)):
            for i in range(nu):
                for j in range(nv):
                    q = [_bil(S, i / nu, j / nv), _bil(S, (i + 1) / nu, j / nv), _bil(S, (i + 1) / nu, (j + 1) / nv),
                         _bil(S, i / nu, (j + 1) / nv)]
                    u_ = [q[1][k] - q[0][k] for k in range(3)]; v_ = [q[3][k] - q[0][k] for k in range(3)]
                    if (u_[0] * v_[1] - u_[1] * v_[0]) * nz < 0:
                        q = [q[1], q[0], q[3], q[2]]
                    if mb.atlas.is_tiled(reg) and mb.split_tiles:
                        mb.quad(q, mb.atlas.uv_tile(reg, math.dist(q[0], q[1]), math.dist(q[0], q[3])), reg)
                    else:
                        mb.rect(q, reg)
    else:
        quad_n(mb, P, (0, 0, 1), region)
        quad_n(mb, Q, (0, 0, -1), bottom or region)
    cx, cy = sum(p[0] for p in P) / 4, sum(p[1] for p in P) / 4
    for i in range(4):
        j = (i + 1) % 4
        mx, my = (P[i][0] + P[j][0]) / 2 - cx, (P[i][1] + P[j][1]) / 2 - cy
        quad_n(mb, [Q[i], Q[j], P[j], P[i]], (mx, my, 0), region)


def blocked_by(blocks, w, z, dist=1.5):
    """True if a block taller than z stands within dist in front of the wall middle"""
    am = (w["a0"] + w["a1"]) / 2
    for d in (0.2, dist / 2, dist):
        p = wpt(w, am, d, z)
        for b in blocks:
            if b[0] < p[0] < b[1] and b[2] < p[1] < b[3] and b[4] > z:
                return True
    return False


def build_lounge(L, blocks, main, lod1, lod2, wins, k0=0):
    """glass box (curtain wall on every free face). slope=(ya, yb, zb): top rises from z1 at y=ya to zb at y=yb;
    the sloped part is closed with trapezoid glass-colour panels (roof plate comes from build_roof_parts)"""
    rects = [r + (1.0,) for r in L["rects"]]
    xs, ys, H = heightfield(rects)
    z0, z1 = L["z0"], L["z1"]
    sl = L.get("slope")
    ztop = (lambda y: z1 + (y - sl[0]) / (sl[1] - sl[0]) * (sl[2] - z1)) if sl else (lambda y: z1)
    for k, w in enumerate(walls_of(xs, ys, H)):
        for mb in (main, lod1, lod2):            # LOD2 too, narrow faces included (skipped ones were see-through)
            mb.rect(K.face_pts(w["axis"], w["c"], w["s"], w["a0"], w["a1"], z0, z1), "spandrel")
        if sl:
            if w["axis"] == "x":                       # side faces: trapezoid above z1
                pa, pb = wpt(w, w["a0"], 0.0, z1), wpt(w, w["a1"], 0.0, z1)
                pts = [pa, pb, (pb[0], pb[1], ztop(w["a1"])), (pa[0], pa[1], ztop(w["a0"]))]
                for mb in (main, lod1, lod2):
                    quad_n(mb, pts, out_vec(w), "spandrel")
            elif ztop(w["c"]) > z1 + 0.05:            # back face: band up to the high edge
                for mb in (main, lod1, lod2):
                    mb.rect(K.face_pts(w["axis"], w["c"], w["s"], w["a0"], w["a1"], z1, ztop(w["c"])), "spandrel")
        sm = [m for (ax, c), m in L.get("solid_mat", {}).items() if w["axis"] == ax and abs(w["c"] - c) < 0.05]
        if sm:                                        # clad (not glass) face: paint over the spandrel
            K.paint(main, w["axis"], w["c"], w["s"], w["a0"], w["a1"], z0, z1, sm[0])
        if blocked_by(blocks, w, (z0 + z1) / 2) or any(w["axis"] == ax and abs(w["c"] - c) < 0.05 for ax, c in L.get("solid", [])):
            continue                                  # wall against a core / shaft / roof plate: solid
        if L.get("rows"):
            lounge_cw(main, wins, w, w["a0"], w["a1"], z0, L["rows"], L.get("module", 1.2), 500 + (k0 + k) * 10)
            if sl and w["axis"] == "x":
                slope_cw(main, wins, w, w["a0"], w["a1"], z0 + sum(L["rows"]), ztop, L.get("module", 1.2),
                         len(L["rows"]), 500 + (k0 + k) * 10)
            continue
        K.curtainwall(main, w["axis"], w["c"], w["s"], w["a0"], w["a1"], z0, z1, L.get("row", z1 - z0), wins, lod1=lod1,
                      module_w=L.get("module", 1.5), spandrel_h=L.get("sp", 0.45), head_h=L.get("head", 0.9),
                      mullion=(0.07, 0.14), transom=(0.06, 0.10), unit0=500 + (k0 + k) * 10, unit_modules=4)
    for x0, x1, y0, y1, _ in roofs_of(xs, ys, H):
        if not sl:
            for mb in (main, lod1, lod2):
                K.floor_quad(mb, x0, x1, y0, y1, z1, "roof")
        for mb in (main, lod1, lod2):           # underside of the box (cantilever is seen from below)
            quad_n(mb, [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1), "spandrel")


def lounge_cw(main, wins, w, a0, a1, z0, rows, module, unit0):
    """glass wall with unequal pane rows (rows = heights from the bottom): mullions 7 x 14 cm on a module,
    transoms 6 x 10 cm between rows, one _Win pane per cell kept clear of every member"""
    ax, c, sd = w["axis"], w["c"], w["s"]
    n = max(1, round((a1 - a0) / module))
    es = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    bs = [z0]
    for r in rows:
        bs.append(bs[-1] + r)
    z1 = bs[-1]
    for i, e in enumerate(es):                      # mullions (end ones inside the face)
        m0, m1 = (e, e + 0.07) if i == 0 else ((e - 0.07, e) if i == n else (e - 0.035, e + 0.035))
        K.axbox(main, ax, c, sd, m0, m1, 0.0, 0.14, z0 + 0.06, z1 - 0.06, "frame")   # between top / bottom rails
    for j, b in enumerate(bs):                      # transoms
        t0, t1 = (b, b + 0.06) if j == 0 else ((b - 0.06, b) if j == len(bs) - 1 else (b - 0.03, b + 0.03))
        K.axbox(main, ax, c, sd, a0 + 0.07, a1 - 0.07, 0.0, 0.10, t0, t1, "frame")
    for i in range(n):
        p0 = es[i] + (0.08 if i == 0 else 0.045)
        p1 = es[i + 1] - (0.08 if i + 1 == n else 0.045)
        for j in range(len(rows)):
            q0 = bs[j] + (0.07 if j == 0 else 0.04)
            q1 = bs[j + 1] - (0.07 if j + 1 == len(rows) else 0.04)
            wins.add_pts(K.face_pts(ax, c + sd * K.WIN_OFF, sd, p0, p1, q0, q1),
                         K.face_pts(ax, c + sd * K.LOD2_WIN_OFF, sd, p0, p1, q0, q1), p1 - p0, q1 - q0, j, unit0 + i // 4)


def slope_cw(main, wins, w, a0, a1, zb, ztop, module, row, unit0):
    """glass in the sloped trapezoid above the lounge rows (the panes run up to the
    sloped top). Same module as lounge_cw: mullions continue up to the slope, one pane per module, its top cut level
    under the lower corner (the small triangle above stays glass-tone spandrel)"""
    ax, c, sd = w["axis"], w["c"], w["s"]
    n = max(1, round((a1 - a0) / module))
    es = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    for i, e in enumerate(es):
        m0, m1 = (e, e + 0.07) if i == 0 else ((e - 0.07, e) if i == n else (e - 0.035, e + 0.035))
        zt = min(ztop(m0), ztop(m1)) - 0.02
        if zt - zb > 0.15:
            K.axbox(main, ax, c, sd, m0, m1, 0.0, 0.14, zb, zt, "frame")
    for i in range(n):
        p0 = es[i] + (0.08 if i == 0 else 0.045)
        p1 = es[i + 1] - (0.08 if i + 1 == n else 0.045)
        q0, q1 = zb + 0.04, min(ztop(p0), ztop(p1)) - 0.05
        if q1 - q0 < 0.25:
            continue
        wins.add_pts(K.face_pts(ax, c + sd * K.WIN_OFF, sd, p0, p1, q0, q1),
                     K.face_pts(ax, c + sd * K.LOD2_WIN_OFF, sd, p0, p1, q0, q1), p1 - p0, q1 - q0, row, unit0 + i // 4)


def build_poly_lounge(L, main, lod1, lod2, wins, k0=0):
    """glass lounge on a plan polygon (CCW, edges may be diagonal - 101_roof_detail: the east glass wall runs on a
    slant under the plate edge). Each edge is built in a local front-wall frame (axis y, c 0, s -1, a 0..len) and
    turned into place. edges[i]: "glass" / "solid" (glass-tone panel) / "white" / "skip"; plinth[i] = white wall
    from plinth_z up to z0 under that edge. Roof quads at zr (under the plate), underside quads at z0"""
    pts, z0, z1, zr = L["poly"], L["z0"], L["z1"], L["zr"]
    A = main.atlas
    for i, kind in enumerate(L["edges"]):
        if kind == "skip":
            continue
        (x0_, y0_), (x1_, y1_) = pts[i], pts[(i + 1) % len(pts)]
        ln = math.hypot(x1_ - x0_, y1_ - y0_)
        deg = math.degrees(math.atan2(y1_ - y0_, x1_ - x0_))   # local +a -> edge direction, local -y -> outward
        w = dict(axis="y", c=0.0, s=-1)
        tm, t1, t2, tw = K.MeshBuilder(A), K.MeshBuilder(A, split_tiles=False), K.MeshBuilder(A, split_tiles=False), K.WindowSet()
        reg = "white" if kind == "white" else "spandrel"
        for mb in (tm, t1, t2):                  # LOD2 too, short edges included (skipped ones were see-through)
            mb.rect(K.face_pts("y", 0.0, -1, 0.0, ln, z0, zr), reg)
        pz = (L.get("plinth") or {}).get(i)
        if pz is not None:
            for mb in (tm, t1, t2):
                mb.rect(K.face_pts("y", 0.0, -1, 0.0, ln, pz, z0), "white")
            for mb in (tm, t1, t2):              # inner side too: seen from the open side under the lounge
                mb.rect(K.face_pts("y", 0.02, 1, 0.0, ln, pz, z0), "white")
        if kind == "glass":
            lounge_cw(tm, tw, w, 0.0, ln, z0, L["rows"], L.get("module", 1.2), 500 + (k0 + i) * 10)
        for mb, dst in ((tm, main), (t1, lod1), (t2, lod2)):
            rotate_mb(mb, deg, x0_, y0_)
            dst.merge(mb)
        rotate_wins(tw, deg, x0_, y0_)
        clear = L.get("win_clear", [])           # plan rects of parts close in front: those panes keep only the frame
        for it in tw.items:                      # (kit rule: no _Win within 1.5 m), the glass-tone panel shows behind
            cx, cy = sum(p[0] for p in it["pts"]) / 4, sum(p[1] for p in it["pts"]) / 4
            if all(math.hypot(max(r[0] - cx, 0, cx - r[1]), max(r[2] - cy, 0, cy - r[3])) > 1.6 for r in clear):
                wins.items.append(it)
    for q in L.get("roof", []):
        for mb in (main, lod1, lod2):
            quad_n(mb, [(x, y, zr) for x, y in q], (0, 0, 1), "spandrel")   # non-tiled (trapezoids), under the plate
    for q in L.get("under", []):
        for mb in (main, lod1, lod2):
            quad_n(mb, [(x, y, z0) for x, y in q], (0, 0, -1), "spandrel")


def seg_prism(mb, w, p0, p1, tw, o0, o1, region):
    """bar between (a, z) points p0 -> p1 lying in the plane of wall w, width tw, depth o0..o1 (outward)"""
    da, dz = p1[0] - p0[0], p1[1] - p0[1]
    l = math.hypot(da, dz) or 1.0
    na, nz = -dz / l * tw / 2, da / l * tw / 2
    q = [(p0[0] - na, p0[1] - nz), (p1[0] - na, p1[1] - nz), (p1[0] + na, p1[1] + nz), (p0[0] + na, p0[1] + nz)]
    av = along_vec(w)
    for o, sg in ((o1, 1), (o0, -1)):
        quad_n(mb, [wpt(w, a, o, z) for a, z in q], out_vec(w, sg), region)
    for (a_0, z_0), (a_1, z_1), sg in ((q[0], q[1], -1), (q[3], q[2], 1)):
        n = (av[0] * na * sg, av[1] * na * sg, nz * sg)
        quad_n(mb, [wpt(w, a_0, o0, z_0), wpt(w, a_1, o0, z_1), wpt(w, a_1, o1, z_1), wpt(w, a_0, o1, z_0)], n, region)


def _hseg(mb, w, a0, a1, zc, hh, d, holes, blk):
    """horizontal joint bar at zc, cut around openings / signs it would cross"""
    cuts = sorted((q[0] - 0.05, q[1] + 0.05) for q in list(holes) + list(blk)
                  if q[2] - 0.35 < zc + hh / 2 and zc - hh / 2 < q[3] + 0.02)
    cur = a0
    for q0, q1 in cuts + [(a1, a1)]:
        if q0 - cur > 0.15:
            K.axbox(mb, w["axis"], w["c"], w["s"], cur, q0, 0.0, d, zc - hh / 2, zc + hh / 2, "cwjoint")
        cur = max(cur, q1)


def cw_joints(mb, w, a0, a1, z0, z1, lv, holes, blk, fh, G=None):
    """panel joints of a curtain-wall-look face as in the reference photo: thin lines just lighter than the panel.
    Verticals only at the left and right edge of every window (run the full zone height, cut around other openings
    and signs); horizontals only at each distinct sill height and at the head height of the windows (cut around openings).
    No module lines and no spandrel mid lines (too many joints)"""
    ax, c, sd = w["axis"], w["c"], w["s"]
    hs = [h for h in holes if h[5] not in ("slot", "D", "D2", "D3") and h[4] >= 1]
    if not hs:
        return
    jw, jo = 0.022, 0.015
    vs = []
    for h in hs:
        for e in (h[0] - jw / 2, h[1] + jw / 2):
            if a0 + 0.06 < e < a1 - 0.06 and all(abs(e - v) > 0.06 for v in vs):
                vs.append(e)
    for x in sorted(vs):
        cuts = sorted((q[2], q[3]) for q in list(hs) + list(blk) if q[0] + 0.005 < x < q[1] - 0.005)
        cur = z0
        for q2, q3 in cuts + [(z1, z1)]:
            if q2 - cur > 0.15:
                K.axbox(mb, ax, c, sd, x - jw / 2, x + jw / 2, 0.0, jo, cur + 0.01, q2 - 0.01, "cwjoint")
            cur = max(cur, q3)
    rel = []
    for h in hs:
        for o in (h[2] - lv[h[4]] - jw / 2, h[3] - lv[h[4]] + jw / 2):
            if all(abs(o - r) > 0.08 for r in rel):
                rel.append(o)
    for zl in lv[1:]:
        for o in rel:
            zz = zl + o
            if z0 + 0.15 < zz < z1 - 0.15:
                cuts = sorted((q[0], q[1]) for q in list(hs) + list(blk) if q[2] + 0.005 < zz < q[3] - 0.005)
                cur = a0 + 0.04
                for q0, q1 in cuts + [(a1 - 0.04, a1 - 0.04)]:
                    if q0 - cur > 0.15:
                        K.axbox(mb, ax, c, sd, cur, q0, 0.0, jo + 0.005, zz - jw / 2, zz + jw / 2, "cwjoint")
                    cur = max(cur, q1)


def draw_grid(mb, w, a0, a1, z0, z1, lv, holes, blk, G, slab=True):
    """panel joints of a curtain-wall-look face: verticals on a module (kept off the openings,
    cut around signs), slab transoms (punched faces) and extra horizontal joints at floor + mids"""
    if slab:
        for zl in lv[1:]:
            if z0 + 0.1 < zl < z1 - 0.1:
                _hseg(mb, w, a0 + 0.08, a1 - 0.08, zl, 0.08, 0.08, holes, blk)
    for zl in lv:
        for m in G.get("mids", []):
            if z0 + 0.1 < zl + m < z1 - 0.1:
                _hseg(mb, w, a0 + 0.08, a1 - 0.08, zl + m, 0.05, 0.05, holes, blk)
    n = max(1, int((a1 - a0) / G["mod"] + 0.5))
    for i in range(1, n):
        e = a0 + (a1 - a0) * i / n
        if any(h[0] - 0.15 < e < h[1] + 0.15 for h in holes):
            continue
        cuts = sorted((q[2], q[3]) for q in blk if q[0] - 0.05 < e < q[1] + 0.05)
        cur = z0
        for q2, q3 in cuts + [(z1, z1)]:
            if q2 - cur > 0.2:
                K.axbox(mb, w["axis"], w["c"], w["s"], e - 0.03, e + 0.03, 0.0, 0.06, cur, q2, "cwjoint")
            cur = max(cur, q3)


def build_xlattice(mb, X, lv):
    """stacked X bracing on a narrow face (shaft east face): one X per storey + storey bars"""
    w = dict(axis=X["axis"], c=X["c"], s=X["s"])
    a0, a1 = X["a0"], X["a1"]
    zs = [z for z in lv if X["z0"] - 0.01 <= z <= X["z1"] + 0.01]
    for k, z in enumerate(zs):
        seg_prism(mb, w, (a0 + 0.06, z), (a1 - 0.06, z), 0.12, 0.04, 0.18, "rail")
        if k + 1 < len(zs):
            zt = zs[k + 1]
            seg_prism(mb, w, (a0 + 0.08, z + 0.08), (a1 - 0.08, zt - 0.08), 0.10, 0.06, 0.16, "rail")
            seg_prism(mb, w, (a0 + 0.08, zt - 0.08), (a1 - 0.08, z + 0.08), 0.10, 0.08, 0.14, "rail")


def build_hang_truss(mb, w, a0, a1, zb, zt, depth=0.5, pitch=0.9, tw=0.08, first_post=True):
    """truss band hanging under a sloped plate: top chord under the plate, bottom chord `depth`
    lower (never below zb), Warren diagonals, end verticals only. Panels thinner than 0.45 m are left out"""
    n = max(1, round((a1 - a0) / pitch))
    nodes = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    bot = lambda a: max(zb + 0.05, zt(a) - depth)
    ok = [zt(a) - bot(a) > 0.3 for a in nodes]
    for i in range(n):
        p, q = nodes[i], nodes[i + 1]
        if not (ok[i] and ok[i + 1]):
            continue
        e = 0.01 * (i % 2)                         # neighbouring panels 1 cm apart: overlapping node ends never coplanar
        seg_prism(mb, w, (p, zt(p) - 0.06), (q, zt(q) - 0.06), tw, -0.21 - e, -0.03 + e, "truss")       # top chord
        seg_prism(mb, w, (p, bot(p) + 0.06), (q, bot(q) + 0.06), tw, -0.20 + e, -0.04 - e, "truss")     # bottom chord
        if i % 2 == 0:
            seg_prism(mb, w, (p, bot(p) + 0.06), (q, zt(q) - 0.06), tw * 0.8, -0.18, -0.06, "truss")
        else:
            seg_prism(mb, w, (p, zt(p) - 0.06), (q, bot(q) + 0.06), tw * 0.8, -0.17, -0.07, "truss")
    for i, a in enumerate(nodes):                   # verticals at the band ends and every 4th node
        edge = ok[i] and (i == 0 or i == n or not ok[i - 1] or not ok[i + 1])
        if ok[i] and (edge or i % 4 == 0) and (i or first_post):
            seg_prism(mb, w, (a, bot(a)), (a, zt(a)), tw, -0.235, -0.005, "truss")


def build_truss(mb, w, a0, a1, zb, zt, pitch=1.3, tw=0.12, first_post=True):
    """vertical Warren/X truss set just behind a face: posts at the panel nodes, X diagonals, top chord under
    the plate. Skips panels lower than 0.5 m. Depths differ by 1-2 cm so crossing members never share a plane"""
    n = max(1, round((a1 - a0) / pitch))
    nodes = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    for i, a in enumerate(nodes):
        if zt(a) - zb > 0.5 and (i or first_post):
            seg_prism(mb, w, (a, zb), (a, zt(a)), tw, -0.22, -0.02, "truss")
    for i in range(n):
        p, q = nodes[i], nodes[i + 1]
        if min(zt(p), zt(q)) - zb < 0.5:
            continue
        seg_prism(mb, w, (p, zb + 0.05), (q, zt(q) - 0.05), tw * 0.8, -0.18, -0.06, "truss")
        seg_prism(mb, w, (p, zt(p) - 0.05), (q, zb + 0.05), tw * 0.8, -0.20, -0.08, "truss")
        seg_prism(mb, w, (p, zt(p) - 0.06), (q, zt(q) - 0.06), tw, -0.21, -0.03, "truss")


def in_quad(P, x, y, m=0.0):
    """(x, y) inside the convex plan quad P (any corner order), at least m from every edge"""
    sg = 0.0
    for i in range(4):
        (ax_, ay_), (bx_, by_) = P[i][:2], P[(i + 1) % 4][:2]
        cr = (bx_ - ax_) * (y - ay_) - (by_ - ay_) * (x - ax_)
        L = math.hypot(bx_ - ax_, by_ - ay_)
        if sg == 0.0:
            sg = 1.0 if cr > 0 else -1.0
        if cr * sg < m * L:
            return False
    return True


def _bil(P, u, v):
    """bilinear point of a 4-corner plate: u along P0 -> P1, v along P0 -> P3"""
    a = [P[0][i] + (P[1][i] - P[0][i]) * u for i in range(3)]
    b = [P[3][i] + (P[2][i] - P[3][i]) * u for i in range(3)]
    return tuple(a[i] + (b[i] - a[i]) * v for i in range(3))


def plate_z(P, x, y):
    """height of a 4-corner plate at (x, y) on its bilinear surface (as drawn by plate()); plan (u, v) found by
    Newton steps, so trapezoid corners (diagonal edges, 101 roof) work. Outside points are clamped to the edge"""
    u, v = 0.5, 0.5
    for _ in range(12):
        px, py, _z = _bil(P, u, v)
        a, b = _bil(P, u + 1e-4, v), _bil(P, u, v + 1e-4)
        j11, j12 = (a[0] - px) / 1e-4, (b[0] - px) / 1e-4
        j21, j22 = (a[1] - py) / 1e-4, (b[1] - py) / 1e-4
        det = j11 * j22 - j12 * j21
        if abs(det) < 1e-12:
            break
        ex, ey = x - px, y - py
        u += (j22 * ex - j12 * ey) / det
        v += (-j21 * ex + j11 * ey) / det
    return _bil(P, min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))[2]


def plate_at(R, x, y):
    """top of the lowest roof plate above (x, y), or None"""
    zs = [plate_z(P, x, y) for P in R.get("plates", []) if in_quad(P, x, y)]
    return min(zs) if zs else None


PLT = 0.12          # roof plate thickness (thin white edge)


def clip_line(P, p, d, m=0.0):
    """part of the line p + t d inside the convex plan quad P (m inside its edges): ((x, y), (x, y)) or None"""
    cx, cy = sum(q[0] for q in P) / 4, sum(q[1] for q in P) / 4
    t0, t1 = -1e9, 1e9
    for i in range(4):
        (ax_, ay_), (bx_, by_) = P[i][:2], P[(i + 1) % 4][:2]
        ex, ey = bx_ - ax_, by_ - ay_
        L = math.hypot(ex, ey)
        nx_, ny_ = -ey / L, ex / L                     # unit normal, turned to the inside
        if nx_ * (cx - ax_) + ny_ * (cy - ay_) < 0:
            nx_, ny_ = -nx_, -ny_
        s0 = nx_ * (p[0] - ax_) + ny_ * (p[1] - ay_) - m   # >= 0 inside
        ds = nx_ * d[0] + ny_ * d[1]
        if abs(ds) < 1e-12:
            if s0 < 0:
                return None
            continue
        t = -s0 / ds
        if ds > 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    if t1 - t0 < 1e-6:
        return None
    return (p[0] + d[0] * t0, p[1] + d[1] * t0), (p[0] + d[0] * t1, p[1] + d[1] * t1)


def glaze_wedge(mb, lod1, w, a0, a1, zb, zt, module=1.2, first=True):
    """dark glass in the wedge between the lounge roof and the sloped plate above it, 1.2 m panels with thin joints"""
    n = max(1, round((a1 - a0) / module))
    nrm = out_vec(w)
    for i in range(n):
        p, q = a0 + (a1 - a0) * i / n, a0 + (a1 - a0) * (i + 1) / n
        if min(zt(p), zt(q)) - zb < 0.05:
            continue
        pts = [wpt(w, p + 0.03, 0.0, zb), wpt(w, q - 0.03, 0.0, zb), wpt(w, q - 0.03, 0.0, zt(q)), wpt(w, p + 0.03, 0.0, zt(p))]
        for m in (mb, lod1):
            quad_n(m, pts, nrm, "spandrel")
    for i in range(n + 1):                                       # vertical joints
        a = a0 + (a1 - a0) * i / n
        h = zt(a) - zb
        if h > 0.1 and (first or i):
            quad_n(mb, [wpt(w, a - 0.03, 0.02, zb), wpt(w, a + 0.03, 0.02, zb), wpt(w, a + 0.03, 0.02, zt(a)), wpt(w, a - 0.03, 0.02, zt(a))], nrm, "cwjoint")


def build_roof_parts(R, main, lod1, lod2):
    """101 roof: folded white plates, posts, sign frame / roof boxes, west slat frame"""
    for P in R.get("plates", []):
        plate(main, P, PLT, "roofw", bottom="sfgrid")
        plate(lod1, P, PLT, "roofw", bottom="sfgrid")
        area = 0.5 * abs(sum(P[i][0] * P[(i + 1) % 4][1] - P[(i + 1) % 4][0] * P[i][1] for i in range(4)))
        if area > 0:                               # LOD2: every plate (small ones left the lounge below open)
            quad_n(lod2, P, (0, 0, 1), "roofw")
            # underside too: from the street a tall tower's roof plate is seen from below (no underside = see-through)
            quad_n(lod2, [(x, y, z - PLT) for x, y, z in P], (0, 0, -1), "sfgrid")
            cx_, cy_ = sum(p[0] for p in P) / 4, sum(p[1] for p in P) / 4
            for i in range(4):                     # 4 edge faces (thin see-through lines from below otherwise)
                p, q = P[i], P[(i + 1) % 4]
                mx, my = (p[0] + q[0]) / 2 - cx_, (p[1] + q[1]) / 2 - cy_
                quad_n(lod2, [(p[0], p[1], p[2] - PLT), (q[0], q[1], q[2] - PLT), q, p], (mx, my, 0.0), "roofw")
    for x, y, z0, z1 in R.get("posts", []):
        if z1 is None:                            # up to the underside of the plate above the post
            zp_ = plate_at(R, x, y)
            z1 = zp_ - PLT if zp_ is not None else z0 + 2.6
        main.box(x - 0.12, x + 0.12, y - 0.12, y + 0.12, z0, z1, "frame", skip=("bottom", "top"))
    # wedge under the plates stays open: the space frame is seen through it
    for x, y, z0, sz in R.get("columns", []):
        z1 = plate_at(R, x, y) - PLT
        for mb in (main, lod1):
            mb.box(x - sz / 2, x + sz / 2, y - sz / 2, y + sz / 2, z0, z1, "colgrey", skip=("bottom", "top"))
    for x, y, z0, z1 in R.get("wposts", []):
        for mb in (main, lod1):
            mb.box(x - 0.08, x + 0.08, y - 0.08, y + 0.08, z0, z1, "fin", skip=("bottom",))
    for x0, x1, y0, y1, z0, z1, reg in R.get("boxes", []):
        for mb in (main, lod1):
            mb.box(x0, x1, y0, y1, z0, z1, reg, skip=("bottom",))
    F = R.get("slat_frame")
    if F:
        x0, x1, y0, y1, z0, z1, t = F["x0"], F["x1"], F["y0"], F["y1"], F["z0"], F["z1"], 0.3
        for mb in (main, lod1):
            # solid white front fin (front elevation: white up to the plate) + back post + top beam
            mb.box(x0, x1, y0, y0 + t, z0, z1, "fin", skip=("bottom",))
            mb.box(x0, x1, y1 - t, y1, z0, z1, "fin", skip=("bottom",))
            mb.box(x1 - t, x1, y0 + t, y1 - t, z1 - t, z1, "fin", skip=("front", "back"))
            mb.box(x0, x0 + t, y0 + t, y1 - t, z1 - t, z1, "fin", skip=("front", "back"))
        n = int((y1 - y0 - 2 * t) / F["pitch"])
        for k in range(1, n + 1):                 # vertical slats on the west face
            yy = y0 + t + k * (y1 - y0 - 2 * t) / (n + 1)
            main.box(x0, x0 + 0.2, yy - 0.05, yy + 0.05, z0, z1 - t, "fin", skip=("bottom", "top"))


SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
       "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcfgd"}


def _edge_normal(w, a1, z1, a2, z2, pts2):
    ca = sum(p[0] for p in pts2) / len(pts2); cz = sum(p[1] for p in pts2) / len(pts2)
    ma, mz = (a1 + a2) / 2 - ca, (z1 + z2) / 2 - cz
    av = along_vec(w)
    return (av[0] * ma, av[1] * ma, mz)


# ---- dong-number font: clean geometric sans, even stroke, true curves (no 7-segment / no Gulim look).
# Each digit = centre-line paths in a unit cell (u 0..GW, v 0..1). Strokes are swept with mitred offsets, so the
# front of one path is one strip of quads without overlaps; separate paths of a digit sit 1 cm apart in depth.
GW, GS = 0.60, 0.115                                   # digit width, stroke (fractions of the digit height)


def _arc(cx, cy, rx, ry, a0, a1, n=14):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def _glyph_paths(ch):
    r, W = GS / 2, GW
    cx, R = W / 2, W / 2 - GS / 2                       # centre / x radius of bowls
    if ch == "0":                                       # oval
        return [(_arc(cx, 0.5, R, 0.5 - r, 0, 360, 28)[:-1], True)]
    if ch == "1":
        x = W * 0.58
        return [([(W * 0.16, 1 - r - 0.17), (x, 1 - r), (x, 0.0)], False)]
    if ch == "2":
        top = _arc(cx, 1 - r - R, R, R, 165, -40, 14)
        return [(top + [(r + 0.01, r), (W, r)], False)]
    if ch == "3":
        up = _arc(cx, 0.75 - r / 2, R * 0.92, 0.25 - r / 2, 160, -90, 12)
        lo = _arc(cx, 0.27, R, 0.27 - r, 90, -160, 14)
        return [(up, False), (lo, False)]
    if ch == "4":
        return [([(W * 0.70, 1 - r * 1.4), (r, 0.30), (W, 0.30)], False),      # behind the stem
                ([(W * 0.70, 0.0), (W * 0.70, 1.0)], False)]
    if ch == "5":
        lo = _arc(cx, 0.31, R, 0.31 - r, 125, -150, 14)
        return [([(W - r * 0.4, 1 - r), (r + 0.03, 1 - r), (r, 0.55)] + lo[1:], False)]
    if ch == "6":
        return [(_arc(cx, 0.31, R, 0.31 - r, 0, 360, 20)[:-1], True),
                (_arc(cx + R * 0.15, 0.62, R * 1.1, 0.38 - r, 70, 180, 10) + [(r + 0.005, 0.31)], False)]
    if ch == "7":
        return [([(r * 0.4, 1 - r), (W - r, 1 - r), (W * 0.32, 0.0)], False)]
    if ch == "8":
        return [(_arc(cx, 0.76, R * 0.88, 0.24 - r / 2, -90, 270, 18)[:-1], True),
                (_arc(cx, 0.27, R, 0.27 - r, 90, 450, 20)[:-1], True)]
    if ch == "9":
        p = _glyph_paths("6")
        return [([(W - u, 1 - v) for u, v in pts], cl) for pts, cl in p]
    return []


def _offset(pts, closed, r):
    """left / right offset chains of a centre-line (mitre, clamped)"""
    n = len(pts)
    segs = [(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]) for i in range(n if closed else n - 1)]
    nrm = []
    for dx, dy in segs:
        l = math.hypot(dx, dy) or 1.0
        nrm.append((-dy / l, dx / l))
    L, Rr = [], []
    for i in range(n):
        if closed:
            n0, n1 = nrm[i - 1], nrm[i % len(nrm)]
        else:
            n0 = nrm[max(i - 1, 0)]; n1 = nrm[min(i, len(nrm) - 1)]
        mx, my = n0[0] + n1[0], n0[1] + n1[1]
        ml = math.hypot(mx, my) or 1.0
        mx, my = mx / ml, my / ml
        k = min(2.0, 1.0 / max(0.2, mx * n1[0] + my * n1[1]))
        L.append((pts[i][0] + mx * r * k, pts[i][1] + my * r * k))
        Rr.append((pts[i][0] - mx * r * k, pts[i][1] - my * r * k))
    return L, Rr, nrm


def dong_number(mb, w, text, a_mid, z0, hgt, region="signw"):
    """raised dong number (6 cm proud). a_mid = centre along the wall; reads left-to-right as seen from outside"""
    gap = 0.20 * hgt
    total = len(text) * GW * hgt + (len(text) - 1) * gap
    sgn = 1 if side_of(w) in ("F", "R") else -1
    av = along_vec(w)
    for i, ch in enumerate(text):
        left = a_mid - sgn * total / 2 + sgn * i * (GW * hgt + gap)
        tw = lambda u, v, d: wpt(w, left + sgn * u * hgt, d, z0 + v * hgt)
        for pi, (pts, closed) in enumerate(_glyph_paths(ch)):
            d = 0.06 + 0.01 * pi
            L, Rr, nrm = _offset(pts, closed, GS / 2)
            n = len(pts)
            rng = range(n) if closed else range(n - 1)
            for k in rng:
                j = (k + 1) % n
                quad_n(mb, [tw(*Rr[k], d), tw(*Rr[j], d), tw(*L[j], d), tw(*L[k], d)], out_vec(w), region)
                nx, ny = nrm[k % len(nrm)]
                nl = (av[0] * sgn * nx, av[1] * sgn * nx, ny)
                quad_n(mb, [tw(*L[k], 0.0), tw(*L[j], 0.0), tw(*L[j], d), tw(*L[k], d)], nl, region)
                quad_n(mb, [tw(*Rr[k], 0.0), tw(*Rr[j], 0.0), tw(*Rr[j], d), tw(*Rr[k], d)], (-nl[0], -nl[1], -nl[2]), region)
            if not closed:                              # end caps
                for k, sgc in ((0, -1), (n - 1, 1)):
                    q = k - 1 if k else 0
                    dx, dy = pts[min(k + 1, n - 1)][0] - pts[max(k - 1, 0)][0], pts[min(k + 1, n - 1)][1] - pts[max(k - 1, 0)][1]
                    l = math.hypot(dx, dy) or 1.0
                    nc = (av[0] * sgn * sgc * dx / l, av[1] * sgn * sgc * dx / l, sgc * dy / l)
                    quad_n(mb, [tw(*L[k], 0.0), tw(*Rr[k], 0.0), tw(*Rr[k], d), tw(*L[k], d)], nc, region)


def build_extras(T, walls, main, lod1):
    """dong numbers, entrance canopies, roof equipment (per tower lists)"""
    for sg in T.get("signs", []):
        for w in walls:
            if side_of(w) == sg["s"] and abs(w["c"] - sg["c"]) < 0.15 and w["a0"] < sg["a"] < w["a1"]:
                dong_number(main, w, T["dong"], sg["a"], sg["z"], sg["h"], sg.get("region", "signw"))
                break
    for b_ in T.get("bars", []):                    # thin raised lines on a wall (beside a dong number)
        K.axbox(main, b_["axis"], b_["c"], b_["s"], b_["a0"], b_["a1"], 0.0, b_["out"], b_["z0"], b_["z1"], b_.get("mat", "signw"))
    build_ribs(T, main)
    build_rails(T, main)
    for S in T.get("stairs", []):
        build_stair(main, S)
    for x0_, x1_, y0_, y1_, z0_, z1_, m_ in T.get("solids", []):   # plain solid boxes on a roof (walls with a door gap)
        for mb in (main, lod1):
            mb.box(x0_, x1_, y0_, y1_, z0_, z1_, m_, skip=("bottom",))
    for F in T.get("frames", []):                   # white portal frame (2 posts + head) proud of a wall
        ax, c, sd, a0, a1, z0, z1, t, dp = F["axis"], F["c"], F["s"], F["a0"], F["a1"], F["z0"], F["z1"], F["t"], F["depth"]
        for mb in (main, lod1):
            K.axbox(mb, ax, c, sd, a0, a0 + t, 0.0, dp, z0, z1 - t, "fin")
            K.axbox(mb, ax, c, sd, a1 - t, a1, 0.0, dp, z0, z1 - t, "fin")
            K.axbox(mb, ax, c, sd, a0, a1, 0.0, dp, z1 - t, z1, "fin")
        for p0, p1, q0, q1, pd in F.get("panels", []):      # flat white panels on the wall inside the frame
            K.axbox(main, ax, c, sd, p0, p1, 0.0, pd, q0, q1, "fin")
        if F.get("step"):                                   # step slab in front of the doors
            b0, b1, sdp, sh = F["step"]
            o0, o1 = (c, c + sdp) if sd > 0 else (c - sdp, c)
            for mb in (main, lod1):
                if ax == "y":
                    mb.box(b0, b1, o0, o1, 0.0, sh, "coping", skip=("bottom", "front" if sd > 0 else "back"))
                else:
                    mb.box(o0, o1, b0, b1, 0.0, sh, "coping", skip=("bottom", "left" if sd > 0 else "right"))
    for cn in T.get("canopies", []):                    # optional 7th item = material (closed box with a bottom face)
        x0, x1, y0, y1, z0, z1 = cn[:6]
        for mb in (main, lod1):
            mb.box(x0, x1, y0, y1, z0, z1, cn[6] if len(cn) > 6 else dict(default="canopy", top="roof"))
    for x0, x1, y0, y1, z0, z1 in T.get("roofbox", []):
        main.box(x0, x1, y0, y1, z0, z1, dict(default="louver", top="frame"), skip=("bottom",))


def rib_lines(R):
    """106 west relief panel (106_num_detail, scan L270): (a, z) line list per row between the horizontal joints.
    Rows of 2 floors near the ground carry near-vertical creases leaning one way, the lean grows with height and the
    creases alternate (long thin triangles); the short rows near the top are zigzag triangles, every row shifted by
    half a period (diamond look). Crease positions / leans are estimated from the photo, joint heights are measured."""
    a0, a1 = R["a0"], R["a1"]
    js = R["joints"]
    out = []
    for i in range(len(js) - 1):
        zb, zt = js[i] + R["jh"] / 2, js[i + 1] - R["jh"] / 2
        h = js[i + 1] - js[i]
        if h > 5.0:                                    # 2-floor rows: 6 creases
            n, wd = 6, a1 - a0
            t = min(1.0, js[i] / 77.0)
            for k in range(n):
                ab = a0 + wd * (k + 0.5) / n
                if js[i] < 37.0:
                    d = 0.12 + 0.25 * t if k not in (4, 5) else 0.03
                else:
                    d = (0.3 + 0.35 * t) * (1 if k % 2 == 0 else -1)
                out.append(((ab, zb), (min(a1 - 0.05, max(a0 + 0.05, ab + d)), zt)))
        else:                                          # zigzag triangles, period shrinks toward the top
            P = 1.67 if h > 2.5 else 1.45
            off = (i % 2) * P / 2
            k = -1
            while True:
                b = a0 + off + k * P
                if b > a1:
                    break
                for p0, p1 in (((b, zb), (b + P / 2, zt)), ((b + P, zb), (b + P / 2, zt))):
                    q = clip_seg(p0, p1, a0 + 0.04, a1 - 0.04)
                    if q:
                        out.append(q)
                k += 1
    return out


def clip_seg(p0, p1, lo, hi):
    """clip a segment (a, z) to lo <= a <= hi; None if nothing is left (or a sliver)"""
    (a_0, z_0), (a_1, z_1) = p0, p1
    t0, t1 = 0.0, 1.0
    da = a_1 - a_0
    for lim, sg in ((lo, 1), (hi, -1)):
        if abs(da) < 1e-9:
            if sg * (a_0 - lim) < 0:
                return None
            continue
        t = (lim - a_0) / da
        if sg * da > 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    if t1 - t0 < 0.08:
        return None
    return ((a_0 + da * t0, z_0 + (z_1 - z_0) * t0), (a_0 + da * t1, z_0 + (z_1 - z_0) * t1))


def build_rails(T, main):
    """steel railings on a low roof edge (107_low_detail): posts ~1.5 m, square pickets 2 cm at 0.11 m, bottom rail and
    handrail; pts = polyline (x, y) along the edge, z0 = deck level, h = rail height"""
    for R in T.get("rails", []):
        rail_line(main, R["pts"], R["z0"], R.get("h", 1.1))


def rail_line(mb, pts, z0, h, pickets=True, closed=False):
    """one steel railing along a polyline (107_low_detail): posts ~1.5 m, square pickets 2 cm at 0.11 m (hidden ends
    skipped), bottom rail and handrail. closed = the last point is the first one (no doubled corner post)"""
    q = [pts[0]]
    for p_ in pts[1:]:                                # drop repeated points (cut / snapped ends)
        if math.hypot(p_[0] - q[-1][0], p_[1] - q[-1][1]) > 0.15:
            q.append(p_)
    pts = q
    for i in range(len(pts) - 1):
        (xa, ya), (xb, yb) = pts[i], pts[i + 1]
        L = math.hypot(xb - xa, yb - ya)
        if L < 0.15:
            continue
        ux, uy = (xb - xa) / L, (yb - ya) / L
        e = 0.045 if i == 0 and not closed else 0.04     # rails start inside the end post (end faces 2.5 cm from post faces)
        f = 0.045 if i == len(pts) - 2 and not closed else RAIL_F   # ... and end inside the last post; past the corner post
        def bar(t0, t1, za, zb, wd, m="frame", skip=None):
            xs_ = sorted((xa + ux * t0 - wd / 2 * abs(uy), xa + ux * t1 + wd / 2 * abs(uy)))
            ys_ = sorted((ya + uy * t0 - wd / 2 * abs(ux), ya + uy * t1 + wd / 2 * abs(ux)))
            mb.box(xs_[0], xs_[1], ys_[0], ys_[1], za, zb, m, skip=skip or (("bottom",) if za <= z0 + 1e-6 else ()))
        bar(e, L - f, z0 + h - 0.05, z0 + h, 0.05)               # handrail
        if pickets:
            bar(e, L - f, z0 + 0.10, z0 + 0.14, 0.035)           # bottom rail
        n = max(1, round(L / 1.5))
        for k in range(n + 1):                                       # posts
            t = min(max(k * L / n, 0.045), L - 0.045)        # end post faces 1.5 cm off the wall at a run end
            if (i > 0 or closed) and k == 0:
                continue
            bar(t - 0.03, t + 0.03, z0, z0 + h - 0.05, 0.05, skip=("bottom", "top"))
        if not pickets:
            continue
        m = int((L - 0.2) / 0.11)
        for k in range(m):                                           # pickets between the rails (ends hidden in the rails)
            t = 0.1 + k * 0.11 + 0.055
            if any(abs(t - j * L / n) < 0.06 for j in range(n + 1)):
                continue
            bar(t - 0.01, t + 0.01, z0 + 0.14, z0 + h - 0.05, 0.02, skip=("bottom", "top"))


def build_roof_rails(T, segs, main, lod1):
    """steel railings on the lowered roof edges (ROOF_RAILS): line 0.15 m inside the wall face (centre of the upstand),
    cut around crown posts / roof solids standing on it, segments meeting at a corner joined into one polyline"""
    h = RAIL_DIM.get(T.get("dong"), (0.4, 1.1))[1]
    obst = [p for F in T.get("crown_frames", []) for p in F["posts"]] + [s_[:4] for s_ in T.get("solids", [])]         + [tuple(b_[:4]) for b_ in T.get("full_strips", [])]      # stop at a full parapet strip (corner of a solid parapet)
    lines = []
    for g in segs:
        o = g["c"] - g["s"] * 0.15
        cur = [(g["a0"], g["a1"])]
        for x0, x1, y0, y1 in obst:                  # cut where the line passes through a post (2 cm clear)
            b0, b1, n0, n1 = (x0, x1, y0, y1) if g["axis"] == "y" else (y0, y1, x0, x1)
            if not (n0 - 0.03 < o < n1 + 0.03):
                continue
            nxt = []
            for u0, u1 in cur:
                if b1 + 0.02 <= u0 or b0 - 0.02 >= u1:
                    nxt.append((u0, u1))
                    continue
                if b0 - 0.02 - u0 > 0.3:
                    nxt.append((u0, b0 - 0.02))
                if u1 - b1 - 0.02 > 0.3:
                    nxt.append((b1 + 0.02, u1))
            cur = nxt
        for sk in T.get("rail_skip", ()):            # (axis, c, a0, a1): no railing on that part of a run (a screen wall stands there)
            if sk[0] != g["axis"] or abs(sk[1] - g["c"]) > 1e-3:
                continue
            nxt = []
            for u0, u1 in cur:
                if sk[3] <= u0 or sk[2] >= u1:
                    nxt.append((u0, u1))
                    continue
                if sk[2] - u0 > 0.3:
                    nxt.append((u0, sk[2]))
                if u1 - sk[3] > 0.3:
                    nxt.append((sk[3], u1))
            cur = nxt
        for u0, u1 in cur:
            P = [(u0, o), (u1, o)] if g["axis"] == "y" else [(o, u0), (o, u1)]
            lines.append(dict(pts=P, z0=g["z0"], ax=g["axis"]))
    # join perpendicular segments whose ends lie within 0.4 m of the crossing of their lines
    for i, A in enumerate(lines):
        for B in lines[i + 1:]:
            if A["ax"] == B["ax"] or abs(A["z0"] - B["z0"]) > 1e-3:
                continue
            X = (A["pts"][0][0], B["pts"][0][1]) if A["ax"] == "x" else (B["pts"][0][0], A["pts"][0][1])
            for ka in (0, -1):
                for kb in (0, -1):
                    pa, pb = A["pts"][ka], B["pts"][kb]
                    if math.hypot(pa[0] - X[0], pa[1] - X[1]) < 0.4 and math.hypot(pb[0] - X[0], pb[1] - X[1]) < 0.4:
                        A["pts"][ka] = X
                        B["pts"][kb] = X
    used = [False] * len(lines)
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    for i, A in enumerate(lines):                     # chain segments sharing an end point
        if used[i]:
            continue
        used[i] = True
        pts = list(A["pts"])
        grow = True
        while grow:
            grow = False
            for j, B in enumerate(lines):
                if used[j] or abs(B["z0"] - A["z0"]) > 1e-3:
                    continue
                for front in (False, True):
                    end = pts[0] if front else pts[-1]
                    for kb, other in ((0, -1), (-1, 0)):
                        if key(B["pts"][kb]) == key(end):
                            add = B["pts"][other]
                            pts = [add] + pts if front else pts + [add]
                            used[j] = grow = True
                            break
                    if used[j]:
                        break
                if grow:
                    break
        closed = len(pts) > 3 and key(pts[0]) == key(pts[-1])
        rail_line(main, pts, A["z0"], h, closed=closed)
        rail_line(lod1, pts, A["z0"], h, pickets=False, closed=closed)


def build_ribs(T, main):
    """raised creases + horizontal joints of a relief panel, cut around the dong number on it"""
    for R in T.get("ribs", []):
        w = dict(axis=R["axis"], c=R["c"], s=R["s"])
        cut = []
        for sg in T.get("signs", []):
            if sg["s"] == side_of(w) and abs(sg["c"] - w["c"]) < 0.15:
                half = (len(T["dong"]) * GW + (len(T["dong"]) - 1) * 0.20) * sg["h"] / 2 + 0.15
                cut.append((sg["a"] - half, sg["a"] + half, sg["z"] - 0.15, sg["z"] + sg["h"] + 0.15))
        for zj in R["joints"]:
            cur = R["a0"]
            for q0, q1 in sorted((q[0], q[1]) for q in cut if q[2] < zj < q[3]) + [(R["a1"], R["a1"])]:
                if q0 - cur > 0.1:
                    K.axbox(main, w["axis"], w["c"], w["s"], cur, q0, 0.0, R["jo"], zj - R["jh"] / 2, zj + R["jh"] / 2, R["mat"])
                cur = max(cur, q1)
        for p0, p1 in rib_lines(R):
            pieces = [(p0, p1)]
            for q0, q1, q2, q3 in cut:                 # drop the part of a crease behind the number (z window)
                nxt = []
                for (u0, v0), (u1, v1) in pieces:
                    if max(u0, u1) < q0 or min(u0, u1) > q1 or v1 <= q2 or v0 >= q3:
                        nxt.append(((u0, v0), (u1, v1)))
                        continue
                    f = lambda z: (u0 + (u1 - u0) * (z - v0) / (v1 - v0), z)
                    if q2 - v0 > 0.15:
                        nxt.append(((u0, v0), f(q2)))
                    if v1 - q3 > 0.15:
                        nxt.append((f(q3), (u1, v1)))
                pieces = nxt
            for q in pieces:                           # the two lean directions cross: 5 / 10 mm apart in depth
                o0, o1 = (0.0, R["ro"]) if q[1][0] >= q[0][0] else (0.005, R["ro"] + 0.01)
                seg_prism(main, w, q[0], q[1], R["rw"], o0, o1, R["mat"])


def make_pergtop_painter(c):
    """black pergola grid seen from above: 0.3 m brown-black bars, light grey square openings"""
    import numpy as np
    u, v = c.u % 1.0, c.v % 1.0
    hole = (u > 0.1) & (u < 0.9) & (v > 0.1) & (v < 0.9)
    c.rgb[:] = (60, 54, 51)
    c.rgb[hole] = (150, 152, 156)
    c.grain(amp=2)


def make_diamond_painter(nx, ny):
    """105 west black panel (105_side7, scan west elevation): long diamond relief, lighter edge lines on a dark base;
    the diamonds get shorter toward the top (3 materials with different tile heights)"""
    def painter(c):
        import numpy as np
        u = (c.u * nx) % 1.0
        v = (c.v * ny) % 1.0
        d = np.abs(np.abs(u - 0.5) + np.abs(v - 0.5) - 0.5)
        c.rgb[:] = (52, 50, 58)
        c.rgb[d < 0.03] = (76, 74, 84)
        c.grain(amp=2)
    return painter


def make_relief_painter(c):
    """dark panel wall with a shallow triangle relief (black shafts and top storeys):
    same triangle layout as the wing screen (1.2 m pairs, 1.0 m rows) drawn as lighter edge lines on a dark base"""
    import numpy as np
    u = (c.u * 3.0) % 1.0
    v = (c.v * 4.0) % 1.0
    flip = (np.floor(c.v * 4.0).astype(int) % 2) == 1
    uu = np.where(flip, (u + 0.5) % 1.0, u)
    tri_up = (v > 0.06) & (v < 0.94) & (np.abs(uu - 0.5) < (0.94 - v) * 0.5)
    tri_dn = (v > 0.06) & (v < 0.94) & (np.abs(((uu + 0.5) % 1.0) - 0.5) < (v - 0.06) * 0.5)
    hole = tri_up | tri_dn
    edge = hole & ~(np.roll(hole, 2, 0) & np.roll(hole, -2, 0) & np.roll(hole, 2, 1) & np.roll(hole, -2, 1))
    c.rgb[:] = (50, 52, 60)
    c.rgb[edge] = (72, 74, 84)
    c.grain(amp=2)


def make_sfgrid_painter(c):
    """roof plate underside: same pattern as the triangle screen, but black.
    screen layout (1.2 m pairs, 1.0 m rows, every 2nd row shifted half a pair), black lattice #181a1e,
    triangle openings light grey #969ca6 (photo lattice #131b2a)"""
    import numpy as np
    u = (c.u * 3.0) % 1.0
    v = (c.v * 4.0) % 1.0
    flip = (np.floor(c.v * 4.0).astype(int) % 2) == 1
    uu = np.where(flip, (u + 0.5) % 1.0, u)
    tri_up = (v > 0.12) & (v < 0.88) & (np.abs(uu - 0.5) < (0.88 - v) * 0.5 - 0.06)
    tri_dn = (v > 0.12) & (v < 0.88) & (np.abs(((uu + 0.5) % 1.0) - 0.5) < (v - 0.12) * 0.5 - 0.06)
    hole = tri_up | tri_dn
    c.rgb[:] = (24, 26, 30)
    c.rgb[hole] = (150, 156, 166)
    c.grain(amp=2)


def make_lattice_painter(c):
    """V / diamond lattice screen (103,104,106,108 wing ends): white bars on a see-through field.
    cell 3.0 x 5.8 m (2 floors): two diagonals meeting top and bottom + a horizontal bar per floor"""
    import numpy as np
    u, v = c.u * 3.0, c.v * 5.8
    bar = 0.16
    d1 = np.abs(v - (u / 3.0) * 5.8)                 # diagonal /
    d2 = np.abs(v - (1 - u / 3.0) * 5.8)             # diagonal \
    k = 5.8 / math.hypot(3.0, 5.8)
    solid = (d1 * k < bar / 2) | (d2 * k < bar / 2) | (np.abs(v - 2.9) < bar / 2) | (v < bar / 2) | (v > 5.8 - bar / 2) \
        | (u < bar / 2) | (u > 3.0 - bar / 2)
    c.alpha[~solid] = 0
    c.rgb[~solid] = (60, 60, 64)
    c.grain(amp=2)


def make_lattice104_painter(c):
    """104 wing-end screen (scan back elevation 40 px/m): bars every 2 floors (5.73 m), between them tall narrow V
    pairs, 1.3 m pitch, see-through field"""
    import numpy as np
    W, H, b = 1.3, 5.732, 0.16
    u, v = c.u * W, c.v * H
    x1 = 0.08 + (v / H) * 0.52                       # left stroke leans right going up
    x2 = 1.22 - (v / H) * 0.52
    solid = (np.abs(u - x1) < b / 2) | (np.abs(u - x2) < b / 2) | (v < 0.1) | (v > H - 0.1)
    c.alpha[~solid] = 0
    c.rgb[~solid] = (60, 60, 64)
    c.grain(amp=2)


# ---- 104 wing-end screen, measured strut by strut on the textured scan back elevation (50 px/m):
# horizontal bars (centre z) and per band the struts as (x at band bottom, x at band top). The tilt grades from dense
# triangles at the top to near-vertical bars at the base; bands below 23 m are partly behind trees -> vertical bars on
# the measured 0.81 m grid (estimated).
LAT104_BARS = [131.28, 129.59, 128.44, 127.3, 126.15, 125.01, 123.88, 122.26, 120.62, 117.64, 114.64, 110.44, 106.23, 102.01, 96.3, 90.6, 84.87, 79.17, 73.46, 67.74, 62.03, 56.34, 50.62, 44.92, 39.2, 33.49, 27.79, 22.1, 16.38, 10.68, 4.97]
LAT104_BW = 0.331
LAT104 = [
    (129.73, 130.67, [(15.06, 15.59), (16.45, 15.92), (16.69, 17.21), (18.09, 17.52), (18.31, 18.86), (19.7, 19.2), (19.93, 20.47), (21.33, 20.81), (21.56, 22.11), (22.97, 22.44), (23.18, 23.72)]),
    (128.59, 129.45, [(15.65, 15.11), (15.89, 16.44), (17.27, 16.71), (17.49, 18.09), (18.91, 18.32), (19.12, 19.7), (20.54, 19.96), (20.75, 21.31), (22.12, 21.61), (22.36, 22.94), (23.81, 23.22)]),
    (127.45, 128.29, [(15.08, 15.61), (16.49, 15.9), (16.68, 17.25), (18.09, 17.55), (18.32, 18.87), (19.71, 19.16), (19.94, 20.53), (21.36, 20.77), (21.58, 22.11), (22.96, 22.44), (23.17, 23.74)]),
    (126.29, 127.15, [(15.68, 15.12), (15.85, 16.45), (17.29, 16.74), (17.52, 18.06), (18.91, 18.37), (19.18, 19.7), (20.54, 19.98), (20.77, 21.34), (22.17, 21.62), (22.37, 22.94), (23.77, 23.27)]),
    (125.15, 126.01, [(15.1, 15.64), (16.49, 15.94), (16.72, 17.27), (18.11, 17.56), (18.36, 18.91), (19.71, 19.19), (19.98, 20.48), (21.34, 20.81), (21.58, 22.11), (23.0, 22.43), (23.16, 23.75)]),
    (124.03, 124.87, [(15.65, 15.12), (15.9, 16.47), (17.28, 16.75), (17.52, 18.08), (18.89, 18.38), (19.16, 19.71), (20.55, 19.98), (20.79, 21.34), (22.16, 21.64), (22.39, 22.94), (23.78, 23.26)]),
    (122.41, 123.73, [(15.09, 15.66), (16.48, 15.93), (16.7, 17.27), (18.12, 17.54), (18.32, 18.91), (19.74, 19.17), (19.95, 20.52), (21.37, 20.79), (21.56, 22.15), (22.98, 22.42), (23.18, 23.78)]),
    (120.77, 122.11, [(15.65, 15.07), (15.89, 16.45), (17.3, 16.7), (17.51, 18.09), (18.89, 18.35), (19.12, 19.72), (20.57, 19.98), (20.76, 21.35), (22.18, 21.58), (22.37, 22.96), (23.78, 23.24)]),
    (117.79, 120.47, [(15.07, 15.69), (16.47, 15.88), (16.68, 17.3), (18.13, 17.47), (18.31, 18.94), (19.75, 19.13), (19.95, 20.56), (21.39, 20.72), (21.55, 22.19), (23.0, 22.39), (23.18, 23.8)]),
    (114.79, 117.49, [(15.71, 15.05), (15.87, 16.5), (17.32, 16.69), (17.49, 18.14), (18.94, 18.32), (19.11, 19.75), (20.58, 19.95), (20.73, 21.37), (22.2, 21.56), (22.37, 23.0), (23.82, 23.2)]),
    (110.59, 114.49, [(15.06, 15.68), (16.48, 15.87), (16.68, 17.31), (18.15, 17.5), (18.3, 18.96), (19.77, 19.12), (19.93, 20.58), (21.39, 20.75), (21.55, 22.21), (23.03, 22.37), (23.18, 23.82)]),
    (106.39, 110.29, [(15.7, 15.05), (15.87, 16.5), (17.33, 16.68), (17.5, 18.14), (18.96, 18.31), (19.12, 19.77), (20.56, 19.95), (20.75, 21.38), (22.22, 21.55), (22.38, 23.02), (23.84, 23.18)]),
    (102.17, 106.07, [(15.06, 15.69), (16.52, 15.88), (16.69, 17.32), (18.15, 17.5), (18.32, 18.95), (19.77, 19.13), (19.93, 20.59), (21.39, 20.75), (21.56, 22.22), (23.0, 22.39), (23.19, 23.84)]),
    (96.45, 101.85, [(15.48, 15.05), (16.08, 16.51), (17.09, 16.67), (17.72, 18.14), (18.72, 18.32), (19.33, 19.78), (20.36, 19.93), (20.97, 21.4), (22.0, 21.55), (22.59, 23.02), (23.6, 23.17)]),
    (90.75, 96.15, [(15.16, 15.48), (16.42, 16.08), (16.77, 17.12), (18.05, 17.71), (18.4, 18.75), (19.66, 19.34), (20.03, 20.37), (21.29, 20.97), (21.65, 21.99), (22.93, 22.59), (23.28, 23.6)]),
    (85.03, 90.45, [(15.48, 15.13), (16.08, 16.42), (17.1, 16.77), (17.71, 18.04), (18.72, 18.43), (19.32, 19.67), (20.35, 20.04), (20.93, 21.29), (21.98, 21.66), (22.58, 22.91), (23.61, 23.28)]),
    (79.33, 84.71, [(15.15, 15.49), (16.43, 16.09), (16.78, 17.1), (18.05, 17.7), (18.41, 18.74), (19.67, 19.34), (20.04, 20.36), (21.3, 20.95), (21.65, 21.99), (22.93, 22.57), (23.27, 23.62)]),
    (73.61, 79.01, [(15.48, 15.15), (16.1, 16.43), (17.11, 16.78), (17.72, 18.05), (18.73, 18.41), (19.34, 19.68), (20.37, 20.04), (20.97, 21.29), (21.98, 21.66), (22.59, 22.92), (23.62, 23.27)]),
    (67.89, 73.31, [(15.16, 15.49), (16.42, 16.1), (16.8, 17.11), (18.06, 17.71), (18.41, 18.73), (19.68, 19.34), (20.04, 20.36), (21.29, 20.98), (21.65, 22.0), (22.92, 22.58), (23.27, 23.6)]),
    (62.19, 67.59, [(15.49, 15.14), (16.08, 16.44), (17.12, 16.79), (17.71, 18.06), (18.75, 18.41), (19.33, 19.68), (20.38, 20.04), (20.97, 21.3), (21.99, 21.65), (22.59, 22.94), (23.62, 23.28)]),
    (56.49, 61.87, [(15.27, 15.49), (16.29, 16.09), (16.9, 17.11), (17.93, 17.71), (18.53, 18.75), (19.54, 19.34), (20.14, 20.38), (21.2, 20.97), (21.75, 21.99), (22.81, 22.58), (23.38, 23.61)]),
    (50.77, 56.19, [(15.48, 15.27), (16.09, 16.3), (17.09, 16.91), (17.71, 17.93), (18.74, 18.52), (19.36, 19.55), (20.37, 20.14), (20.96, 21.18), (22.0, 21.77), (22.59, 22.8), (23.61, 23.38), (24.21, 24.37)]),
    (45.07, 50.47, [(15.27, 15.49), (16.29, 16.09), (16.9, 17.11), (17.93, 17.71), (18.53, 18.75), (19.54, 19.34), (20.14, 20.38), (21.2, 20.97), (21.75, 21.99), (22.81, 22.58), (23.38, 23.61)]),
    (39.35, 44.77, [(15.48, 15.29), (16.1, 16.32), (17.13, 16.91), (17.73, 17.92), (18.76, 18.52), (19.36, 19.54), (20.37, 20.15), (20.97, 21.18), (22.0, 21.77), (22.59, 22.81), (23.62, 23.41), (24.23, 24.36)]),
    (33.65, 39.05, [(15.28, 15.5), (16.32, 16.09), (16.9, 17.14), (17.94, 17.71), (18.52, 18.76), (19.55, 19.36), (20.16, 20.38), (21.18, 20.98), (21.77, 22.0), (22.82, 22.59), (23.4, 23.64)]),
    (27.95, 33.33, [(15.48, 15.29), (16.1, 16.32), (17.13, 16.91), (17.73, 17.92), (18.76, 18.52), (19.36, 19.54), (20.37, 20.15), (20.97, 21.18), (22.0, 21.77), (22.59, 22.81), (23.62, 23.41), (24.23, 24.36)]),
    (22.25, 27.63, [(15.4, 15.4), (16.2, 16.2), (17.04, 17.04), (17.85, 17.85), (18.66, 18.66), (19.46, 19.46), (20.27, 20.27), (21.1, 21.1), (21.9, 21.9), (22.71, 22.71), (23.52, 23.52), (24.32, 24.32)]),
    (16.53, 21.95, [(15.4, 15.4), (16.2, 16.2), (17.04, 17.04), (17.85, 17.85), (18.66, 18.66), (19.46, 19.46), (20.27, 20.27), (21.1, 21.1), (21.9, 21.9), (22.71, 22.71), (23.52, 23.52), (24.32, 24.32)]),
    (10.79, 16.23, [(15.4, 15.4), (16.2, 16.2), (17.04, 17.04), (17.85, 17.85), (18.66, 18.66), (19.46, 19.46), (20.27, 20.27), (21.1, 21.1), (21.9, 21.9), (22.71, 22.71), (23.52, 23.52), (24.32, 24.32)]),
    (5.04, 10.6, [(15.4, 15.4), (16.2, 16.2), (17.04, 17.04), (17.85, 17.85), (18.66, 18.66), (19.46, 19.46), (20.27, 20.27), (21.1, 21.1), (21.9, 21.9), (22.71, 22.71), (23.52, 23.52), (24.32, 24.32)]),
    (0.02, 4.9, [(15.4, 15.4), (16.2, 16.2), (17.04, 17.04), (17.85, 17.85), (18.66, 18.66), (19.46, 19.46), (20.27, 20.27), (21.1, 21.1), (21.9, 21.9), (22.71, 22.71), (23.52, 23.52), (24.32, 24.32)]),
]


# wing-end lattice tables per tower: (bar centres, bar height, bands, x limit of mis-read edge struts)


def build_struts(main, lod1, w, a0, a1, so, bars, bands, bw=0.24, sw=0.20, panel=None, text=None, xlim=24.15, sides=False):
    """real-geometry screen in front of wall w (axis y): bars + tilted struts, optional number panel"""
    c, sd = w["c"], w["s"]
    P = lambda x, o, z: (x, c + sd * o, z)
    for zc in bars:
        for mb in (main, lod1):
            K.axbox(mb, w["axis"], c, sd, a0 + 0.3, a1 - 0.3, 0.0, 0.30, zc - bw / 2, zc + bw / 2, "fin")   # ledge on the wall
    for z0, z1, segs in bands:
        if xlim is not None and z1 < 100.0:
            segs = [sg for sg in segs if max(sg) <= xlim]    # mis-read edge struts on the side post
        z0, z1 = z0 + 0.01, z1 - 0.01
        for i, (xb, xt) in enumerate(segs):
            zz0 = z0
            if panel and panel[0] < (xb + xt) / 2 < panel[1] and z0 < panel[3] < z1:
                zz0 = panel[3] + bw / 2 + 0.01          # strut starts on the short bar above the number panel
                xb = xb + (xt - xb) * (zz0 - z0) / (z1 - z0)
            o0, o1 = so - 0.04 + 0.01 * (i % 2), so + 0.06 + 0.01 * (i % 2)   # neighbours 1 cm apart (no coplanar)
            if max(xb, xt) > a1 - 0.33 or min(xb, xt) < a0 + 0.33:
                continue                                # inside the end pilaster
            h = sw / 2
            q = [(xb - h, zz0), (xb + h, zz0), (xt + h, z1), (xt - h, z1)]
            quad_n(main, [P(x, o1, z) for x, z in q], (0, sd, 0), "fin")
            quad_n(main, [P(x, o0, z) for x, z in q], (0, -sd, 0), "fin")
            for (x_0, z_0), (x_1, z_1), sg in ((q[0], q[3], -1), (q[1], q[2], 1)):
                quad_n(main, [P(x_0, o0, z_0), P(x_1, o0, z_1), P(x_1, o1, z_1), P(x_0, o1, z_0)], (sg, 0, 0), "fin")
    if panel:
        x0, x1, pz0, pzb = panel                         # number plate below a short bar
        for mb in (main, lod1):
            K.axbox(mb, w["axis"], c, sd, x0, x1, 0.0, 0.29, pzb - bw / 2, pzb + bw / 2, "fin")
            K.axbox(mb, w["axis"], c, sd, x0, x1, 0.0, so + 0.04, pz0, pzb - bw / 2, "gray4")
            if sides:                                    # white side frames of the plate
                for f0, f1 in ((x0 - 0.12, x0), (x1, x1 + 0.12)):
                    K.axbox(mb, w["axis"], c, sd, f0, f1, 0.03, so + 0.08, pz0, pzb - bw / 2, "fin")
        if text:
            w2 = dict(w, c=c + sd * (so + 0.04))
            hgt = (pzb - bw / 2 - pz0) * 0.5
            dong_number(main, w2, text, (x0 + x1) / 2, pz0 + (pzb - bw / 2 - pz0 - hgt) / 2, hgt, "signw")


# ---- 106 wing-end lattice (R part frame), measured strut by strut on the scan back elevation 50 px/m (scripts/latx106.py):
# top 6 small bands filled with the alternating A/B rows of bands 104.05 / 102.41, the plate band (26.89) gets the 4 middle
# struts of the same-pattern band 38.27; the two bottom bands are behind trees -> vertical bars every 0.81 m (estimated)
LAT106_BARS = [111.23, 110.1, 108.96, 107.81, 106.67, 105.53, 103.91, 102.26, 99.3, 96.32, 92.1, 87.9, 83.69, 78.0, 72.29, 66.59, 60.89, 55.2, 49.51, 43.81, 38.11, 32.41, 26.73, 21.04, 15.35, 9.66, 4.0]
LAT106 = [
    (111.37, 112.31, [(13.048, 13.636), (14.456, 13.856), (14.647, 15.241), (16.078, 15.438), (16.279, 16.873), (17.717, 17.071), (17.887, 18.481), (19.322, 18.698), (19.506, 20.142), (20.951, 20.325), (21.123, 21.753), (22.5, 21.984)]),
    (110.23, 111.09, [(13.663, 13.021), (13.866, 14.414), (15.284, 14.664), (15.458, 16.074), (16.904, 16.264), (17.099, 17.673), (18.523, 17.893), (18.684, 19.324), (20.139, 19.509), (20.35, 20.902), (21.743, 21.145), (21.95, 22.518)]),
    (109.11, 109.97, [(13.048, 13.636), (14.456, 13.856), (14.647, 15.241), (16.078, 15.438), (16.279, 16.873), (17.717, 17.071), (17.887, 18.481), (19.322, 18.698), (19.506, 20.142), (20.951, 20.325), (21.123, 21.753), (22.5, 21.984)]),
    (107.95, 108.81, [(13.663, 13.021), (13.866, 14.414), (15.284, 14.664), (15.458, 16.074), (16.904, 16.264), (17.099, 17.673), (18.523, 17.893), (18.684, 19.324), (20.139, 19.509), (20.35, 20.902), (21.743, 21.145), (21.95, 22.518)]),
    (106.81, 107.67, [(13.048, 13.636), (14.456, 13.856), (14.647, 15.241), (16.078, 15.438), (16.279, 16.873), (17.717, 17.071), (17.887, 18.481), (19.322, 18.698), (19.506, 20.142), (20.951, 20.325), (21.123, 21.753), (22.5, 21.984)]),
    (105.67, 106.53, [(13.663, 13.021), (13.866, 14.414), (15.284, 14.664), (15.458, 16.074), (16.904, 16.264), (17.099, 17.673), (18.523, 17.893), (18.684, 19.324), (20.139, 19.509), (20.35, 20.902), (21.743, 21.145), (21.95, 22.518)]),
    (104.05, 105.39, [(13.048, 13.636), (14.456, 13.856), (14.647, 15.241), (16.078, 15.438), (16.279, 16.873), (17.717, 17.071), (17.887, 18.481), (19.322, 18.698), (19.506, 20.142), (20.951, 20.325), (21.123, 21.753), (22.5, 21.984)]),
    (102.41, 103.77, [(13.663, 13.021), (13.866, 14.414), (15.284, 14.664), (15.458, 16.074), (16.904, 16.264), (17.099, 17.673), (18.523, 17.893), (18.684, 19.324), (20.139, 19.509), (20.35, 20.902), (21.743, 21.145), (21.95, 22.518)]),
    (99.45, 102.11, [(13.03, 13.634), (14.458, 13.838), (14.66, 15.244), (16.102, 15.446), (16.271, 16.865), (17.714, 17.078), (17.879, 18.525), (19.339, 18.697), (19.495, 20.145), (20.94, 20.32), (21.121, 21.767), (22.543, 21.949)]),
    (96.47, 99.15, [(13.651, 13.025), (13.816, 14.46), (15.276, 14.652), (15.461, 16.071), (16.886, 16.262), (17.072, 17.712), (18.54, 17.9), (18.703, 19.349), (20.168, 19.512), (20.326, 20.966), (21.779, 21.133), (21.975, 22.537)]),
    (92.25, 96.17, [(13.016, 13.652), (14.488, 13.832), (14.642, 15.278), (16.103, 15.473), (16.268, 16.904), (17.74, 17.072), (17.889, 18.539), (19.348, 18.712), (19.499, 20.177), (20.982, 20.342), (21.129, 21.811), (22.545, 22.003)]),
    (88.05, 91.95, [(13.665, 13.019), (13.831, 14.445), (15.278, 14.642), (15.426, 16.078), (16.911, 16.245), (17.054, 17.706), (18.524, 17.888), (18.684, 19.324), (20.168, 19.516), (20.318, 20.954), (21.788, 21.132), (21.981, 22.539)]),
    (83.85, 87.75, [(13.005, 13.651), (14.467, 13.837), (14.63, 15.27), (16.098, 15.462), (16.255, 16.881), (17.725, 17.075), (17.863, 18.529), (19.382, 18.694), (19.521, 20.151), (21.005, 20.323), (21.136, 21.808), (22.55, 21.982)]),
    (78.17, 83.53, [(13.66, 13.04), (13.837, 14.467), (15.294, 14.67), (15.471, 16.065), (16.892, 16.292), (17.059, 17.721), (18.529, 17.899), (18.688, 19.34), (20.125, 19.547), (20.313, 20.955), (21.758, 21.158), (21.969, 22.531)]),
    (72.45, 77.83, [(13.011, 13.641), (14.46, 13.84), (14.628, 15.268), (16.088, 15.468), (16.258, 16.898), (17.715, 17.069), (17.865, 18.527), (19.332, 18.696), (19.488, 20.128), (20.946, 20.322), (21.115, 21.761), (22.528, 21.96)]),
    (66.75, 72.13, [(13.653, 13.043), (13.813, 14.459), (15.268, 14.668), (15.429, 16.079), (16.896, 16.276), (17.035, 17.697), (18.525, 17.895), (18.667, 19.313), (20.14, 19.5), (20.299, 20.925), (21.762, 21.142), (21.926, 22.526)]),
    (61.05, 66.43, [(13.023, 13.621), (14.44, 13.836), (14.638, 15.262), (16.067, 15.453), (16.242, 16.882), (17.702, 17.05), (17.871, 18.497), (19.332, 18.68), (19.491, 20.117), (20.945, 20.299), (21.115, 21.745), (22.522, 21.934)]),
    (55.37, 60.73, [(13.481, 13.027), (13.955, 14.461), (15.111, 14.617), (15.584, 16.08), (16.739, 16.233), (17.211, 17.685), (18.353, 17.863), (18.819, 19.325), (19.965, 19.491), (20.446, 20.926), (21.583, 21.125), (22.067, 22.525)]),
    (49.67, 55.03, [(13.02, 13.468), (14.452, 13.952), (14.615, 15.105), (16.074, 15.59), (16.215, 16.737), (17.685, 17.211), (17.871, 18.377), (19.321, 18.831), (19.491, 19.965), (20.94, 20.456), (21.102, 21.618), (22.52, 22.108)]),
    (43.97, 49.35, [(13.481, 13.027), (13.963, 14.453), (15.131, 14.621), (15.579, 16.089), (16.74, 16.256), (17.213, 17.703), (18.354, 17.874), (18.817, 19.327), (19.969, 19.495), (20.434, 20.95), (21.581, 21.123), (22.073, 22.527)]),
    (38.27, 43.65, [(13.016, 13.48), (14.46, 13.976), (14.609, 15.103), (16.069, 15.579), (16.238, 16.738), (17.7, 17.216), (17.856, 18.372), (19.332, 18.832), (19.495, 19.969), (20.939, 20.481), (21.106, 21.61), (22.531, 22.093)]),
    (32.57, 37.95, [(13.483, 13.029), (13.956, 14.456), (15.142, 14.606), (15.578, 16.074), (16.742, 16.246), (17.212, 17.712), (18.365, 17.859), (18.822, 19.318), (19.983, 19.489), (20.414, 20.966), (21.587, 21.109), (22.066, 22.53)]),
    (26.89, 32.25, [(13.018, 13.482), (14.458, 13.958), (14.613, 15.119), (16.067, 15.577), (16.238, 16.738), (17.7, 17.216), (17.856, 18.372), (19.332, 18.832), (19.467, 19.989), (20.929, 20.475), (21.121, 21.591), (22.511, 22.109)]),
    (21.19, 26.57, [(13.49, 13.026), (13.966, 14.45), (15.137, 14.607), (15.579, 16.073), (16.758, 16.222), (17.202, 17.69), (18.349, 17.875), (18.814, 19.314), (19.973, 19.499), (20.439, 20.945), (21.586, 21.122), (22.058, 22.542)]),
    (15.51, 20.89, [(13.005, 13.475), (14.473, 13.931), (14.6, 15.116), (16.064, 15.58), (16.236, 16.736), (17.715, 17.189), (17.863, 18.373), (19.341, 18.831), (19.502, 19.966), (20.961, 20.451), (21.105, 21.599), (22.53, 22.098)]),
    (9.81, 15.19, [(13.485, 13.027), (13.961, 14.435), (15.124, 14.624), (15.57, 16.054), (16.736, 16.252), (17.207, 17.681), (18.359, 17.869), (18.815, 19.305), (19.966, 19.502), (20.425, 20.931), (21.585, 21.131), (22.05, 22.53)]),
    (4.11, 9.51, [(13.35, 13.35), (14.16, 14.16), (14.97, 14.97), (15.78, 15.78), (16.59, 16.59), (17.4, 17.4), (18.21, 18.21), (19.02, 19.02), (19.83, 19.83), (20.64, 20.64), (21.45, 21.45), (22.26, 22.26)]),
    (0.02, 3.85, [(13.35, 13.35), (14.16, 14.16), (14.97, 14.97), (15.78, 15.78), (16.59, 16.59), (17.4, 17.4), (18.21, 18.21), (19.02, 19.02), (19.83, 19.83), (20.64, 20.64), (21.45, 21.45), (22.26, 22.26)]),
]


# ---- 107 wing-end lattice, measured on the scan back elevation 50 px/m (scripts/latx107.py); bands the scan read lost
# (number plate, trees at the bottom, short top bands) are filled with the same alternating pattern band
LAT107_BARS = [92.98, 91.58, 90.44, 89.29, 88.16, 87.01, 85.86, 84.24, 82.62, 79.64, 76.66, 72.46, 68.25, 64.06, 58.36, 52.68, 46.98, 41.29, 35.58, 29.92, 24.22, 18.52, 12.83, 7.11, 1.45]
LAT107 = [
    (91.74, 92.58, [(-21.382, -20.902), (-20.083, -20.629), (-19.799, -19.289), (-18.482, -19.034), (-18.204, -17.694), (-16.913, -17.383), (-16.629, -16.067), (-15.271, -15.777), (-14.977, -14.487), (-13.672, -14.176), (-13.391, -12.849), (-12.048, -12.564)]),
    (90.6, 91.42, [(-20.873, -21.431), (-20.645, -20.047), (-19.271, -19.817), (-18.995, -18.453), (-17.65, -18.198), (-17.411, -16.849), (-16.046, -16.618), (-15.81, -15.274), (-14.402, -15.045), (-14.229, -13.635), (-12.835, -13.391), (-12.607, -12.045)]),
    (89.44, 90.28, [(-21.442, -20.89), (-20.026, -20.646), (-19.849, -19.295), (-18.405, -19.022), (-18.245, -17.647), (-16.812, -17.4), (-16.647, -16.053), (-15.228, -15.796), (-15.053, -14.439), (-13.581, -14.191), (-13.452, -12.832), (-12.028, -12.564)]),
    (88.32, 89.14, [(-20.873, -21.431), (-20.645, -20.047), (-19.271, -19.817), (-18.995, -18.453), (-17.65, -18.198), (-17.411, -16.849), (-16.046, -16.618), (-15.81, -15.274), (-14.402, -15.045), (-14.229, -13.635), (-12.835, -13.391), (-12.607, -12.045)]),
    (87.16, 88.0, [(-21.442, -20.89), (-20.026, -20.646), (-19.849, -19.295), (-18.405, -19.022), (-18.245, -17.647), (-16.812, -17.4), (-16.647, -16.053), (-15.228, -15.796), (-15.053, -14.439), (-13.581, -14.191), (-13.452, -12.832), (-12.028, -12.564)]),
    (86.02, 86.86, [(-20.874, -21.41), (-20.654, -20.118), (-19.283, -19.777), (-19.043, -18.485), (-17.676, -18.176), (-17.408, -16.892), (-16.052, -16.552), (-15.82, -15.252), (-14.424, -14.944), (-14.203, -13.677), (-12.809, -13.335), (-12.605, -12.083)]),
    (84.4, 85.7, [(-21.442, -20.89), (-20.026, -20.646), (-19.849, -19.295), (-18.405, -19.022), (-18.245, -17.647), (-16.812, -17.4), (-16.647, -16.053), (-15.228, -15.796), (-15.053, -14.439), (-13.581, -14.191), (-13.452, -12.832), (-12.028, -12.564)]),
    (82.78, 84.08, [(-20.873, -21.431), (-20.645, -20.047), (-19.271, -19.817), (-18.995, -18.453), (-17.65, -18.198), (-17.411, -16.849), (-16.046, -16.618), (-15.81, -15.274), (-14.402, -15.045), (-14.229, -13.635), (-12.835, -13.391), (-12.607, -12.045)]),
    (79.8, 82.46, [(-21.441, -20.847), (-20.032, -20.668), (-19.845, -19.235), (-18.427, -19.057), (-18.238, -17.65), (-16.819, -17.445), (-16.644, -16.024), (-15.215, -15.825), (-15.071, -14.405), (-13.604, -14.244), (-13.415, -12.821), (-12.025, -12.587)]),
    (76.82, 79.48, [(-20.847, -21.477), (-20.639, -20.045), (-19.237, -19.851), (-19.049, -18.439), (-17.621, -18.231), (-17.465, -16.835), (-16.005, -16.635), (-15.841, -15.231), (-14.393, -15.023), (-14.244, -13.624), (-12.803, -13.413), (-12.631, -12.021)]),
    (72.62, 76.5, [(-21.449, -20.835), (-20.046, -20.666), (-19.843, -19.233), (-18.436, -19.06), (-18.247, -17.633), (-16.815, -17.445), (-16.655, -16.025), (-15.227, -15.841), (-15.05, -14.414), (-13.61, -14.23), (-13.421, -12.823), (-12.027, -12.605)]),
    (68.42, 72.3, [(-20.836, -21.476), (-20.676, -20.02), (-19.222, -19.858), (-19.044, -18.444), (-17.627, -18.237), (-17.457, -16.811), (-16.002, -16.638), (-15.847, -15.217), (-14.387, -15.049), (-14.246, -13.606), (-12.798, -13.418), (-12.64, -12.004)]),
    (64.22, 68.08, [(-21.449, -20.851), (-20.05, -20.654), (-19.855, -19.241), (-18.442, -19.062), (-18.258, -17.638), (-16.826, -17.446), (-16.658, -16.022), (-15.228, -15.848), (-15.048, -14.424), (-13.62, -14.224), (-13.435, -12.825), (-12.029, -12.607)]),
    (58.52, 63.9, [(-21.002, -21.461), (-20.488, -20.04), (-19.409, -19.863), (-18.884, -18.436), (-17.796, -18.26), (-17.263, -16.825), (-16.201, -16.639), (-15.676, -15.212), (-14.599, -15.041), (-14.069, -13.611), (-12.986, -13.434), (-12.472, -12.024)]),
    (52.84, 58.2, [(-21.459, -21.021), (-20.041, -20.495), (-19.883, -19.409), (-18.413, -18.903), (-18.265, -17.807), (-16.804, -17.288), (-16.66, -16.192), (-15.204, -15.684), (-15.039, -14.581), (-13.619, -14.057), (-13.442, -12.978), (-12.017, -12.439)]),
    (47.14, 52.52, [(-21.027, -21.465), (-20.497, -20.043), (-19.415, -19.853), (-18.879, -18.421), (-17.803, -18.281), (-17.284, -16.82), (-16.209, -16.635), (-15.677, -15.203), (-14.596, -15.044), (-14.081, -13.611), (-12.979, -13.437), (-12.466, -12.018)]),
    (41.46, 46.82, [(-21.461, -21.039), (-20.048, -20.512), (-19.878, -19.414), (-18.459, -18.885), (-18.256, -17.828), (-16.831, -17.285), (-16.658, -16.206), (-15.219, -15.689), (-15.061, -14.603), (-13.606, -14.074), (-13.441, -12.999), (-12.003, -12.457)]),
    (35.74, 41.12, [(-21.035, -21.477), (-20.508, -20.06), (-19.413, -19.887), (-18.901, -18.443), (-17.818, -18.282), (-17.289, -16.847), (-16.217, -16.671), (-15.685, -15.227), (-14.596, -15.064), (-14.084, -13.636), (-12.982, -13.462), (-12.469, -12.031)]),
    (30.08, 35.42, [(-21.461, -21.039), (-20.048, -20.512), (-19.878, -19.414), (-18.459, -18.885), (-18.256, -17.828), (-16.831, -17.285), (-16.658, -16.206), (-15.219, -15.689), (-15.061, -14.603), (-13.606, -14.074), (-13.441, -12.999), (-12.003, -12.457)]),
    (24.38, 29.76, [(-21.05, -21.498), (-20.527, -20.069), (-19.453, -19.895), (-18.92, -18.472), (-17.832, -18.3), (-17.323, -16.849), (-16.236, -16.684), (-15.709, -15.235), (-14.606, -15.086), (-14.096, -13.648), (-13.009, -13.479), (-12.504, -12.024)]),
    (18.68, 24.06, [(-21.48, -21.068), (-20.072, -20.536), (-19.903, -19.445), (-18.467, -18.925), (-18.289, -17.847), (-16.848, -17.316), (-16.683, -16.225), (-15.242, -15.71), (-15.073, -14.615), (-13.643, -14.097), (-13.461, -13.003), (-12.04, -12.472)]),
    (12.98, 18.36, [(-21.039, -21.493), (-20.535, -20.077), (-19.439, -19.913), (-18.925, -18.467), (-17.836, -18.304), (-17.321, -16.847), (-16.234, -16.682), (-15.711, -15.237), (-14.62, -15.068), (-14.125, -13.615), (-13.014, -13.466), (-12.487, -12.029)]),
    (7.26, 12.68, [(-21.48, -21.068), (-20.072, -20.536), (-19.903, -19.445), (-18.467, -18.925), (-18.289, -17.847), (-16.848, -17.316), (-16.683, -16.225), (-15.242, -15.71), (-15.073, -14.615), (-13.643, -14.097), (-13.461, -13.003), (-12.04, -12.472)]),
    (1.58, 6.96, [(-21.039, -21.493), (-20.535, -20.077), (-19.439, -19.913), (-18.925, -18.467), (-17.836, -18.304), (-17.321, -16.847), (-16.234, -16.682), (-15.711, -15.237), (-14.62, -15.068), (-14.125, -13.615), (-13.014, -13.466), (-12.487, -12.029)]),
]


# ---- 108 wing-end lattice (scripts/latx108.py, 50 px/m): steep V rows, then near-vertical bars every 0.815 m below z 24
# (partly behind trees, estimated); plate band and lost bands filled with the alternating pattern
LAT108_BARS = [78.39, 77.05, 75.87, 74.68, 73.04, 71.39, 68.39, 65.4, 61.38, 57.36, 51.65, 45.94, 40.21, 34.48, 28.77, 23.03, 17.34, 11.62, 5.86]
LAT108 = [
    (77.19, 78.09, [(9.65, 10.27), (11.09, 10.422), (11.298, 11.882), (12.734, 12.162), (12.972, 13.524), (14.344, 13.796), (14.605, 15.183), (15.979, 15.453), (16.249, 16.827), (17.646, 17.094), (17.887, 18.481), (19.305, 18.747), (19.532, 20.1), (20.919, 20.409)]),
    (76.01, 76.91, [(10.26, 9.642), (10.468, 11.068), (11.899, 11.325), (12.118, 12.702), (13.539, 12.981), (13.761, 14.371), (15.156, 14.64), (15.417, 16.031), (16.82, 16.284), (17.033, 17.679), (18.484, 17.916), (18.658, 19.29), (20.142, 19.554), (20.322, 20.906)]),
    (74.81, 75.73, [(9.65, 10.27), (11.09, 10.422), (11.298, 11.882), (12.734, 12.162), (12.972, 13.524), (14.344, 13.796), (14.605, 15.183), (15.979, 15.453), (16.249, 16.827), (17.646, 17.094), (17.887, 18.481), (19.305, 18.747), (19.532, 20.1), (20.919, 20.409)]),
    (73.19, 74.55, [(10.237, 9.639), (10.499, 11.113), (11.887, 11.313), (12.101, 12.763), (13.534, 12.95), (13.774, 14.378), (15.195, 14.585), (15.379, 16.021), (16.807, 16.245), (17.052, 17.672), (18.463, 17.901), (18.691, 19.317), (20.111, 19.559), (20.318, 20.918)]),
    (71.51, 72.89, [(9.65, 10.27), (11.09, 10.422), (11.298, 11.882), (12.734, 12.162), (12.972, 13.524), (14.344, 13.796), (14.605, 15.183), (15.979, 15.453), (16.249, 16.827), (17.646, 17.094), (17.887, 18.481), (19.305, 18.747), (19.532, 20.1), (20.919, 20.409)]),
    (68.51, 71.27, [(10.264, 9.608), (10.457, 11.115), (11.912, 11.26), (12.108, 12.74), (13.557, 12.911), (13.746, 14.382), (15.19, 14.55), (15.386, 16.022), (16.839, 16.213), (17.018, 17.654), (18.472, 17.852), (18.642, 19.334), (20.154, 19.486), (20.285, 20.947)]),
    (65.53, 68.27, [(9.65, 10.27), (11.09, 10.422), (11.298, 11.882), (12.734, 12.162), (12.972, 13.524), (14.344, 13.796), (14.605, 15.183), (15.979, 15.453), (16.249, 16.827), (17.646, 17.094), (17.887, 18.481), (19.305, 18.747), (19.532, 20.1), (20.919, 20.409)]),
    (61.51, 65.27, [(10.25, 9.614), (10.439, 11.101), (11.932, 11.26), (12.085, 12.731), (13.556, 12.884), (13.728, 14.4), (15.197, 14.571), (15.378, 16.018), (16.846, 16.206), (16.988, 17.692), (18.5, 17.844), (18.649, 19.331), (20.15, 19.478), (20.284, 20.936)]),
    (57.49, 61.25, [(9.609, 10.303), (11.094, 10.422), (11.258, 11.918), (12.738, 12.062), (12.897, 13.559), (14.387, 13.725), (14.541, 15.203), (16.016, 15.376), (16.182, 16.854), (17.659, 17.033), (17.83, 18.486), (19.318, 18.662), (19.47, 20.122), (20.933, 20.319)]),
    (51.77, 57.23, [(10.034, 9.622), (10.643, 11.081), (11.664, 11.272), (12.297, 12.735), (13.321, 12.903), (13.931, 14.385), (14.988, 14.524), (15.596, 16.008), (16.622, 16.174), (17.228, 17.676), (18.251, 17.829), (18.872, 19.316), (19.896, 19.5), (20.508, 20.936)]),
    (46.05, 51.53, [(9.816, 10.056), (10.876, 10.648), (11.474, 11.698), (12.528, 12.288), (13.108, 13.332), (14.151, 13.937), (14.748, 14.992), (15.797, 15.563), (16.401, 16.635), (17.45, 17.226), (18.061, 18.259), (19.102, 18.874), (19.701, 19.915), (20.743, 20.529)]),
    (40.31, 45.83, [(10.056, 9.816), (10.648, 10.876), (11.698, 11.474), (12.288, 12.528), (13.332, 13.108), (13.937, 14.151), (14.992, 14.748), (15.563, 15.797), (16.635, 16.401), (17.226, 17.45), (18.259, 18.061), (18.874, 19.102), (19.915, 19.701), (20.529, 20.743)]),
    (34.59, 40.11, [(9.816, 10.056), (10.876, 10.648), (11.474, 11.698), (12.528, 12.288), (13.108, 13.332), (14.151, 13.937), (14.748, 14.992), (15.797, 15.563), (16.401, 16.635), (17.45, 17.226), (18.061, 18.259), (19.102, 18.874), (19.701, 19.915), (20.743, 20.529)]),
    (28.89, 34.37, [(10.056, 9.816), (10.648, 10.876), (11.698, 11.474), (12.288, 12.528), (13.332, 13.108), (13.937, 14.151), (14.992, 14.748), (15.563, 15.797), (16.635, 16.401), (17.226, 17.45), (18.259, 18.061), (18.874, 19.102), (19.915, 19.701), (20.529, 20.743)]),
    (23.13, 28.65, [(9.96, 9.96), (10.78, 10.78), (11.59, 11.59), (12.41, 12.41), (13.22, 13.22), (14.04, 14.04), (14.85, 14.85), (15.67, 15.67), (16.48, 16.48), (17.3, 17.3), (18.11, 18.11), (18.93, 18.93), (19.74, 19.74), (20.55, 20.55)]),
    (17.43, 22.93, [(9.96, 9.96), (10.78, 10.78), (11.59, 11.59), (12.41, 12.41), (13.22, 13.22), (14.04, 14.04), (14.85, 14.85), (15.67, 15.67), (16.48, 16.48), (17.3, 17.3), (18.11, 18.11), (18.93, 18.93), (19.74, 19.74), (20.55, 20.55)]),
    (11.69, 17.25, [(9.96, 9.96), (10.78, 10.78), (11.59, 11.59), (12.41, 12.41), (13.22, 13.22), (14.04, 14.04), (14.85, 14.85), (15.67, 15.67), (16.48, 16.48), (17.3, 17.3), (18.11, 18.11), (18.93, 18.93), (19.74, 19.74), (20.55, 20.55)]),
    (5.99, 11.49, [(9.96, 9.96), (10.78, 10.78), (11.59, 11.59), (12.41, 12.41), (13.22, 13.22), (14.04, 14.04), (14.85, 14.85), (15.67, 15.67), (16.48, 16.48), (17.3, 17.3), (18.11, 18.11), (18.93, 18.93), (19.74, 19.74), (20.55, 20.55)]),
    (0.02, 5.73, [(9.96, 9.96), (10.78, 10.78), (11.59, 11.59), (12.41, 12.41), (13.22, 13.22), (14.04, 14.04), (14.85, 14.85), (15.67, 15.67), (16.48, 16.48), (17.3, 17.3), (18.11, 18.11), (18.93, 18.93), (19.74, 19.74), (20.55, 20.55)]),
]


LAT_TABLES = {"104": (LAT104_BARS, 0.24, LAT104, 24.15),
              "106": (LAT106_BARS, 0.25, LAT106, None), "107": (LAT107_BARS, 0.26, LAT107, None),
              "108": (LAT108_BARS, 0.25, LAT108, None)}


def build_crowns(T, main, lod1):
    """open white portal frame on a wing roof: 4 corner posts + 4 top beams (photos: 103/104/106/108)"""
    t = 0.45
    for x0, x1, y0, y1, z0, hh in T.get("crowns", []):
        z1 = z0 + hh
        for mb in (main, lod1):
            for px, py in ((x0, y0), (x1 - t, y0), (x0, y1 - t), (x1 - t, y1 - t)):
                mb.box(px, px + t, py, py + t, z0, z1 - t, "roofw", skip=("bottom", "top"))
            mb.box(x0, x1, y0, y0 + t, z1 - t, z1, "roofw")
            mb.box(x0, x1, y1 - t, y1, z1 - t, z1, "roofw")
            mb.box(x0, x0 + t, y0 + t, y1 - t, z1 - t, z1, "roofw", skip=("front", "back"))
            mb.box(x1 - t, x1, y0 + t, y1 - t, z1 - t, z1, "roofw", skip=("front", "back"))


def slope_bar(mb, xa, za, xb, zb, y0, y1, h, region):
    """bar along x from (xa, za) to (xb, zb), y0..y1 wide, h tall (top at z): 4 long faces + 2 ends"""
    P = lambda x, y, z: (x, y, z)
    lo_a, lo_b = za - h, zb - h
    quad_n(mb, [P(xa, y0, lo_a), P(xb, y0, lo_b), P(xb, y0, zb), P(xa, y0, za)], (0, -1, 0), region)
    quad_n(mb, [P(xa, y1, lo_a), P(xb, y1, lo_b), P(xb, y1, zb), P(xa, y1, za)], (0, 1, 0), region)
    nz = 1 if True else 0
    quad_n(mb, [P(xa, y0, za), P(xb, y0, zb), P(xb, y1, zb), P(xa, y1, za)], (-(zb - za), 0, abs(xb - xa)), region)
    quad_n(mb, [P(xa, y0, lo_a), P(xb, y0, lo_b), P(xb, y1, lo_b), P(xa, y1, lo_a)], ((zb - za), 0, -abs(xb - xa)), region)
    for x, z, sg in ((xa, za, -1 if xa < xb else 1), (xb, zb, 1 if xa < xb else -1)):
        quad_n(mb, [P(x, y0, z - h), P(x, y1, z - h), P(x, y1, z), P(x, y0, z)], (sg, 0, 0), region)


def build_stair(main, S):
    """open steel roof stair along x (x0 at z0 -> x1 at z1): steel treads 0.18 rise, two side stringers, handrail posts
    + sloped top rail on both sides, optional top landing (x, y box at z1) with a rail and one support post"""
    x0, x1, y0, y1, z0, z1 = S["x0"], S["x1"], S["y0"], S["y1"], S["z0"], S["z1"]
    n = max(2, math.ceil((z1 - z0) / 0.18))
    dx = (x1 - x0) / n
    for i in range(n):
        xa, xb = sorted((x0 + dx * i, x0 + dx * (i + 1)))
        zt = z0 + (z1 - z0) * (i + 1) / n
        main.box(xa + 0.005, xb - 0.005, y0 + 0.07, y1 - 0.07, zt - 0.035, zt, "louver")
    for ya, yb in ((y0, y0 + 0.06), (y1 - 0.06, y1)):
        slope_bar(main, x0, z0 + 0.25, x1, z1 + 0.05, ya, yb, 0.3, "louver")                    # stringer
        ym0, ym1 = ya + 0.01, yb - 0.01
        k = max(2, round(abs(x1 - x0) / 1.2))
        for i in range(k + 1):                                                                  # rail posts
            x = x0 + (x1 - x0) * i / k
            z = z0 + (z1 - z0) * i / k
            xa_ = min(max(x - 0.025, min(x0, x1) + 0.06), max(x0, x1) - 0.11)    # clear of the stringer end faces
            main.box(xa_, xa_ + 0.05, ym0, ym1, z + 0.05, z + 0.95, "louver", skip=("bottom",))
        slope_bar(main, x0, z0 + 1.0, x1, z1 + 1.0, ya - 0.01, yb + 0.01, 0.05, "louver")       # handrail
    L = S.get("landing")
    if L:
        lx0, lx1, ly0, ly1 = L
        main.box(lx0, lx1, ly0, ly1, z1 - 0.12, z1, "louver")
        main.box(lx0, lx0 + 0.05, ly0, ly1, z1, z1 + 1.0, "louver", skip=("bottom",))           # landing rails
        main.box(lx0 + 0.05, lx1, ly0, ly0 + 0.05, z1, z1 + 1.0, "louver", skip=("bottom",))
        main.box(lx0 + 0.02, lx0 + 0.14, ly0 + 0.02, ly0 + 0.14, z0, z1 - 0.12, "louver", skip=("bottom", "top"))   # post


def build_crown_frames(T, main, lod1):
    """open white crown frames above a roof: beams = plates whose top follows ztop(y), posts from z0 to the beam"""
    for F in T.get("crown_frames", []):
        bh = F["beam"]
        zt = (lambda y, f=F["ztop"]: f(y)) if F.get("ztop") else (lambda y: 0.0)
        zf = (lambda x, y, f=F["ztx"]: f(x)) if F.get("ztx") else (lambda x, y, f=zt: f(y))   # top along x (sloped beam)
        for x0, x1, y0, y1 in F["beams"]:
            P = [(x0, y0, zf(x0, y0)), (x1, y0, zf(x1, y0)), (x1, y1, zf(x1, y1)), (x0, y1, zf(x0, y1))]
            plate(main, P, bh, F.get("mat", "fin"))
            plate(lod1, P, bh, F.get("mat", "fin"))
        for q in F.get("quads", []):              # plates with a slanted edge (corners counter-clockwise from above)
            P = [(x, y, zf(x, y)) for x, y in q]
            plate(main, P, bh, F.get("mat", "fin"))
            plate(lod1, P, bh, F.get("mat", "fin"))
        for x0, x1, y0, y1 in F["posts"]:
            zb = min(zf(x0, y0), zf(x1, y0), zf(x0, y1), zf(x1, y1)) - bh
            pz0 = F.get("posts_z0", F["z0"])
            for q0, q1, r0, r1, utop in T.get("low_strips", []):   # the parapet under the post became a railing upstand:
                # any plan overlap, not only the centre: deep posts / fins only partly on the strip were left hanging
                # at the parapet top with a gap above the upstand (front crown frames)
                if x0 < q1 - 1e-3 and x1 > q0 + 1e-3 and y0 < r1 - 1e-3 and y1 > r0 + 1e-3 and pz0 > utop + 1e-3 and not any(
                        x0 < b[1] - 1e-3 and x1 > b[0] + 1e-3 and y0 < b[3] - 1e-3 and y1 > b[2] + 1e-3 for b in T.get("full_strips", [])):
                    pz0 = utop
            for mb in (main, lod1):
                # bottom only where nothing is under the post (standing out past the wall, 106): an open bottom there is
                # see-through from below; on a roof / beam a bottom face would be coplanar with other faces
                hb = T.get("hf_blocks", [])
                sup = [max([b[4] for b in hb if b[0] <= x_ <= b[1] and b[2] <= y_ <= b[3]] or [0.0])
                       for x_ in (x0 + 0.01, (x0 + x1) / 2, x1 - 0.01) for y_ in (y0 + 0.01, (y0 + y1) / 2, y1 - 0.01)]
                open_below = min(sup) < pz0 - 0.05
                mb.box(x0, x1, y0, y1, pz0, zb, F.get("mat", "fin"), skip=("top",) if open_below else ("bottom", "top"))
        if F.get("deck"):                          # closed plate: tiled top over the whole plate
            for x0, x1, y0, y1 in F["beams"]:
                # 2 cm in from the plate edges: flush, its underside showed as a 1 cm see-through line from below
                K.floor_quad(main, x0 + 0.02, x1 - 0.02, y0 + 0.02, y1 - 0.02, zt(y0) + 0.01, F["deck"])
        if F.get("top_mat"):                       # open grid on the plate top (black frame with square openings)
            for x0, x1, y0, y1 in F["beams"]:
                K.floor_quad(main, x0 + 0.3, x1 - 0.3, y0 + 0.3, y1 - 0.3, zt(y0) + 0.01, F["top_mat"])


def rotate_mb(mb, deg, dx, dy):
    """rotate a builder's vertices about z (origin) then move: part plan frame -> tower frame"""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    mb.verts = [(ca * x - sa * y + dx, sa * x + ca * y + dy, z) for x, y, z in mb.verts]


def rotate_wins(W, deg, dx, dy):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    f = lambda p: (ca * p[0] - sa * p[1] + dx, sa * p[0] + ca * p[1] + dy, p[2])
    for it in W.items:
        it["pts"] = [f(p) for p in it["pts"]]
        it["pts2"] = [f(p) for p in it["pts2"]]


def build(A, T):
    """tower = one or more parts (each in its own plan frame, rotated into the tower frame)"""
    out = dict(main=K.MeshBuilder(A), lod1=K.MeshBuilder(A, split_tiles=False), lod2=K.MeshBuilder(A, split_tiles=False),
               gls=K.MeshBuilder(A), lod1_gls=K.MeshBuilder(A))
    wins = K.WindowSet()
    for pi, P in enumerate(T.get("parts", [dict()])):
        TP = dict(T, **P)
        TP["roof_rails"] = [r for r in ROOF_RAILS.get(T["dong"], []) if r[0] == pi]
        res = build_part(A, TP, unit0=pi * 100000)
        rot, (dx, dy) = P.get("rot", 0.0), P.get("move", (0.0, 0.0))
        for k in out:
            if rot or dx or dy:
                rotate_mb(res[k], rot, dx, dy)
            out[k].merge(res[k])
        if rot or dx or dy:
            rotate_wins(res["windows"], rot, dx, dy)
        wins.items += res["windows"].items
    out["windows"] = wins
    if MIRROR_Y:
        mirror_y(out, wins)
    return out


def mirror_y(out, wins):
    """reflect the whole tower front <-> back (y -> ymin + ymax - y) and keep the faces facing outward:
    quad vertex order (a, b, c, d) -> (b, a, d, c) with the UVs unchanged (texture still reads left to right from outside).
    Used when the scan -> generator frame turned out to be a mirror image of the real building (photos vs model)."""
    ys = [v[1] for v in out["main"].verts]
    k = min(ys) + max(ys)
    for mb in out.values():
        if hasattr(mb, "verts"):
            mb.verts = [(x, k - y, z) for x, y, z in mb.verts]
            mb.faces = [(f[1], f[0], f[3], f[2]) if len(f) == 4 else tuple(reversed(f)) for f in mb.faces]
    for it in wins.items:
        for key in ("pts", "pts2"):
            q = [(x, k - y, z) for x, y, z in it[key]]
            it[key] = [q[1], q[0], q[3], q[2]]


STAIR_WIN = {"A": (0.0, 0.85), "B": (1.4, 2.25)}     # stair windows sit on the landings, not on the room-window line (scan)


def expand_slots(T):
    """a zone's slots=[(a0, a1, kind)] -> a darker paint stripe with small windows at the stair landing height"""
    out = []
    for zn in T["zones"]:
        sl = zn.get("slots")
        if not sl:
            out.append(zn)
            continue
        out.append(dict(zn, slots=None))
        for i, q in enumerate(sl):
            # q = (a0, a1, kind "A"/"B" or measured (sill, head)[, (first, last floor)[, [(z0, z1) extra panes above the roof]]])
            kind = q[2] if len(q) > 2 else "AB"[i % 2]
            sill, head = STAIR_WIN[kind] if isinstance(kind, str) else kind
            out.append(dict(s=zn["s"], c=zn["c"], a=(q[0], q[1]), t="W", mat=zn.get("slot_mat", "stripe" + T["dong"]),
                            wa=[(q[0] + 0.12, q[1] - 0.12, (sill, head))], f=q[3] if len(q) > 3 else (5, T["floors"]),
                            pz=[(q[0] + 0.12, q[1] - 0.12, z0_, z1_) for z0_, z1_ in (q[4] if len(q) > 4 else [])],
                            **({"z": zn["z"]} if "z" in zn else {})))
    return dict(T, zones=out)


def cream_split(T, pieces):
    """beige parapet band (scan 102/103): the top PARAPET of every white/grey wall piece that ends at a roof + PARAPET
    becomes its own blank piece in the cream material. Off: that band is a steel railing (ROOF_RAILS)"""
    if not T.get("cream"):
        return pieces
    tops = [b[4] + PARAPET for b in T["blocks"]]
    out = []
    for a0, a1, z0, z1, zone in pieces:
        if zone["t"] == "W" and not zone.get("nocream") and zone.get("mat") in (None, "gray102", "lgray4", "gray4") and z1 - z0 > PARAPET + 0.5 \
                and any(abs(z1 - t) < 1e-3 for t in tops):
            out.append((a0, a1, z0, z1 - PARAPET, dict(zone, lod2_z1=z1)))
            band = dict(zone, wa=[], w=[], fins=[], slots=[], pz=[], grid=None, nobase=True, lod2_skip=True)
            if CREAM_BAND:
                band["mat"] = "cream"
            out.append((a0, a1, z1 - PARAPET, z1, band))
        else:
            out.append((a0, a1, z0, z1, zone))
    return out


def build_wframe(main, lod1, w, a0, a1, z0, z1, lv, WFs):
    """white frame members proud of a wall piece (this complex: white grid / bands / staggered S frames on grey panels).
    WFs = list of dict(r=[(a0, a1, dz0, dz1[, out])], f=(first, last floor), p=period floors, out=0.15, mat="fin",
    lod1_min=0.6): rects measured as one typical period on the scan elevation (scripts/wmask.py, median over many periods),
    dz from the floor bottom of the period's first floor, repeated every p floors; pieces that touch vertically become one
    box. All groups of a zone are handled together so a band can stop 2 cm inside a more proud pier"""
    merged = []
    for WF in WFs:
        f0, f1 = WF.get("f", (1, 99))
        p, out_, mat = WF.get("p", 1), WF.get("out", 0.15), WF.get("mat", "fin")
        rects = []
        for k in range(f0, f1 + 1, p):
            if k - 1 >= len(lv):
                break
            for r in WF["r"]:
                q0, q1 = max(r[0], a0), min(r[1], a1)
                zb, zt = max(lv[k - 1] + r[2], z0), min(lv[k - 1] + r[3], z1)
                if q1 - q0 > 0.05 and zt - zb > 0.05:
                    rects.append([q0, q1, zb, zt, r[4] if len(r) > 4 else out_, mat, WF.get("lod1_min", 0.6)])
        rects.sort(key=lambda q: (round(q[0], 3), round(q[1], 3), q[4], q[2]))
        for q in rects:
            m = merged[-1] if merged else None
            if m and abs(m[0] - q[0]) < 1e-3 and abs(m[1] - q[1]) < 1e-3 and m[4] == q[4] and m[5] == q[5] and q[2] <= m[3] + 1e-3:
                m[3] = max(m[3], q[3])
            else:
                merged.append(list(q))
    for A_ in merged:                              # a band ending flush with a more proud pier's edge: 2 cm into the pier
        for B_ in merged:                          # (shared end / side faces on one plane flicker)
            if B_[4] > A_[4] + 1e-3 and A_[2] < B_[3] - 1e-3 and B_[2] < A_[3] - 1e-3:
                if abs(A_[0] - B_[0]) < 1e-3 and A_[1] > B_[1]:
                    A_[0] += 0.02
                if abs(A_[1] - B_[1]) < 1e-3 and A_[0] < B_[0]:
                    A_[1] -= 0.02
    for q0, q1, zb, zt, o, mat, l1 in merged:    # FLAT paint (the frames do not stand out); piers (out
        lay = int(o) if o >= 1 else (2 if o > 0.16 else 1)   # 0.17) on layer 2 over the bands (0.15, layer 1); out >= 1 = layer
        K.paint(main, w["axis"], w["c"], w["s"], q0, q1, zb, zt, mat, layer=lay)
        if q1 - q0 >= l1:
            K.paint(lod1, w["axis"], w["c"], w["s"], q0, q1, zb, zt, mat, layer=lay)


def build_part(A, T, unit0=0):
    T = expand_slots(T)
    # LOD1 without real-size tile cutting (one quad per face) keeps it well under 50 % of main
    main, lod1 = K.MeshBuilder(A), K.MeshBuilder(A, split_tiles=False)
    lod2 = K.MeshBuilder(A, split_tiles=False)
    gls, lod1_gls = K.MeshBuilder(A), K.MeshBuilder(A)
    wins = K.WindowSet()
    rsegs = []                                     # roof railing runs: the parapet strip there is only an upstand
    up = RAIL_DIM.get(T.get("dong"), (0.4, 1.1))[0]
    keep = [p for F in T.get("crown_frames", []) for p in F["posts"]]
    blocks = with_parapets(T["blocks"], T.get("roof_rails", ()), up, rsegs, keep)
    full = [b for b in blocks[len(T["blocks"]):] if not any(abs(b[4] - g["z0"]) < 1e-6 and tuple(b[:4]) == tuple(g["rect"]) for g in rsegs)]
    def out_rect(g, d=0.6):                        # strip + d outside the wall face: fins / posts standing in front of it
        x0, x1, y0, y1 = g["rect"]                 # (103 front white fins carried up through the crown, 0.3 m off the face)
        if g["axis"] == "y":
            return (x0, x1, y0 - d, y1) if g["s"] < 0 else (x0, x1, y0, y1 + d)
        return (x0 - d, x1, y0, y1) if g["s"] < 0 else (x0, x1 + d, y0, y1)
    T = dict(T, low_strips=[out_rect(g) + (g["z0"],) for g in rsegs], full_strips=full, hf_blocks=blocks)
    build_crowns(T, main, lod1)
    build_crown_frames(T, main, lod1)
    build_roof_rails(T, rsegs, main, lod1)
    lv = floor_levels(T)
    wf_done = set()                                # white frames already built (zone, wall plane)
    base_top = lv[T["base_floors"]] if T["base_floors"] < len(lv) else 0.0
    xs, ys, H = heightfield(blocks)
    unit_id = [unit0]
    walls = walls_of(xs, ys, H)
    build_extras(T, walls, main, lod1)
    for R in T.get("grails", []):                  # glass railing inside a window reveal: glass (gls) + handrail on top
        ax, c, sd, o = R["axis"], R["c"], R["s"], R["o"]
        for g in (gls, lod1_gls):
            g.rect(K.face_pts(ax, c - sd * o, sd, R["a0"] + 0.04, R["a1"] - 0.04, R["z0"], R["z0"] + R["h"]), "frame")
        K.axbox(main, ax, c - sd * (o + 0.02), sd, R["a0"] + 0.01, R["a1"] - 0.01, 0.0, 0.05, R["z0"] + R["h"], R["z0"] + R["h"] + 0.05, "rail")
    for X in T.get("xlattices", []):
        build_xlattice(main, X, lv)
    for wi, w in enumerate(walls):
        side = side_of(w)
        for a0, a1, z0, z1, zone in cream_split(T, split_zones(w, T)):
            typ = zone["t"]
            mat_of = zone.get("mat", MAT[typ])
            btop = 0.0 if zone.get("nobase") else base_top
            st = base_mat(T, w, (a0 + a1) / 2)
            mat_at = lambda zm, m=mat_of, bt=btop, st=st: st if zm < bt else m
            holes = zone_windows(zone, side, lv, z0, z1, a0, a1, T, w)
            unit_id[0] += 1
            # LOD1: same holes as main (glass is recessed), no reveals. LOD2: build_lod2_shell
            if T.get("dong") in BASE_TONE and not zone.get("nobase") and z0 < base_top - 0.4 and base_top + 0.2 < z1 \
                    and a1 - a0 > 1.0 and typ not in ("T", "X"):
                e = 0.01 if w["axis"] == "x" else 0.0      # x / y walls 1 cm apart: corner overlaps never coplanar
                ca0, ca1 = a0 + 0.02, a1 - 0.02            # ends 2 cm in: never on a fin / pilaster side face
                # stop at fins that run down through the base (west CW lines, east piers): the cornice crossed in
                # front of them as a dark horizontal line
                cuts = sorted((fn[0] - fn[1] / 2 - 0.02, fn[0] + fn[1] / 2 + 0.02) for fn in zone.get("fins", [])
                              if isinstance(fn, tuple) and zone.get("fin_z0", base_top) < base_top - 0.4)
                runs, cur = [], ca0
                for q0, q1 in cuts:
                    if q0 - cur > 0.1:
                        runs.append((cur, min(q0, ca1)))
                    cur = max(cur, q1)
                if ca1 - cur > 0.1:
                    runs.append((cur, ca1))
                cdz = T.get("corn_dz", 0.0)    # a rotated part: its cornice sits 2 cm off the other part's (no coplanar)
                for r0, r1 in runs:
                    K.axbox(main, w["axis"], w["c"], w["s"], r0, r1, 0.0, 0.26, base_top - 0.32 + e + cdz,
                            base_top - 0.06 + e + cdz, "cornice")
                    K.axbox(main, w["axis"], w["c"], w["s"], r0, r1, 0.0, 0.13, base_top - 0.06 + e + cdz,
                            base_top + 0.075 + e + cdz, "cornice")
                if not zone.get("fins"):
                    K.axbox(lod1, w["axis"], w["c"], w["s"], ca0, ca1, 0.0, 0.26, base_top - 0.32 + e + cdz,
                            base_top + 0.075 + e + cdz, "cornice")
            for q0, q1, p0, p1 in zone.get("pz", []):  # single small openings (core tops): dark panes 1 cm proud
                if a0 <= q0 and q1 <= a1 and z0 <= p0 and p1 <= z1:
                    K.paint(main, w["axis"], w["c"], w["s"], q0, q1, p0, p1, "spandrel")
            if typ in ("W", "G", "S", "P", "C", "B") or zone.get("punch"):
                punched(lod1, w, a0, a1, z0, z1, holes, mat_at, [base_top])
                db = base_top if T.get("dong") in BASE_TONE and not zone.get("nobase") else None
                backing_lod1(lod1, w, a0, a1, z0, z1, holes, deep_below=db)
                backing(main, w, a0, a1, holes, deep_below=db)
            else:
                punched(lod1, w, a0, a1, z0, z1, [], mat_at, [base_top])
            if typ in ("T", "X"):                # dark wall + perforated screen 0.45 m in front
                punched(main, w, a0, a1, z0, z1, [], mat_at, [btop])
                sz0 = max(z0, btop, 0.02)
                zw1 = z1
                z1 = max(z1, zone.get("ztop", z1))   # screen may rise above the wall
                if z1 > zw1 + 0.1:                   # dark back plate above the wall top: else the roof side shows through
                    for mb in (main, lod1):          # the screen openings (seen-through, lod_check)
                        K.axbox(mb, w["axis"], w["c"], w["s"], a0 + 0.33, a1 - 0.33, -0.14, -0.02, zw1, z1 - 0.01, mat_of,
                                skip=("bottom",))   # stands on the parapet top (a bottom face there is coplanar)
                if zone.get("struts") and z1 - sz0 > 1.0:
                    so = 0.16
                    lt = LAT_TABLES.get(T["dong"], LAT_TABLES["104"])
                    build_struts(main, lod1, w, a0, a1, so, lt[0], lt[2], bw=lt[1], panel=zone.get("panel"), text=T["dong"], xlim=lt[3],
                                 sides=zone.get("panel_sides", False))
                    for xx0, xx1 in ((a0 + 0.02, a0 + 0.32), (a1 - 0.32, a1 - 0.02)):    # white end pilasters
                        for mb in (main, lod1):
                            K.axbox(mb, w["axis"], w["c"], w["s"], xx0, xx1, 0, 0.33, sz0, z1, "fin")
                    continue
                if z1 - sz0 > 1.0:
                    so = zone.get("so", 0.45)
                    main.rect(K.face_pts(w["axis"], w["c"] + w["s"] * so, w["s"], a0 + 0.12, a1 - 0.12, sz0, z1 - 0.12),
                              zone.get("screen", "screen" if typ == "T" else "lattice"))
                    K.axbox(main, w["axis"], w["c"], w["s"], a0 + 0.02, a0 + 0.14, 0, so + 0.02, sz0, z1, zone.get("edge", "coping"))
                    K.axbox(main, w["axis"], w["c"], w["s"], a1 - 0.14, a1 - 0.02, 0, so + 0.02, sz0, z1, zone.get("edge", "coping"))
                    K.axbox(main, w["axis"], w["c"], w["s"], a0 + 0.14, a1 - 0.14, 0, so + 0.02, z1 - 0.12, z1, zone.get("edge", "coping"))
                continue
            if zone.get("wf"):                         # once per zone and wall plane, not per wall piece: a piece border
                key = (id(zone["wf"]), w["axis"], round(w["c"], 3))   # (a block edge above) would cut a pier in two
                if key not in wf_done:
                    wf_done.add(key)
                    zz = zone.get("z", (0.0, 999.0))
                    build_wframe(main, lod1, w, zone["a"][0], zone["a"][1], zz[0], zz[1], lv, zone["wf"])
            for q0, q1, p0, p1, m in zone.get("paints", []):   # flat colour panels 1 cm proud (light sill panels, dark slits)
                for k in range(m.get("f", (1, 99))[0], min(m.get("f", (1, 99))[1], len(lv)) + 1, m.get("p", 1)):
                    zb = lv[k - 1] + p0
                    zt = lv[k - 1] + p1
                    if a0 - 1e-6 <= q0 and q1 <= a1 + 1e-6 and z0 - 1e-6 <= zb and zt <= z1 + 1e-6:
                        K.paint(main, w["axis"], w["c"], w["s"], q0, q1, zb, zt, m["mat"], layer=m.get("layer", 1))
            # lighter HORIZONTAL-striped panel under the front small windows (scan 1.19 x panel)
            if zone.get("mat") in ("dpanel", "dpanelh") and side == "B" and not zone.get("nosill"):   # back: light panel round the wide band windows + under small ones
                for h in holes:
                    fl = lv[h[4]] if h[4] > 0 else lv[0] + T["gf"] - T["fh"]
                    # fill the whole cell between the floor bands (band top fl + 0.2, next band bottom fl + fh - 0.4)
                    if isinstance(h[5], tuple) and len(h[5]) == 2 and abs(h[5][0] - 1.0) < 1e-3 and abs(h[5][1] - 1.65) < 1e-3:
                        K.paint(main, w["axis"], w["c"], w["s"], h[0], h[1], fl + 0.2, h[2], "dsill")
                        K.paint(main, w["axis"], w["c"], w["s"], h[0], h[1], h[3], fl + T["fh"] - 0.4, "dsill")
                    elif h[2] - fl >= 1.2 and h[3] - h[2] < 1.3 and not (isinstance(h[5], tuple) and len(h[5]) > 2):
                        K.paint(main, w["axis"], w["c"], w["s"], h[0], h[1], fl + 0.2, h[2], "dsill")
            if zone.get("mat") == "dpanel" and side == "F" and T.get("front_sill", True):
                for h in holes:
                    fl = lv[h[4]] if h[4] > 0 else lv[0] + T["gf"] - T["fh"]
                    if h[2] - fl >= 1.2 and h[2] - (fl + 0.2) > 0.3 and h[3] - h[2] < 1.3 and not is_open(h)                             and not (isinstance(h[5], tuple) and len(h[5]) > 2):
                        K.paint(main, w["axis"], w["c"], w["s"], h[0], h[1], fl + 0.2, h[2], "dsill")
            if zone.get("fins") and z1 - max(z0, base_top) > 3.0:
                # measured fin centres (scan elevation): 0.25 wide, 0.3 proud, base top to wall top
                for fn in zone["fins"]:
                    fc, fw, ft = (fn, 0.25, z1) if not isinstance(fn, tuple) else (fn + (z1,))[:3]
                    ft = z1 if ft is None else ft
                    fz0 = fn[3] if isinstance(fn, tuple) and len(fn) > 3 else zone.get("fin_z0", max(z0, base_top))   # 4th = own bottom
                    fo = zone.get("fin_out", 0.3)
                    if a0 - 1e-6 <= fc - fw / 2 and fc + fw / 2 <= a1 + 1e-6:
                        K.axbox(main, w["axis"], w["c"], w["s"], fc - fw / 2, fc + fw / 2, 0.0, fo, fz0, ft, zone.get("fin_mat", "fin"))
                        for mb in (main,) + ((lod1,) if fw > 0.6 else ()):
                            if mb is lod1:
                                K.axbox(lod1, w["axis"], w["c"], w["s"], fc - fw / 2, fc + fw / 2, 0.0, fo, fz0, ft, zone.get("fin_mat", "fin"))
                            if ft > z1 + 0.01:         # fin above the wall top (lowered railing upstand): its wall-side face
                                quad_n(mb, [wpt(w, fc - fw / 2, 0.0, z1), wpt(w, fc + fw / 2, 0.0, z1),   # is open there
                                            wpt(w, fc + fw / 2, 0.0, ft), wpt(w, fc - fw / 2, 0.0, ft)],   # (see-through)
                                       out_vec(w, -1), zone.get("fin_mat", "fin"))
            elif typ == "P" and z1 - max(z0, base_top) > 3.0:
                # vertical white fins: 0.2 wide, 0.3 proud, every 1.2 m, from the base top to the wall top
                n = int((a1 - a0 - 0.2) / 1.2)
                pad = (a1 - a0 - 0.2 - n * 1.2) / 2
                for k in range(n + 1):
                    f0 = a0 + pad + k * 1.2
                    if a0 + 0.05 < f0 and f0 + 0.2 < a1 - 0.05:
                        K.axbox(main, w["axis"], w["c"], w["s"], f0, f0 + 0.2, 0.0, 0.3, max(z0, base_top), z1, "fin")
            flush = False                        # every glass opening is inset (also in curtain-wall-look zones)
            depth = CW_IN if typ in ("C", "B") else WIN_IN
            if flush:                            # curtain-wall look: flush glass, full wall behind
                punched(main, w, a0, a1, z0, z1, [], mat_at, [base_top])
            else:
                punched(main, w, a0, a1, z0, z1, holes, mat_at, [base_top])
            for h in holes:
                if is_open(h):                       # empty space behind: deep recess, dark inside, no window
                    reveal(main, w, h, "char", depth=1.5)
                    main.rect(K.face_pts(w["axis"], w["c"] - w["s"] * 1.5, w["s"], h[0], h[1], h[2], h[3]), "char")
                    continue
                if h[5] == "slot":
                    reveal(main, w, h, "frame", depth=0.2)
                    main.rect(K.face_pts(w["axis"], w["c"] - w["s"] * 0.2, w["s"], h[0], h[1], h[2], h[3]), "spandrel")
                    continue
                if not flush and (h[3] - h[2] < 0.6 or (isinstance(h[5], tuple) and len(h[5]) > 2 and h[5][2] == "louver")):
                    # short wide opening = AC-unit room louver (or kind (sill, head, "louver")): real blades, dark backing
                    reveal(main, w, h, "frame")
                    ledge(main, w, h[0] - 0.05, h[1] + 0.05, h[2], out=0.08, h=0.22)
                    zb_ = h[2] + 0.04
                    while zb_ + 0.03 < h[3]:
                        K.axbox(main, w["axis"], w["c"] - w["s"] * 0.11, w["s"], h[0] + 0.01, h[1] - 0.01, 0.0, 0.08, zb_, zb_ + 0.025, "louver")
                        zb_ += 0.1
                    continue
                dep = depth
                if not flush and T.get("dong") in BASE_TONE and h[3] < base_top and not zone.get("nobase"):
                    dep = 0.35                         # podium: deep granite reveal
                steel = isinstance(h[5], tuple) and len(h[5]) > 2 and h[5][2] == "rail"
                # steel railing in front: glass only above the handrail (kit: nothing opaque within 1.5 m in front of a
                # window); below it the dark backing shows between the pickets
                gaps = glass(wins, w, h[0], h[1], (min(1.0, h[3] - h[2] - 0.3) + h[2] + 0.1) if steel else h[2], h[3], h[4], unit_id[0], dep)
                if steel:
                    # wide (balcony) window: STEEL railing in the reveal (TASK.md railing: 철제) - no glass.
                    # Pickets as an alpha-cut plane (srail: 2 cm bars every 0.11 m, too many tris as mesh on every floor),
                    # handrail + bottom rail as real boxes
                    o_, zr0 = dep * 0.5, h[2] + 0.02
                    hr = min(1.0, h[3] - h[2] - 0.3)
                    main.rect(K.face_pts(w["axis"], w["c"] - w["s"] * o_, w["s"], h[0] + 0.02, h[1] - 0.02, zr0 + 0.06, zr0 + hr), "srail")
                    for zz0, zz1 in ((zr0, zr0 + 0.06), (zr0 + hr, zr0 + hr + 0.05)):
                        K.axbox(main, w["axis"], w["c"] - w["s"] * (o_ + 0.03), w["s"], h[0] + 0.01, h[1] - 0.01, 0.0, 0.05, zz0, zz1, "srailbar")
                if zone.get("ltrim") and h[3] - h[2] > 0.6:
                    # black CW windows framed by a white L (detail photo, scan back view): sill shelf + jamb on the +a side.
                    # detail photos (19 px/m): sill line about 0.2 m tall, jamb about 0.1 m wide (thinner ones were lost at distance)
                    K.axbox(main, w["axis"], w["c"], w["s"], h[0] - 0.02, h[1] + 0.105, 0.0, 0.12, h[2] - 0.18, h[2] + 0.004, "sill")   # 4 mm over the sill joint line
                    if not any(q0 - 1e-3 <= h[0] and h[1] <= q1 + 1e-3 for q0, q1 in zone.get("ltrim_skip", [])):
                        K.axbox(main, w["axis"], w["c"], w["s"], h[1] + 0.005, h[1] + 0.105, 0.0, 0.11, h[2] + 0.004, h[3], "sill")
                if not flush:
                    reveal(main, w, h, "frame", depth=dep)
                    lo, lh = T.get("ledges", {}).get(h[5], (0.08, 0.22))
                    ledge(main, w, h[0] - 0.05, h[1] + 0.05, h[2], out=lo, h=lh)
                    for g0, g1 in gaps:              # pane mullion inside the reveal
                        K.axbox(main, w["axis"], w["c"] - w["s"] * dep, w["s"], g0, g1, 0.0, 0.05, h[2], h[3], "frame")
                else:
                    # light rail bar: under the opening, or at 1.05 m across a full-height opening (kind R)
                    rz = h[2] + 1.05 if h[5] == "R" else h[2]
                    rh, ro = zone.get("rail_h", 0.06), zone.get("rail_out", 0.06)       # bold white sill shelf (0.15 x 0.3 m)
                    K.axbox(main, w["axis"], w["c"], w["s"], h[0] - (ro - 0.06) * 0.3, h[1] + (ro - 0.06) * 0.3, 0.0, ro, rz - rh, rz, "rail")
                    for g0, g1 in gaps:
                        K.axbox(main, w["axis"], w["c"], w["s"], g0, g1, 0.0, 0.05, h[2], h[3], "frame")
            G = zone.get("grid")
            if zone.get("panels") and z1 - z0 > 6:
                pm, pr = zone["panels"]                  # blank shaft: panel joints every pm m across, every pr floors up
                nn = max(1, round((a1 - a0) / pm))
                for i in range(1, nn):
                    e = a0 + (a1 - a0) * i / nn
                    K.axbox(main, w["axis"], w["c"], w["s"], e - 0.025, e + 0.025, 0.0, 0.04, max(z0, base_top) + 0.01, z1 - 0.01, "cwjoint")
                for k in range(T["base_floors"], len(lv), pr):
                    if z0 + 0.2 < lv[k] < z1 - 0.2:
                        K.axbox(main, w["axis"], w["c"], w["s"], a0 + 0.05, a1 - 0.05, 0.0, 0.05, lv[k] - 0.025, lv[k] + 0.025, "cwjoint")
            if typ in ("C", "B") and z1 - z0 > 6 and not (zone.get("struts") or zone.get("lod2_skip")) \
                    and any(h[5] not in ("slot", "D", "D2", "D3") for h in holes):
                cw_joints(main, w, a0, a1, max(z0, btop), z1, lv, holes, blockers(T, w), T["fh"], G)
            elif G and z1 - z0 > 6:
                draw_grid(main, w, a0, a1, max(z0, btop), z1, lv, holes, blockers(T, w), G, slab=False)
            if flush and z1 - z0 > 6:
                # vertical mullions at the opening edges (continuous over the floors) + slab transoms
                edges = sorted(set([round(h[0] - 0.05, 3) for h in holes] + [round(h[1], 3) for h in holes]))
                for e in edges:
                    if a0 + 0.1 < e < a1 - 0.15:
                        K.axbox(main, w["axis"], w["c"], w["s"], e, e + 0.05, 0.0, 0.10, max(z0, base_top), z1, "frame")
                sign_box = blockers(T, w)              # transoms stop behind a dong number
                for k in range(T["base_floors"], len(lv)):
                    if z0 + 0.1 < lv[k] < z1 - 0.1:
                        cuts = sorted((q[0], q[1]) for q in sign_box if q[2] < lv[k] < q[3])
                        cur = a0 + 0.08
                        for q0, q1 in cuts + [(a1 - 0.08, a1 - 0.08)]:
                            if q0 - cur > 0.1:
                                K.axbox(main, w["axis"], w["c"], w["s"], cur, q0, 0.0, 0.07, lv[k] - 0.04, lv[k] + 0.04, "frame")
                            cur = max(cur, q1)
    for x0, x1, y0, y1, z in roofs_of(xs, ys, H):
        top_mat = "coping" if (x1 - x0) <= PT + 1e-3 or (y1 - y0) <= PT + 1e-3 else "roof"
        for rx0, rx1, ry0, ry1, rz, rm in T.get("roof_mats", []):    # e.g. a paved low terrace
            if rx0 - 1e-3 <= x0 and x1 <= rx1 + 1e-3 and ry0 - 1e-3 <= y0 and y1 <= ry1 + 1e-3 and abs(z - rz) < 0.05:
                top_mat = rm
        for mb in (main, lod1):
            K.floor_quad(mb, x0, x1, y0, y1, z, top_mat)
    build_lod2_shell(T, lod2, base_top)
    for li, L in enumerate(T.get("lounge") or []):
        if L.get("poly"):
            build_poly_lounge(L, main, lod1, lod2, wins, k0=li * 20)
        else:
            build_lounge(L, T["blocks"], main, lod1, lod2, wins, k0=li * 20)
    if T.get("roof"):
        build_roof_parts(T["roof"], main, lod1, lod2)
    return dict(main=main, lod1=lod1, lod2=lod2, gls=gls, lod1_gls=lod1_gls, windows=wins)


# ---------------------------------------------------------------- (6) export
def hide_dong(T):
    """drop every dong number: wall text (joints / ribs / windows no longer cut around it) and the lattice number
    plates (plate + short bar + side frames; the plate-band struts then run from the band bottom like the rest)"""
    for P in [T] + list(T.get("parts", [])):         # two-body towers keep signs / zones per part
        P["signs"] = []
        for zone in P.get("zones", []):
            if isinstance(zone, dict):
                zone.pop("panel", None)
                zone.pop("panel_sides", None)
    return T



def run(tower_fn, atlas=None, argv=None):
    """build one asset from a data module: `tower_fn()` -> tower dict, `atlas(A)` adds building materials"""
    global ATLAS_HOOK
    ATLAS_HOOK = atlas
    T = tower_fn()
    if not SHOW_DONG:
        hide_dong(T)
    out = K.out_dir_from_argv("output")
    A = make_atlas()
    meshes = build(A, T)
    folder, _ = K.export_asset(T["name"], LEVEL, meshes, A, out, lod2_tex=512,
                               notes=dict(dims="scan plan + VR floors", lot="auto", tower=T.get("dong", "")))
    # LOD1 shares the main atlas; copy the 5 main maps under the LOD1 name.
    import shutil
    asset = os.path.basename(os.path.normpath(folder))
    for kind in ("BaseColor", "ControlMask", "Emissive", "MaskMap", "Normal"):
        src = os.path.join(folder, "%s_%s.png" % (asset, kind))
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(folder, "%s_LOD1_%s.png" % (asset, kind)))
    return folder


if __name__ == "__main__":
    raise SystemExit("facade_engine is a library: write <name>_data.py + a launcher that calls facade_engine.run(...)")
