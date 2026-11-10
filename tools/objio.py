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

    def padded(self):
        """(F,4) 인덱스 · (F,) 꼭짓점 수 · (F,4,2) UV. 삼각형은 마지막 점을 반복해 채운다.
        한 번 만들어 재사용한다 (faces/uvs 는 바꾸지 않는다; verts 는 바뀌어도 된다)."""
        if not hasattr(self, "_pad"):
            n = len(self.faces)
            L = np.fromiter((len(f) for f in self.faces), np.int64, n)
            if n and L.min() == 4 and L.max() == 4:
                F = np.array(self.faces, np.int64)
            else:
                F = np.array([(list(f) + [f[-1]] * 3)[:4] for f in self.faces], np.int64).reshape(-1, 4)
            UV = None
            if len(self.uvs) == n and all(len(u) == k for u, k in zip(self.uvs, L.tolist())):
                if n and L.min() == 4 and L.max() == 4:
                    UV = np.asarray(self.uvs, float).reshape(-1, 4, 2)
                else:
                    UV = np.zeros((n, 4, 2))
                    for k in np.unique(L).tolist():
                        rows = np.nonzero(L == k)[0]
                        part = np.asarray([self.uvs[i] for i in rows.tolist()], float).reshape(len(rows), k, 2)
                        UV[rows, :min(k, 4)] = part[:, :4]
                        if k < 4:
                            UV[rows, k:] = part[:, -1:]
            self._pad = (F, L, UV)
        return self._pad

    def quads(self):
        """(F,4,3) — 삼각형은 마지막 점을 반복해 사각형 모양으로."""
        return np.asarray(self.verts, float)[self.padded()[0]]


OBJ_CACHE_VERSION = 1
OBJ_CACHE_MIN_BYTES = 256 * 1024          # 이보다 작으면 텍스트 파싱이 더 빠르다


def _load_obj_cache(path):
    """cs2kit.export_asset 이 남긴 <obj>.npz 사이드카. 키가 어긋나면 None → 텍스트 파싱으로 폴백."""
    cf = path + ".npz"
    if not os.path.exists(cf):
        return None
    try:
        st = os.stat(path)
        with np.load(cf, allow_pickle=False) as z:
            if z["key"].item() != f"{OBJ_CACHE_VERSION}:{st.st_size}:{st.st_mtime_ns}":
                return None
            V, F, FL, UVT, UVO = z["V"], z["F"], z["FL"], z["UVT"], z["UVO"]
    except Exception:                                     # noqa: BLE001 - 깨진 캐시는 없는 것으로 친다
        return None
    n = len(F)
    if n and FL.min() == 4 and FL.max() == 4 and UVT.shape[0] == n * 4:   # 대부분의 메쉬: quad 고정
        faces = F.tolist()
        uvs = list(UVT.reshape(n, 4, 2))                  # 면마다 (4,2) 뷰
        return Mesh(V, faces, uvs)
    faces = [None] * n
    uvs = [None] * n
    for i in range(n):
        k = int(FL[i])
        faces[i] = F[i, :k].tolist()
        o = int(UVO[i])
        uvs[i] = UVT[o:o + k]
    return Mesh(V, faces, uvs)


def load_obj(path):
    try:
        # 작은 OBJ 는 텍스트 파싱이 더 빠르다(npz 로드 고정비 ~10 ms). 큰 메쉬만 캐시를 쓴다.
        if os.path.getsize(path) >= OBJ_CACHE_MIN_BYTES:
            cached = _load_obj_cache(path)
            if cached is not None:
                return cached
    except OSError:
        pass
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
