# -*- coding: utf-8 -*-
"""
photo_sections.py (was paint_from_detail.py) - photo section registry PHOTOS + row fit, used by every
tools/samhan_facade script. Its old main() (per-cell auto paint, do NOT use for final paint) reads the paint of every wall, floor by floor, from the near-frontal detail photos
(atype-1..8, btype-1..8: 3D-map facade views, labels "NN F" mark floors).

Every photo is cut into SECTIONS (one depth group of walls that face the camera, e.g. the near head or the bar
behind it). A section is registered by hand: two pixel columns <-> two plan positions along the wall (linear) and
two floors <-> pixel rows of their window centres (linear). Each wall of the section is cut into 0.5 m cells and
every floor gets a class: 0 white wall, 1 navy, 2 navy with the thick white band below the windows (stripe floor).

Data is read in TYPE A plan coordinates (the detail photos of both towers show the same layout). Walls without a
photo get the data of their point-symmetric partner (plan rotated 180 deg), type B gets its walls through the
mirror y -> -y. Hidden / unknown floors copy the nearest known floor.

    python paint_from_detail.py A        -> paint_A.json + previews/paint_detail/A_<photo>_<section>.png
    python paint_from_detail.py B        -> paint_B.json

Comments ASCII only. Never writes into output/.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen  # noqa: E402
T = gen()

CELL = 0.5
BASE_TOP = 5
FLOORS = {"A": 58, "B": 57}

# Views (A plan): front = camera along +y (walls facing -y), back = along -y, right = along -x, left = along +x.
# sec: walls (A edge indices), a = plan positions at the two px columns, px, fl = ((model floor, y), ...) window rows.
# Floor numbers: the refuge row (blank big bays + one small window on the head walls) = model floor 29 (user);
# the map listing labels "N F" then sit on model floor N - 1 (checked on atype-1/2, btype-1..8). Top visible row
# without a refuge in view = model floor 57 (estimated, atype-3 far: refuge + top row).
FRONT_HEAD, FRONT_BAR = [0, 2, 4, 6], [12, 14, 16, 18, 20, 22, 24]
BACK_HEAD, BACK_BAR = [28, 30, 32, 34], [40, 42, 44, 46, 48, 50, 52]
R_FAR, R_MID, R_NEAR = [5, 7], [19, 21], [23, 25, 27]
L_FAR, L_MID, L_NEAR = [33, 35], [47, 49], [51, 53, 55]
FA, FB = (-31.6, -6.4), (-5.6, 32.6)      # plan a at the left / right px of front head / bar
BA, BB = (31.6, 6.4), (5.6, -32.6)
RF, RM, RN = (-22.3, -10.9), (-6.3, 4.2), (4.2, 20.2)
LF, LM, LN = (22.3, 10.9), (6.3, -4.2), (-4.2, -20.2)


def labels(x0, x1, ys, h=22):
    """mask boxes over the listing labels (they cover the wall)"""
    return [(x0, y - h, x1, y + h) for y in ys]


PHOTOS = {
    "A": [
        dict(file="atype-1.png", masks=[], secs=[
            dict(name="head", walls=FRONT_HEAD, a=FA, px=(165, 575), fl=((29, 1494), (56, 236)), rowx=(442, 460)),
            dict(name="bar", walls=FRONT_BAR, a=FB, px=(590, 1047), fl=((24, 1562), (56, 329)), rowx=(932, 947)),
        ]),
        dict(file="atype-2.png", masks=labels(0, 335, (228, 272, 460, 690, 830)), secs=[
            dict(name="head", walls=FRONT_HEAD, a=FA, px=(285, 693), fl=((24, 230), (11, 828)), rowx=(557, 582)),
            dict(name="bar", walls=FRONT_BAR, a=FB, px=(710, 1162), fl=((24, 315), (11, 817)), rowx=(1050, 1068)),
        ]),
        dict(file="atype-3.png", masks=labels(50, 190, (1622, 1657, 1795)), secs=[
            dict(name="far", walls=R_FAR, a=RF, px=(145, 270), fl=((29, 1442), (57, 517))),
            dict(name="mid", walls=R_MID, a=RM, px=(285, 460), fl=((57, 359), (31, 1736))),
            dict(name="near", walls=R_NEAR, a=RN, px=(460, 755), fl=((57, 319), (31, 1791)), rowx=(615, 640)),
        ]),
        dict(file="atype-4.png", masks=labels(80, 215, (581, 615, 757, 928, 1031)) + [(350, 0, 500, 65)], secs=[
            dict(name="far", walls=R_FAR, a=RF, px=(168, 300), fl=((24, 581), (11, 1031))),
            dict(name="mid", walls=R_MID, a=RM, px=(310, 490), fl=((24, 445), (11, 1108))),
            dict(name="near", walls=R_NEAR, a=RN, px=(490, 786), fl=((24, 415), (11, 1120)), rowx=(645, 665)),
        ]),
        dict(file="atype-5.png", masks=[(0, 1690, 140, 1783), (500, 0, 670, 45)], secs=[
            dict(name="head", walls=BACK_HEAD, a=BA, px=(100, 510), fl=((29, 1475), (57, 212)), rowx=(381, 401)),
            dict(name="bar", walls=BACK_BAR, a=BB, px=(520, 955), fl=((57, 325), (24, 1558)), rowx=(857, 873)),
        ]),
        dict(file="atype-6.png", masks=labels(65, 200, (390, 436, 628, 862, 1007)), secs=[
            dict(name="head", walls=BACK_HEAD, a=BA, px=(155, 550), fl=((24, 390), (11, 1007)), rowx=(445, 460)),
            dict(name="bar", walls=BACK_BAR, a=BB, px=(575, 1010), fl=((24, 438), (11, 942)), rowx=(917, 930)),
        ]),
        dict(file="atype-7.png", masks=labels(70, 200, (1545, 1578)), secs=[
            dict(name="far", walls=L_FAR, a=LF, px=(155, 285), fl=((29, 1362), (57, 428))),
            dict(name="mid", walls=L_MID, a=LM, px=(340, 500), fl=((57, 262), (47, 772)), rowx=(460, 488)),
            dict(name="near", walls=L_NEAR, a=LN, px=(515, 810), fl=((57, 232), (47, 762)), rowx=(680, 697)),
        ]),
        dict(file="atype-8.png", masks=labels(90, 222, (480, 514, 655, 828, 932)) + [(360, 0, 510, 60)], secs=[
            dict(name="far", walls=L_FAR, a=LF, px=(180, 300), fl=((24, 480), (11, 932))),
            dict(name="mid", walls=L_MID, a=LM, px=(350, 500), fl=((24, 295), (11, 965))),
            dict(name="near", walls=L_NEAR, a=LN, px=(540, 830), fl=((24, 270), (11, 968)), rowx=(688, 705)),
        ]),
    ],
    # type B photos read in A plan terms (btype_1 head = A front head, column correlation 0.82; mirrored only 0.25),
    # the result is moved onto the mirrored B plan by mirror_to_b(). Which side pair is front / back and right / left
    # is not visible in the photos (point symmetric views) - chosen like the A photos (estimated).
    "B": [
        dict(file="btype_1.png", masks=labels(45, 195, (365, 457, 595, 1283, 1430, 1620)), secs=[
            dict(name="head", walls=FRONT_HEAD, a=FA, px=(130, 545), fl=((29, 1560), (55, 365)), rowx=(410, 428)),
            dict(name="bar", walls=FRONT_BAR, a=FB, px=(552, 1000), fl=((50, 620), (32, 1312)), rowx=(900, 912)),
        ]),
        dict(file="btype-2.png", masks=labels(138, 290, (123, 270, 463, 609, 655, 795, 933, 1027, 1073)), secs=[
            dict(name="head", walls=FRONT_HEAD, a=FA, px=(220, 640), fl=((29, 403), (15, 1073)), rowx=(510, 528)),
            dict(name="bar", walls=FRONT_BAR, a=FB, px=(645, 1090), fl=((24, 680), (15, 1025)), rowx=(990, 1003)),
        ]),
        dict(file="btype-5.png", masks=labels(70, 200, (357, 449, 588, 1283, 1430, 1620)), secs=[
            dict(name="head", walls=BACK_HEAD, a=BA, px=(155, 575), fl=((29, 1560), (55, 357)), rowx=(445, 462)),
            dict(name="bar", walls=BACK_BAR, a=BB, px=(580, 1020), fl=((50, 625), (32, 1315)), rowx=(922, 938)),
        ]),
        dict(file="btype-6.png", masks=labels(180, 310, (68, 262, 409, 456, 596, 736, 830, 877)), secs=[
            dict(name="head", walls=BACK_HEAD, a=BA, px=(262, 690), fl=((29, 204), (15, 877)), rowx=(560, 575)),
            dict(name="bar", walls=BACK_BAR, a=BB, px=(692, 1125), fl=((24, 505), (15, 845)), rowx=(1030, 1045)),
        ]),
        dict(file="btype-3.png", masks=labels(38, 170, (558, 626, 728, 1239, 1347, 1489, 1595, 1630, 1732))
                                       + [(300, 0, 450, 35)], secs=[
            dict(name="far", walls=R_FAR, a=RF, px=(125, 250), fl=((29, 1442), (55, 558))),
            dict(name="mid", walls=R_MID, a=RM, px=(265, 440), fl=((50, 675), (32, 1585))),
            dict(name="near", walls=R_NEAR, a=RN, px=(440, 740), fl=((50, 665), (32, 1637)), rowx=(597, 617)),
        ]),
        dict(file="btype-4.png", masks=labels(100, 232, (0, 141, 248, 283, 386, 490, 558, 593)), secs=[
            dict(name="far", walls=R_FAR, a=RF, px=(190, 320), fl=((29, 95), (15, 593))),
            dict(name="mid", walls=R_MID, a=RM, px=(355, 545), fl=((24, 155), (15, 615))),
            dict(name="near", walls=R_NEAR, a=RN, px=(545, 845), fl=((24, 135), (15, 618)), rowx=(700, 720)),
        ]),
        dict(file="btype-7.png", masks=labels(80, 212, (558, 626, 728, 1237, 1345, 1485, 1590, 1625, 1727))
                                       + [(340, 0, 490, 25)], secs=[
            dict(name="far", walls=L_FAR, a=LF, px=(165, 290), fl=((29, 1440), (55, 558))),
            dict(name="mid", walls=L_MID, a=LM, px=(295, 470), fl=((50, 675), (32, 1588))),
            dict(name="near", walls=L_NEAR, a=LN, px=(470, 765), fl=((50, 668), (32, 1640)), rowx=(620, 640)),
        ]),
        dict(file="btype-8.png", masks=labels(98, 228, (230, 338, 373, 475, 578, 647, 681)), secs=[
            dict(name="far", walls=L_FAR, a=LF, px=(185, 310), fl=((29, 187), (15, 681))),
            dict(name="mid", walls=L_MID, a=LM, px=(345, 530), fl=((24, 195), (15, 655))),
            dict(name="near", walls=L_NEAR, a=LN, px=(535, 830), fl=((24, 175), (15, 650)), rowx=(690, 710)),
        ]),
    ],
}


# The registry above is the Samhan Goldenview example (kept as a model for new entries).
# For a new building: register its photos in PHOTOS below (or set PHOTOS = EXAMPLE_PHOTOS to try the example).
EXAMPLE_PHOTOS = PHOTOS
PHOTOS = {"A": [], "B": []}


def edges():
    return T.edges_of(T.full_poly(T.HALF, False))


def ncells(e):
    return max(1, int(round(e["L"] / CELL)))


def section_cells(g, sec, E, floors, mask, tint, br):
    """{edge index: array (rows, cells)} for one section; -1 = not read"""
    a_l, a_r = sec["a"]
    p_l, p_r = sec["px"]

    def px(a):
        return p_l + (a - a_l) * (p_r - p_l) / (a_r - a_l)

    H, W = g.shape
    x0, x1 = int(max(0, min(p_l, p_r))), int(min(W, max(p_l, p_r)))
    yc, pitch = fit_rows(g, sec, x0, x1, mask)
    # white reference per pixel row: bright parts of this section, smoothed over +-3 floors
    prof = np.percentile(g[:, x0:x1], 93, axis=1)
    k = max(3, int(abs(pitch) * 3))
    ref = np.array([np.median(prof[max(0, i - k):i + k + 1]) for i in range(H)])
    yb_lo, yb_hi = sorted((yc(BASE_TOP + 1), yc(floors)))
    body = ref[int(max(0, yb_lo)):int(min(H, yb_hi)) + 1]
    if len(body):
        ref = np.minimum(ref, 1.08 * np.median(body))   # sky / sign above the roof must not raise the white level
    rows = list(range(BASE_TOP + 1, floors + 1))
    # blue tint (b - r) of the white wall of this section: shaded white is bluish too, panels are judged against it
    sub_g, sub_br = g[:, x0:x1], br[:, x0:x1]
    bright = sub_g > 0.85 * ref[:, None]
    white_br = float(np.median(sub_br[bright])) if bright.any() else 0.0
    out = {}
    for i in sec["walls"]:
        e = E[i]
        n = ncells(e)
        cls = np.full((len(rows), n), -1, np.int8)
        for kk in range(n):
            a0 = e["a0"] + kk * e["L"] / n
            a1 = a0 + e["L"] / n
            xa, xb = sorted((px(a0), px(a1)))
            xa, xb = int(round(xa)) + 1, int(round(xb)) - 1
            if xb - xa < 2:
                xa, xb = int(xa) - 1, int(xa) + 2
            if xa < 0 or xb > W:
                continue
            for r, f in enumerate(rows):
                p = abs(yc(f + 0.5) - yc(f - 0.5))
                # floor body from the slab (0) to the slab above (1); the row mark sits at rowh of the floor
                y_bot = yc(f) + rowh(sec) * p
                y_top = y_bot - p
                if y_top < 0 or y_bot > H or p < 4:
                    continue
                if mask[int(y_top):int(y_bot) + 1, xa:xb].any():
                    continue
                if tint[int(y_top):int(y_bot) + 1, xa:xb].mean() > 0.2:
                    continue          # listing highlight band (blue / pink overlay) over this floor

                def zone(h0, h1):
                    ya, yb = int(round(y_bot - h1 * p)), int(round(y_bot - h0 * p)) + 1
                    blk = g[ya:yb, xa:xb]
                    return np.median(np.percentile(blk, 75, axis=1) / np.maximum(ref[ya:yb], 1))
                win = zone(0.38, 0.72)                          # window band (piers between the windows)
                ya, yb = int(round(y_top)), int(round(y_bot)) + 1
                pr = np.percentile(g[ya:yb, xa:xb], 75, axis=1) / np.maximum(ref[ya:yb], 1)
                frac = float((pr > BAND_LIGHT).mean())          # share of bright rows: robust to row offsets
                ZONES[(sec["name"], i, f, kk)] = (round(float(win), 2), round(frac, 2))
                wb = g[ya:yb, xa:xb] > 0.45 * ref[ya:yb, None]
                blue = float(np.median(br[ya:yb, xa:xb][wb])) - white_br if wb.sum() > 6 else 0.0
                if blue > BLUE_DB and win >= 0.45:
                    cls[r, kk] = 3          # light blue-grey panels (atype-7 bar end)
                elif win >= LIGHT:
                    cls[r, kk] = 0          # white pier between the windows
                elif frac < NAVY_FRAC:
                    cls[r, kk] = 1          # no white rows at all: navy block
                else:
                    cls[r, kk] = 9          # dark window band with white rows: window in a white wall or stripe floor
        out[i] = resolve(cls, e["L"] / n)
    return out, px, yc, rows


WIN_MAX = 4.2   # a dark run between two white piers that is not wider than this is a window in a white wall


def resolve(cls, cw):
    """class 9 runs: between white piers and narrow -> white wall with a window, otherwise stripe floor"""
    out = cls.copy()
    for r in range(cls.shape[0]):
        row = cls[r]
        k = 0
        n = len(row)
        while k < n:
            if row[k] != 9:
                k += 1
                continue
            j = k
            while j < n and row[j] in (9, 1):
                j += 1
            left = row[k - 1] if k > 0 else -2
            right = row[j] if j < n else -2
            narrow = (j - k) * cw <= WIN_MAX
            white_sides = left in (0, -2) and right in (0, -2) and not (left == -2 and right == -2)
            for q in range(k, j):
                if row[q] == 9:
                    out[r, q] = 0 if (narrow and white_sides) else 2
            k = j
    return out


ZONES = {}


def rowh(sec):
    """height of the row mark above the slab, share of the floor: small windows 0.62 (they sit in the upper half of the big ones), label bands 0.5"""
    return sec.get("rowh", 0.62 if "rowx" in sec else 0.55)
LIGHT = 0.58        # pier brighter than this share of the local white = white paint
BAND_LIGHT = 0.45   # white band below the windows (often in shade) brighter than this = white
BLUE_DB = 999       # light blue-grey test off: window glass reflections hit it too (atype-1 bar)
NAVY_FRAC = 0.12    # floors with less bright rows than this are navy blocks


def fit_rows(g, sec, x0, x1, mask):
    """window row centre of every floor. sec["rowx"] = a pixel strip with one small window per floor (white wall):
    its dark minima are followed floor by floor from the anchor sec["fl"][0] (label floor, y). Without a strip the
    two anchors give a straight line. Returns yc(f) (f may be fractional) and the mean pitch (px per floor, < 0)."""
    (f1, y1), (f2, y2) = sec["fl"]
    p0 = (y2 - y1) / (f2 - f1)
    H = g.shape[0]
    ys = {}
    if "rowx" in sec:
        xa, xb = sec["rowx"]
        prof = np.convolve(g[:, xa:xb].mean(axis=1), np.ones(3) / 3, mode="same")
        w = max(2, int(abs(p0) * 0.3))
        med = np.median(prof)
        mins = np.array([i for i in range(w, H - w) if prof[i] == prof[i - w:i + w + 1].min() and prof[i] < 0.85 * med])
        if len(mins):
            def near(y, p):
                k = np.argmin(np.abs(mins - y))
                return mins[k] if abs(mins[k] - y) < 0.3 * abs(p) else None
            y = near(y1, p0)
            ys[f1] = float(y if y is not None else y1)
            for d in (1, -1):                      # walk up (d = +1 floor) and down
                f, y, p = f1, ys[f1], p0
                while True:
                    f += d
                    pred = y + d * p
                    if pred < -abs(p) or pred > H + abs(p) or f < BASE_TOP or f > 70:
                        break
                    m = near(pred, p)
                    if m is not None:
                        p = 0.7 * p + 0.3 * (m - y) * d
                        y = float(m)
                    else:
                        y = pred
                    ys[f] = y
    if len(ys) < 4:
        ys = {f: y1 + (f - f1) * p0 for f in range(BASE_TOP - 2, 72)}
    fs = np.array(sorted(ys))
    yv = np.array([ys[f] for f in fs])
    pitch = (yv[-1] - yv[0]) / (fs[-1] - fs[0])

    def yc(f):
        if f <= fs[0]:
            return yv[0] + (f - fs[0]) * pitch
        if f >= fs[-1]:
            return yv[-1] + (f - fs[-1]) * pitch
        return float(np.interp(f, fs, yv))
    return yc, pitch


def sheet(kind, ph, sec, im, E, res, px, yc, rows):
    d0 = os.path.join(ROOT, "previews", "paint_detail")
    os.makedirs(d0, exist_ok=True)
    (f1, _), (f2, _) = sec["fl"]
    ov = im.copy()
    d = ImageDraw.Draw(ov, "RGBA")
    col = {1: (255, 0, 0, 90), 2: (255, 200, 0, 110), 3: (0, 220, 255, 110)}
    for i, cls in res.items():
        e = E[i]
        n = cls.shape[1]
        for r, f in enumerate(rows):
            for kk in range(n):
                v = cls[r, kk]
                a0 = e["a0"] + kk * e["L"] / n
                xa, xb = sorted((px(a0), px(a0 + e["L"] / n)))
                p = abs(yc(f + 0.5) - yc(f - 0.5))
                yb = yc(f) + rowh(sec) * p
                ya = yb - p
                if v > 0:
                    d.rectangle([xa, ya, xb, yb], fill=col[v])
                elif v < 0:
                    d.rectangle([xa, ya, xb, yb], fill=(0, 0, 0, 60))
    lines = ImageDraw.Draw(im)
    for f in rows:
        y = yc(f) + rowh(sec) * abs(yc(f + 0.5) - yc(f - 0.5))
        lines.line([(min(sec["px"]), y), (max(sec["px"]), y)], fill=(0, 255, 0) if f % 5 == 0 else (0, 160, 0), width=1)
        if f % 5 == 0:
            lines.text((min(sec["px"]) - 22, y - 12), str(f), fill=(0, 140, 0))
    for i in res:
        for a in (E[i]["a0"], E[i]["a1"]):
            lines.line([(px(a), 0), (px(a), im.size[1])], fill=(255, 0, 255), width=1)
    xs = sorted(sec["px"])
    box = (max(0, int(xs[0]) - 30), 0, min(im.size[0], int(xs[1]) + 10), im.size[1])
    a, b = im.crop(box), ov.crop(box)
    both = Image.new("RGB", (a.size[0] * 2 + 6, a.size[1]), "white")
    both.paste(a, (0, 0))
    both.paste(b, (a.size[0] + 6, 0))
    both.save(os.path.join(d0, "%s_%s_%s.png" % (kind, ph["file"].split(".")[0], sec["name"])))


def partner_of(E, e):
    for o in E:
        if o["axis"] == e["axis"] and o["s"] == -e["s"] and abs(o["c"] + e["c"]) < 0.05 and \
                abs(o["a0"] + e["a1"]) < 0.05 and abs(o["a1"] + e["a0"]) < 0.05:
            return o


def clean(c):
    """remove single-cell and single-floor specks (the paint comes in clean rectangles)"""
    c = c.copy()
    for _ in range(2):
        for row in c:
            for k in range(1, len(row) - 1):
                if row[k - 1] == row[k + 1] and row[k] != row[k - 1]:
                    row[k] = row[k - 1]
        v = c.copy()
        for r in range(1, len(c) - 1):
            m = (c[r - 1] == c[r + 1]) & (c[r] != c[r - 1])
            v[r][m] = c[r - 1][m]
        c = v
    return c


def default_class(e):
    notch = (e["axis"] == "y" and 6.0 < abs(e["c"]) < 11.5 and abs(e["a0"] + e["a1"]) / 2 > 5.5 and e["L"] < 7.0) or \
            (e["axis"] == "x" and abs(abs(e["c"]) - 12.3) < 0.05)
    return 1 if (notch or e["L"] < 1.6) else 0


def read_kind(kind):
    """per A edge: rows x cells, read from the detail photos of this tower (A plan coordinates)"""
    E = edges()
    floors = FLOORS[kind]
    data = {}
    for ph in PHOTOS[kind]:
        im = Image.open(os.path.join(ROOT, ph["file"])).convert("RGB")
        g = np.asarray(im.convert("L"), np.float32)
        mask = np.zeros(g.shape, bool)
        for x0, y0, x1, y1 in ph["masks"]:
            mask[y0:y1, x0:x1] = True
        rgb = np.asarray(im, np.float32)
        r, gg, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        tint = ((b - r > 45) & (b > 90)) | ((r - gg > 25) & (b - gg > 25))   # listing highlight bands
        for sec in ph["secs"]:
            res, px, yc, rows = section_cells(g, sec, E, floors, mask, tint, b - r)
            sheet(kind, ph, sec, im.copy(), E, res, px, yc, rows)
            for i, cls in res.items():
                if i not in data:
                    data[i] = cls
                else:
                    m = (data[i] < 0) & (cls >= 0)
                    data[i][m] = cls[m]
    return E, data


def finish(E, data, floors):
    nrow = floors - BASE_TOP
    out = {}
    known = {}
    for e in E:
        c = data.get(e["i"])
        known[e["i"]] = c if c is not None else np.full((nrow, ncells(e)), -1, np.int8)
    stat = dict(photo=0, partner=0, floor_copy=0, default=0)
    for e in E:
        c = known[e["i"]].copy()
        stat["photo"] += int((c >= 0).sum())
        o = partner_of(E, e)
        if o is not None and (c < 0).any():
            pc = known[o["i"]][:, ::-1]
            m = (c < 0) & (pc >= 0)
            c[m] = pc[m]
            stat["partner"] += int(m.sum())
        if (c >= 0).any():
            for k in range(c.shape[1]):   # unknown floors: nearest known floor of the same cell column
                col = c[:, k]
                kn = np.where(col >= 0)[0]
                if len(kn) == 0:
                    continue
                for r in np.where(col < 0)[0]:
                    col[r] = col[kn[np.argmin(np.abs(kn - r))]]
                    stat["floor_copy"] += 1
            for r in range(c.shape[0]):   # still unknown cells: nearest known cell of the same floor
                row = c[r]
                kn = np.where(row >= 0)[0]
                for k in np.where(row < 0)[0]:
                    row[k] = row[kn[np.argmin(np.abs(kn - k))]] if len(kn) else default_class(e)
        m = c < 0
        c[m] = default_class(e)
        stat["default"] += int(m.sum())
        out[e["i"]] = clean(c)
    return out, stat


def mirror_to_b(EA, outA):
    """type B walls from the A-plan data (B plan = A mirrored y -> -y)"""
    EB = T.edges_of(T.full_poly(T.HALF, True))
    out = {}
    for e in EB:
        for a in EA:
            if e["axis"] == "y" and a["axis"] == "y" and abs(a["c"] + e["c"]) < 0.05 and a["s"] == -e["s"] and \
                    abs(a["a0"] - e["a0"]) < 0.05 and abs(a["a1"] - e["a1"]) < 0.05:
                out[e["i"]] = outA[a["i"]]
                break
            if e["axis"] == "x" and a["axis"] == "x" and abs(a["c"] - e["c"]) < 0.05 and a["s"] == e["s"] and \
                    abs(a["a0"] + e["a1"]) < 0.05 and abs(a["a1"] + e["a0"]) < 0.05:
                out[e["i"]] = outA[a["i"]][:, ::-1]
                break
    return out


def main(kind):
    E, data = read_kind(kind)
    floors = FLOORS[kind]
    out, stat = finish(E, data, floors)
    if kind == "B":
        out = mirror_to_b(E, out)
    meta = dict(floors=floors, base_top=BASE_TOP, cell=CELL, classes="0 white, 1 navy, 2 navy + white band below the windows, 3 light blue-grey",
                source="paint_from_detail.py", photos=[p["file"] for p in PHOTOS[kind]], cells=stat)
    js = dict(meta=meta, edges={str(i): dict(n=int(c.shape[1]), rows=c.tolist()) for i, c in out.items()})
    json.dump(js, open(os.path.join(ROOT, "paint_%s.json" % kind), "w"))
    print("paint_%s.json  walls %d  cells %s" % (kind, len(out), stat))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
