# -*- coding: utf-8 -*-
"""
render.py — Blender 없이 미리보기 PNG (numpy 래스터라이저, 정사영). output/<asset>/ 의 OBJ + BaseColor 사용.

사용:
  python tools/render.py output/<asset> -o previews/a.png                       기본 4방향 (정면·우측 사선·후면·좌측 사선)
  python tools/render.py output/<asset> -o p.png --views front,iso,top,lod1,lod2
  python tools/render.py output/<asset> -o p.png --views front --zoom 3,0.5,0.1  3배 확대, 가로 50%·높이 10% 지점 중심
  python tools/render.py output/<asset> -o p.png --views yaw30:pitch5 --box=-10,10,-5,3,0,8   일부만 (x0,x1,y0,y1,z0,z1 m)
  python tools/render.py output/<asset> -o p.png --views front --photo refs/a.jpg  사진과 나란히 (같은 높이)
  python tools/render.py output/<asset> -o p.png --views atlas                    아틀라스(BaseColor) 칸 이름 표시

보기 이름: front back left right iso(=-35°) iso2(=35°) iso3 iso4 top lod1 lod2 atlas, 또는 yaw<도>[:pitch<도>]
  yaw 0 = 정면(-Y 쪽에서 봄), 90 = 오른쪽(+X)에서, 180 = 후면
옵션: --size 900x700, --mode color|normal|ctrl|emissive (텍스처 종류 확인), --night (발광만 밝게), --nolabel
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)
from objio import load_asset, load_png, tex_path  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass

SKY = np.array([0.84, 0.90, 0.97])
WINC = np.array([0.33, 0.45, 0.56])
GLS = np.array([0.55, 0.75, 0.78])
PRESET = {"front": (0, 8), "back": (180, 8), "left": (-90, 8), "right": (90, 8), "iso": (-35, 22), "iso2": (35, 22),
          "iso3": (145, 22), "iso4": (-145, 22), "top": (0, 89.5), "lod1": (-35, 22), "lod2": (-35, 22)}


class Tex:
    def __init__(self, texdir, asset, lod2, mode):
        name = {"color": "BaseColor", "normal": "Normal", "ctrl": "ControlMask", "emissive": "Emissive"}[mode]
        p = tex_path(texdir, asset, name, lod2) or tex_path(texdir, asset, name)
        self.img = load_png(p) / 255.0 if p else np.ones((4, 4, 4))
        bp = tex_path(texdir, asset, "BaseColor", lod2) or tex_path(texdir, asset, "BaseColor")
        self.alpha = load_png(bp)[..., 3] / 255.0 if bp else np.ones(self.img.shape[:2])
        npth = tex_path(texdir, asset, "Normal", lod2)
        self.nrm = load_png(npth, "RGB") / 127.5 - 1 if (npth and mode == "color") else None
        ep = tex_path(texdir, asset, "Emissive", lod2)
        self.emis = load_png(ep, "RGB") / 255.0 if ep else None
        self.H, self.W = self.img.shape[:2]


def render(parts, tex, yaw, pitch, size, title="", zoom=None, box=None, night=False, label=True):
    T, UV, KIND = [], [], []
    for mesh, kind in parts:
        if mesh is None:
            continue
        for f, uv in zip(mesh.faces, mesh.uvs):
            q = mesh.verts[f]
            if box is not None:
                c = q.mean(0)
                if not (box[0] <= c[0] <= box[1] and box[2] <= c[1] <= box[3] and box[4] <= c[2] <= box[5]):
                    continue
            for k in range(1, len(f) - 1):
                T.append(q[[0, k, k + 1]]); UV.append(uv[[0, k, k + 1]]); KIND.append(kind)
    if not T:
        return Image.new("RGB", size, "white")
    T = np.array(T); UV = np.array(UV); KIND = np.array(KIND)
    yw, pt = math.radians(yaw), math.radians(pitch)
    cy, sy, cp, sp = math.cos(yw), math.sin(yw), math.cos(pt), math.sin(pt)
    Pm = T @ np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]).T
    x = Pm[..., 0]; dpt = Pm[..., 1] * cp - Pm[..., 2] * sp; z = Pm[..., 2] * cp + Pm[..., 1] * sp
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    light = np.array([-0.45, -0.75, 0.55]); light /= np.linalg.norm(light)
    shade = (0.58 + 0.42 * np.clip(n @ light, 0, 1)) * (0.25 if night else 1.0)
    W, H = size
    sc = 0.92 * min(W / max(1e-6, x.max() - x.min()), H / max(1e-6, z.max() - z.min()))
    cx0, cz0 = (x.max() + x.min()) / 2, (z.max() + z.min()) / 2
    if zoom:
        f, fx, fz = zoom
        cx0 = x.min() + (x.max() - x.min()) * fx; cz0 = z.min() + (z.max() - z.min()) * fz; sc *= f
    X = (x - cx0) * sc + W / 2; Y = H / 2 - (z - cz0) * sc
    img = np.ones((H, W, 3)) * (SKY * (0.2 if night else 1)); zb = np.full((H, W), np.inf)
    order = list(np.nonzero(KIND != "glass")[0]) + list(np.nonzero(KIND == "glass")[0])
    for i in order:
        xa, ya, da = X[i], Y[i], dpt[i]
        x0, x1 = int(max(0, math.floor(xa.min()))), int(min(W - 1, math.ceil(xa.max())))
        y0, y1 = int(max(0, math.floor(ya.min()))), int(min(H - 1, math.ceil(ya.max())))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, bx, cx), (ay, by, cyy) = xa, ya
        den = (by - cyy) * (ax - cx) + (cx - bx) * (ay - cyy)
        if abs(den) < 1e-9:
            continue
        w0 = ((by - cyy) * (gx - cx) + (cx - bx) * (gy - cyy)) / den
        w1 = ((cyy - ay) * (gx - cx) + (ax - cx) * (gy - cyy)) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        dep = w0 * da[0] + w1 * da[1] + w2 * da[2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        reg = img[y0:y1 + 1, x0:x1 + 1]
        if KIND[i] == "window":
            col = np.broadcast_to((np.array([1.0, 0.85, 0.55]) * 0.8 if night else WINC * shade[i]), gx.shape + (3,))
        elif KIND[i] == "glass":
            upd = m & (dep < sub)
            reg[upd] = reg[upd] * 0.62 + GLS * 0.38 * (0.3 if night else 1)
            continue
        else:
            u = w0 * UV[i, 0, 0] + w1 * UV[i, 1, 0] + w2 * UV[i, 2, 0]
            v = w0 * UV[i, 0, 1] + w1 * UV[i, 1, 1] + w2 * UV[i, 2, 1]
            px = np.clip((u * tex.W).astype(int), 0, tex.W - 1); py = np.clip(((1 - v) * tex.H).astype(int), 0, tex.H - 1)
            bump = 1.0
            if tex.nrm is not None:
                nn = tex.nrm[py, px]
                bump = 1 + 0.6 * (nn[..., 0] * 0.4 - nn[..., 1] * 0.5)
            col = tex.img[py, px][..., :3] * (shade[i] * bump)[..., None]
            if tex.emis is not None:
                col = col + tex.emis[py, px] * (1.0 if night else 0.35)
            m = m & (tex.alpha[py, px] >= 0.5)
        upd = m & (dep < sub)
        sub[upd] = dep[upd]
        reg[upd] = col[upd]
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if label and title:
        ImageDraw.Draw(im).text((10, 8), title, fill=(30, 30, 30) if not night else (230, 230, 230))
    return im


def atlas_view(texdir, asset, man, size):
    p = tex_path(texdir, asset, "BaseColor")
    im = Image.open(p).convert("RGBA")
    S = im.size[0]
    bg = Image.new("RGBA", im.size, (255, 0, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB").resize((size[1], size[1]), Image.LANCZOS)
    k = size[1] / S
    d = ImageDraw.Draw(im)
    if man and man.get("atlas"):
        for name, c in man["atlas"]["cells"].items():
            x, y, w, h = c["rect"]
            d.rectangle([x * k, y * k, (x + w) * k, (y + h) * k], outline=(255, 255, 0))
            d.text((x * k + 3, y * k + 2), name, fill=(255, 255, 0))
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--views", default="front,iso2,back,iso")
    ap.add_argument("--size", default="900x700")
    ap.add_argument("--zoom")
    ap.add_argument("--box")
    ap.add_argument("--photo")
    ap.add_argument("--mode", default="color", choices=["color", "normal", "ctrl", "emissive"])
    ap.add_argument("--night", action="store_true")
    ap.add_argument("--nolabel", action="store_true")
    a = ap.parse_args()
    asset, M, texdir, man = load_asset(a.path)
    size = tuple(int(s) for s in a.size.lower().split("x"))
    zoom = tuple(float(s) for s in a.zoom.split(",")) if a.zoom else None
    box = tuple(float(s) for s in a.box.split(",")) if a.box else None
    tex_main = Tex(texdir, asset, False, a.mode)
    tex_l2 = None
    ims = []
    for v in a.views.split(","):
        v = v.strip()
        if v == "atlas":
            ims.append(atlas_view(texdir, asset, man, size)); continue
        if v in PRESET:
            yaw, pitch = PRESET[v]
        else:
            yaw, pitch = 0.0, 8.0
            for tok in v.split(":"):
                if tok.startswith("yaw"):
                    yaw = float(tok[3:])
                elif tok.startswith("pitch"):
                    pitch = float(tok[5:])
        if v == "lod1":
            parts, tex = [(M.get("lod1"), "s"), (M.get("lod1_win"), "window"), (M.get("lod1_gls"), "glass")], tex_main
        elif v == "lod2":
            tex_l2 = tex_l2 or Tex(texdir, asset, True, a.mode)
            parts, tex = [(M.get("lod2"), "s"), (M.get("lod2_win"), "window")], tex_l2
        else:
            parts, tex = [(M.get("main"), "s"), (M.get("win"), "window"), (M.get("gls"), "glass")], tex_main
        title = f"{v}  yaw {yaw:g} pitch {pitch:g}" + (f"  zoom {a.zoom}" if zoom else "")
        ims.append(render(parts, tex, yaw, pitch, size, title, zoom, box, a.night, not a.nolabel))
    if a.photo:
        ph = Image.open(a.photo).convert("RGB")
        ph = ph.resize((int(ph.size[0] * size[1] / ph.size[1]), size[1]), Image.LANCZOS)
        ims.insert(0, ph)
    Wt = sum(im.size[0] for im in ims); Ht = max(im.size[1] for im in ims)
    sheet = Image.new("RGB", (Wt, Ht), "white")
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0)); x += im.size[0]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out)
    print(f"[render] {a.out}  ({Wt}x{Ht}, {len(ims)} views)")


if __name__ == "__main__":
    main()
