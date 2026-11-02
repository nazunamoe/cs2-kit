# -*- coding: utf-8 -*-
"""OBJ·PNG 읽기 공통 (check.py, render.py 가 씀). OBJ 는 Y-up (x, z, -y) 로 저장된 것을 Z-up 으로 되돌림."""
import glob
import json
import os
import re

import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass

SUFFIXES = {"main": "", "win": "_Win", "gls": "_Gls", "lod1": "_LOD1", "lod1_win": "_LOD1_Win",
            "lod1_gls": "_LOD1_Gls", "lod2": "_LOD2", "lod2_win": "_LOD2_Win"}
MAPS = ["BaseColor", "ControlMask", "MaskMap", "Normal", "Emissive"]


class Mesh:
    def __init__(self, verts, faces, uvs):
        self.verts = verts          # (N,3) Z-up
        self.faces = faces          # list of index lists (보통 4개)
        self.uvs = uvs              # list of (k,2)

    @property
    def tri_count(self):
        return sum(len(f) - 2 for f in self.faces)

    def quads(self):
        """(F,4,3) — 삼각형은 마지막 점을 반복해 사각형 모양으로."""
        out = np.zeros((len(self.faces), 4, 3))
        for i, f in enumerate(self.faces):
            idx = list(f) + [f[-1]] * (4 - len(f)) if len(f) < 4 else list(f[:4])
            out[i] = self.verts[idx]
        return out


def load_obj(path):
    V, VT, F, FU = [], [], [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                x, y, z = map(float, line.split()[1:4])
                V.append((x, -z, y))
            elif line.startswith("vt "):
                VT.append(tuple(map(float, line.split()[1:3])))
            elif line.startswith("f "):
                vi, ti = [], []
                for tok in line.split()[1:]:
                    p = tok.split("/")
                    vi.append(int(p[0]) - 1)
                    ti.append(int(p[1]) - 1 if len(p) > 1 and p[1] else -1)
                F.append(vi)
                FU.append(ti)
    V = np.array(V, float).reshape(-1, 3)
    VT = np.array(VT, float).reshape(-1, 2)
    uvs = [VT[t] if (len(VT) and min(t) >= 0) else np.zeros((len(t), 2)) for t in FU]
    faces = []
    out_uvs = []
    for f, uv in zip(F, uvs):          # 5각형 이상은 부채꼴로 쪼갬
        if len(f) <= 4:
            faces.append(f); out_uvs.append(uv)
        else:
            for k in range(1, len(f) - 1):
                faces.append([f[0], f[k], f[k + 1]]); out_uvs.append(uv[[0, k, k + 1]])
    return Mesh(V, faces, out_uvs)


def find_asset(path):
    """폴더(output/<asset>) 또는 그 안 아무 파일 → (asset 이름, OBJ 폴더, 텍스처 폴더)."""
    if os.path.isfile(path):
        path = os.path.dirname(path)
    path = os.path.abspath(path)
    for cand in (os.path.join(path, "_check"), path):
        objs = [o for o in glob.glob(os.path.join(cand, "*.obj"))]
        mains = [o for o in objs if not re.search(r"_(Win|Gls|LOD\d(_Win|_Gls)?)\.obj$", o)]
        if mains:
            asset = os.path.splitext(os.path.basename(sorted(mains, key=len)[0]))[0]
            return asset, cand, path
    sub = [d for d in glob.glob(os.path.join(path, "*")) if os.path.isdir(d)]
    if len(sub) == 1:
        return find_asset(sub[0])
    raise SystemExit(f"no OBJ found: {path}\n  (if only FBX exists: python tools/run_blender.py --fbx2obj {path})")


def load_asset(path):
    asset, objdir, texdir = find_asset(path)
    meshes = {}
    for key, suf in SUFFIXES.items():
        p = os.path.join(objdir, asset + suf + ".obj")
        if os.path.exists(p):
            meshes[key] = load_obj(p)
    man = None
    for mp in (os.path.join(texdir, "manifest.json"), os.path.join(objdir, "manifest.json")):
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as fh:
                man = json.load(fh)
            break
    return asset, meshes, texdir, man


def load_png(path, mode="RGBA"):
    from PIL import Image
    return np.asarray(Image.open(path).convert(mode), np.float32)


def tex_path(texdir, asset, m, lod2=False):
    p = os.path.join(texdir, f"{asset}{'_LOD2' if lod2 else ''}_{m}.png")
    return p if os.path.exists(p) else None
