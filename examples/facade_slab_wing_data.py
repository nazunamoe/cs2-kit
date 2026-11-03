# -*- coding: utf-8 -*-
"""
Building data: tower 101 (Daegu, 19 F slab + 22 F diagonal body). Everything specific to this building lives here;
the shared machinery is facade_engine.py. Sources: scan 3dview.glb (ortho elevations, winlist/wmask), VR slices, photos
road1-3 / roofview / side*. Plan frame: slab axis-aligned; diagonal body = part frame turned +45 deg (see shape_notes.md).
"""
import os
import sys


def _find_kit():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, "cs2kit.py")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(os.path.abspath(__file__))


sys.path.insert(0, _find_kit())
import facade_engine as E  # noqa: E402

Z, KINDS, LOBBY_KINDS = E.Z, E.KINDS, E.LOBBY_KINDS
PARAPET = 1.25                                    # scan: parapet top 56.37 vs roof slab 55.12
E.PARAPET = PARAPET


def atlas_extra(A):
    """materials of this building (photo / scan colours)"""
    wall_painter, stripe_painter = E.wall_painter, E.stripe_painter
    A.add("bgrey", color=(86, 78, 76), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)   # #564e4c slab east end (scan)
    A.add("brown", color=(124, 84, 56), gloss=0.3, px=256, tile=(4.0, 4.0), painter=wall_painter)   # #7c5438 road1/2 brown strip
    A.add("bgroove", color=(74, 66, 64), gloss=0.3, px=256, tile=(4.0, 4.0), painter=stripe_painter)   # slab east end (road2): dark brown, grooves
    A.add("gray4h", color=(120, 126, 133), gloss=0.3, px=256, tile=(4.0, 4.0), painter=stripe_painter)    # back grey panels (scan 0.62 x white), grooves
    A.add("lgray4h", color=(138, 144, 150), gloss=0.3, px=256, tile=(4.0, 4.0), painter=stripe_painter)   # back light grey panels (0.72 x white)
    def _louvr2(c):                                        # horizontal slats: 9 per 1.5 m tile, dark gaps (closed band, see LESSONS)
        h = c.rgb.shape[0]
        band = max(1, h // 9)
        for k in range(9):
            c.rgb[k * band:min(h, k * band + int(band * 0.62)), :, :] *= 0.5
    A.add("louvr2", color=(176, 180, 184), gloss=0.35, px=128, tile=(1.5, 1.5), painter=_louvr2)


GF, FH = 3.73, 2.83                                # 1F floor at +0.90, pitch 2.83 (VR floor.range), gf = 2F floor
TOPA = 0.90 + 19 * FH + 0.45                       # 55.12 slab roof
TOPB = 0.90 + 22 * FH + 0.45                       # 63.61 diagonal body roof
TWR_TOP, BOX_TOP, PH_TOP = 60.50, 62.40, 68.90


def _t101():
    # scan mesh 887188 (3dview.glb). Slab (19 F) axis-aligned in the tower frame, diagonal body (22 F) = part turned +45 deg.
    blocks = [
        (0.60, 23.50, 5.55, 15.90, TOPA), (3.30, 19.05, 4.62, 5.55, TOPA),
        (8.04, 14.46, 0.42, 4.82, TWR_TOP - PARAPET), (8.04, 14.46, 4.82, 6.11, TWR_TOP - PARAPET),
        (8.27, 14.19, 0.58, 5.08, BOX_TOP - PARAPET),
    ]
    wing = [
        (-8.20, 10.80, 10.80, 22.03, TOPB), (-2.56, 10.80, 8.06, 10.80, TOPB),
        (10.80, 12.45, 16.31, 22.03, TOPB), (-9.73, -7.49, 16.43, 22.17, TOPB),
        (-7.49, 10.25, 22.03, 25.85, TOPB),
        (-2.50, 3.00, 2.41, 8.06, 6.00),               # entrance lobby box
        (-2.63, 5.32, 8.09, 13.32, PH_TOP - PARAPET),  # penthouse
    ]
    fh = FH
    DK = lambda a, b, f: (a, b, 0.0, fh, dict(mat="dpanel", f=f))
    zones = [Z("L", (0.5, 0.7), (5.55, 15.9), "W", mat="wstripe", wa=[]),    # slab west end: mostly inside the diagonal body
             # FRONT (-Y). Windows from the scan elevation (scripts: winlist.py on work/e101/s_y000_v000.png, floors 4-19);
             # dark balcony columns are painted over the white wall
             Z("F", (4.52, 4.72), (3.3, 8.04), "W", mat="dpanel", f=(4, 19), wa=[(4.3, 7.25, (0.65, 2.85))],
               wf=[dict(r=[(3.3, 4.28, 0.0, fh), (7.27, 8.04, 0.0, fh)], f=(4, 19), p=1, out=0.17)]),
             Z("F", (0.32, 0.52), (8.04, 8.88), "W", f=(4, 19), wa=[]),
             Z("F", (0.32, 0.52), (8.88, 10.37), "W", mat="dpanel", f=(4, 19), wa=[(8.9, 10.35, (0.15, 2.7))]),
             Z("F", (0.32, 0.52), (10.37, 14.46), "W", f=(4, 19), wa=[(12.15, 13.55, (1.4, 2.6))]),
             Z("F", (4.52, 4.72), (14.46, 19.05), "W", f=(4, 19), wa=[(15.25, 18.15, (0.7, 2.65))]),
             Z("F", (5.45, 5.65), (0.6, 3.3), "W", mat="lgray4", f=(4, 19), wa=[(1.6, 3.05, (0.65, 2.65))]),
             Z("F", (5.45, 5.65), (19.05, 23.5), "W", mat="bgrey", f=(4, 19), wa=[(19.45, 20.95, (0.8, 2.65)), (21.75, 22.6, (1.75, 2.65))]),
             # EAST END (+X, road2: dark brown wall with fine horizontal grooves, the number is not modelled)
             Z("R", (23.4, 23.6), (5.55, 15.9), "W", mat="bgroove", f=(4, 19), wa=[]),
             # BACK (+Y): colour bands from the scan ortho (row below the sills, ratio to the white): dark 0.43 / white / grey 0.62 /
             # light grey 0.72 / white; horizontal grooves on all panels (road3). Louvers beside the stair strip (TASK.md:
             # hidden louvers at the back stair sides; positions estimated), one louver at the east end (road3 left column)
             Z("B", (15.8, 16.0), (0.6, 3.4), "W", mat="bgroove", f=(4, 19), wa=[]),
             Z("B", (15.8, 16.0), (3.4, 8.2), "W", mat="wstripe", f=(4, 19), wa=[(5.2, 6.3, (0.55, 2.65)), (7.2, 8.0, (0.55, 2.7))]),
             Z("B", (15.8, 16.0), (8.2, 15.6), "W", mat="gray4h", f=(4, 19),
               wa=[(10.6, 11.5, (0.6, 2.6, "louver")), (11.9, 12.85, (0.15, 2.7)), (13.2, 14.1, (0.6, 2.6, "louver")),
                   (14.3, 15.5, (0.45, 2.7))]),
             Z("B", (15.8, 16.0), (15.6, 19.2), "W", mat="lgray4h", f=(4, 19), wa=[(16.1, 17.25, (0.5, 2.65))]),
             Z("B", (15.8, 16.0), (19.2, 23.5), "W", mat="wstripe", f=(4, 19),
               wa=[(19.3, 20.6, (1.4, 2.65)), (21.4, 22.35, (0.6, 2.6, "louver"))]),
             ]
    SQ = (0.8, 2.6)
    brown = lambda a, b: (a, b, 0.0, fh, dict(mat="brown", f=(4, 22)))
    wzones = [Z("R", (10.7, 10.9), (8.06, 16.31), "W", mat="wstripe", wa=[]),
              Z("F", (7.96, 8.16), (6.0, 10.8), "W", mat="wstripe", wa=[]),
              # WEST faces (x_n const, photo road1: white face + brown strip). Windows: scan ortho work/e101/s_y-45_v000.png
              # (view 0: image a = 8.963 - y_n), floors 4-22. The same brown strip runs on the main face (y 12.05..13.15)
              Z("L", (-8.3, -8.1), (10.8, 16.43), "W", f=(4, 22),
                wa=[(10.95, 12.03, (0.75, 2.85)), (13.18, 14.93, (0.75, 2.85)), (15.53, 16.33, (1.75, 2.6))],
                paints=[brown(12.05, 13.15)]),
              Z("L", (-9.83, -9.63), (16.43, 22.17), "W", f=(4, 22),
                wa=[(16.82, 17.62, (1.75, 2.6)), (18.22, 19.87, (0.75, 2.85)), (21.17, 22.1, SQ)]),
              Z("L", (-7.59, -7.39), (22.17, 25.85), "W", f=(4, 22), wa=[(22.3, 24.05, SQ)]),
              Z("L", (-2.66, -2.46), (8.06, 10.8), "W", f=(4, 22), wa=[(9.1, 10.7, (0.75, 2.85))]),
              # NORTH face (y 25.85): scan ortho w_y-45_v270.png (image a = 8.963 - x_n)
              Z("B", (25.75, 25.95), (-7.49, -4.3), "W", f=(4, 22), wa=[(-6.04, -4.64, (0.7, 2.65))]),
              Z("B", (25.75, 25.95), (-4.3, 1.3), "W", mat="brown", f=(4, 22),
                wa=[(-2.89, -2.04, (1.7, 2.6)), (-1.49, -0.29, (1.65, 2.8))]),
              Z("B", (25.75, 25.95), (1.3, 10.25), "W", f=(4, 22), wa=[(1.71, 3.06, (0.65, 2.7)), (4.3, 5.75, (0.65, 2.7))]),
              ]    # wing east wall runs into the slab
    # PODIUM (floors 1-3): the same window columns as above on every floor (scan podium, brightened ortho), dark polished
    # granite with a lighter granite band under the windows of floors 2-3 (road2: tonal bands step round the corners)
    zb = GF + 2 * FH
    def band_h(zn):                                          # light granite band under the windows (never over a window)
        sills = [w_[2][0] for w_ in zn["wa"] if isinstance(w_[2], tuple)]
        return max(0.1, min([0.72] + [x - 0.03 for x in sills]))
    def podium(zl):
        out = []
        for zn in zl:
            if not zn.get("wa") or zn.get("z") or zn["s"] in "LR" and zn.get("mat") == "wstripe":
                continue
            q = {k: v for k, v in zn.items() if k not in ("paints", "mat", "wf", "f", "wa")}
            q.update(z=(0.0, zb), wa=[], wsets=[dict(wa=[w_ for w_ in zn["wa"] if not (len(w_) > 2 and isinstance(w_[2], tuple) and len(w_[2]) > 2)], f=(1, 3))],
                     paints=[(zn["a"][0], zn["a"][1], 0.0, band_h(zn), dict(mat="stone_lt", f=(2, 3)))])
            out.append(q)
        return out
    zones = zones + podium(zones)
    for zn in zones:                                         # entrance (scan portal 3.5..8.0 on the slab front, canopy top z 4.4)
        if zn["s"] == "F" and zn.get("z") and tuple(zn["a"]) == (3.3, 8.04):
            zn["wsets"] = [dict(wa=[(4.3, 7.25, (0.75, 2.85))], f=(2, 3)), dict(wa=[(4.4, 7.9, "D2")], f=(1, 1))]
    screens = [(3.40, 23.20, 13.80, 15.20, TOPA, 58.40, "louvr2"), (21.70, 23.20, 7.15, 13.80, TOPA, 58.40, "louvr2"),
               (18.70, 23.20, 5.80, 7.15, TOPA, 58.40, "louvr2")]       # slab roof louver screens (roofview, scan top 58.4)
    wscreens = [(-7.20, 10.00, 24.85, 25.55, TOPB, 66.30, "louvr2")]       # diagonal body north screen
    portal = [(3.55, 8.05, 3.72, 4.62, 4.15, 4.5, "coping"),
              (3.55, 3.8, 3.72, 4.62, 0.0, 4.15, "coping"), (7.8, 8.05, 3.72, 4.62, 0.0, 4.15, "coping")]
    wzones = wzones + podium(wzones)
    return dict(name="ResidentialHighTower101", dong="101", gf=GF, fh=FH, floors=19, base_floors=3,
                blocks=blocks, zones=zones, canopies=[], solids=[], roofbox=[], default="W", auto=True,
                base_stone="stone_dk", kinds=dict(KINDS, D=(0.08, 3.6), D2=(0.08, 3.1), **LOBBY_KINDS),
                parts=[dict(blocks=blocks, zones=zones, canopies=[], solids=portal + screens),
                       dict(blocks=wing, zones=wzones, canopies=[], solids=wscreens, rot=45.0, move=(0.0, 0.0), floors=22)])





def tower():
    return _t101()
