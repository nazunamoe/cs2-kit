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
import glob
import hashlib
import math
import os
import shutil
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
PRESET = {"front": (0, 8), "back": (180, 8), "left": (90, 8), "right": (-90, 8), "iso": (-35, 22), "iso2": (35, 22),
          "iso3": (145, 22), "iso4": (-145, 22), "top": (0, 89.5), "lod1": (-35, 22), "lod2": (-35, 22)}


def _u8(path, mode="RGBA"):
    return np.asarray(Image.open(path).convert(mode))      # uint8 그대로 (float 변환은 샘플한 픽셀에만)


class Tex:
    """텍스처는 uint8 로 들고, 그릴 때 샘플한 픽셀만 실수로 바꾼다 (4096^2 float 4장 ~1 GB 읽기를 피함)."""

    def __init__(self, texdir, asset, lod2, mode):
        name = {"color": "BaseColor", "normal": "Normal", "ctrl": "ControlMask", "emissive": "Emissive"}[mode]
        p = tex_path(texdir, asset, name, lod2) or tex_path(texdir, asset, name)
        self.img = _u8(p) if p else np.full((4, 4, 4), 255, np.uint8)
        bp = tex_path(texdir, asset, "BaseColor", lod2) or tex_path(texdir, asset, "BaseColor")
        if mode == "color" and p and bp and os.path.abspath(bp) == os.path.abspath(p):
            self.alpha = self.img[..., 3]                  # 같은 PNG 를 두 번 디코드하지 않는다 (4096² 361 ms)
        else:
            self.alpha = _u8(bp)[..., 3] if bp else np.full(self.img.shape[:2], 255, np.uint8)
        npth = tex_path(texdir, asset, "Normal", lod2)
        self.nrm = _u8(npth, "RGB") if (npth and mode == "color") else None
        ep = tex_path(texdir, asset, "Emissive", lod2)
        self.emis = _u8(ep, "RGB") if ep else None
        self.H, self.W = self.img.shape[:2]


def _collect_tris(parts, box):
    """(M,3,3) 삼각형, (M,3,2) UV, (M,) kind. quad 메쉬는 numpy 로 한 번에 만든다."""
    T, UV, K = [], [], []
    for mesh, kind in parts:
        if mesh is None or not mesh.faces:
            continue
        faces = mesh.faces
        if box is None and all(len(f) == 4 for f in faces):
            F = np.array(faces, np.int32)
            V = mesh.verts[F]                                  # (n,4,3)
            U = np.asarray(mesh.uvs, dtype=float)              # (n,4,2)
            T.append(np.stack((V[:, [0, 1, 2]], V[:, [0, 2, 3]]), 1).reshape(-1, 3, 3))
            UV.append(np.stack((U[:, [0, 1, 2]], U[:, [0, 2, 3]]), 1).reshape(-1, 3, 2))
            K.append(np.full(2 * len(faces), kind))
            continue
        for f, uv in zip(faces, mesh.uvs):
            q = mesh.verts[f]
            if box is not None:
                c = q.mean(0)
                if not (box[0] <= c[0] <= box[1] and box[2] <= c[1] <= box[3] and box[4] <= c[2] <= box[5]):
                    continue
            for k in range(1, len(f) - 1):
                T.append(q[[0, k, k + 1]][None]); UV.append(np.asarray(uv)[[0, k, k + 1]][None]); K.append(np.full(1, kind))
    if not T:
        return None, None, None
    return np.concatenate(T), np.concatenate(UV), np.concatenate(K)


MAX_FRAG = 1 << 17          # 한 배치의 (삼각형 x 픽셀) 원소 수 상한
_NO_BATCH = False           # 디버그: True 면 모든 삼각형을 기존 순차 경로로
SHADE_CHUNK = 1 << 15       # 지연 셰이딩 한 번에 처리하는 픽셀 수 (메모리 상한)
# 사전 할당된 버퍼 풀 (스레드 안전하지 않음 - render는 단일 스레드에서 호출됨)
_RENDER_BUFFERS = {}


def render(parts, tex, yaw, pitch, size, title="", zoom=None, box=None, night=False,
           label=True, cull=False, mask=False):
    T, UV, KIND = _collect_tris(parts, box)
    if T is None:
        return Image.new("RGB", size, "white")
    if cull:
        d = np.array([-math.sin(math.radians(yaw)) * math.cos(math.radians(pitch)),
                      -math.cos(math.radians(yaw)) * math.cos(math.radians(pitch)),
                      math.sin(math.radians(pitch))])
        n0 = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        front = (n0 @ d) > 0
        keep = np.nonzero(front)[0]
        T, UV, KIND = T[keep], UV[keep], KIND[keep]
        if not len(T):
            return Image.new("RGB", size, "black" if mask else "white")
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
    img = (np.zeros((H, W, 3)) if mask else
           np.ones((H, W, 3)) * (SKY * (0.2 if night else 1)))
    zb = np.full((H, W), np.inf)
    zb_flat, img_flat = zb.reshape(-1), img.reshape(-1, 3)
    owner = np.full(H * W, 0x7FFFFFFF, np.int64)     # 동률일 때 작은 삼각형 인덱스가 이기게 (순차 처리와 동일)

    # ---- 화면 경계 상자 (모든 삼각형을 한 번에)
    xlo = np.floor(X.min(1)); xhi = np.ceil(X.max(1))
    ylo = np.floor(Y.min(1)); yhi = np.ceil(Y.max(1))
    onscr = (xhi >= 0) & (ylo <= H - 1) & (yhi >= 0) & (xlo <= W - 1)
    bx0 = np.clip(xlo, 0, W - 1).astype(np.int32); bx1 = np.clip(xhi, 0, W - 1).astype(np.int32)
    by0 = np.clip(ylo, 0, H - 1).astype(np.int32); by1 = np.clip(yhi, 0, H - 1).astype(np.int32)
    bw = (bx1 - bx0 + 1).astype(np.int64); bh = (by1 - by0 + 1).astype(np.int64)

    ax, bx_, cx_ = X[:, 0], X[:, 1], X[:, 2]
    ay, by, cy_ = Y[:, 0], Y[:, 1], Y[:, 2]
    den = (by - cy_) * (ax - cx_) + (cx_ - bx_) * (ay - cy_)
    good = onscr & (np.abs(den) >= 1e-9) & (bw > 0) & (bh > 0)
    # 아래 계수들은 기존 구현과 '비트 단위로 같은' 결과를 내도록 일부러 곱/나눗셈 순서를 유지한다.
    # (UV 가 아틀라스 셀 경계에 걸친 면에서 1 ULP 차이가 다른 셀을 집어 색이 통째로 바뀐다)
    e0, e1 = by - cy_, cx_ - bx_
    e2, e3 = cy_ - ay, ax - cx_
    den = np.where(good, den, 1.0)
    da0, da1, da2 = dpt[:, 0], dpt[:, 1], dpt[:, 2]
    U0, U1, U2 = UV[:, 0, 0], UV[:, 1, 0], UV[:, 2, 0]
    V0, V1, V2 = UV[:, 0, 1], UV[:, 1, 1], UV[:, 2, 1]
    if tex is not None:
        tW, tH = tex.W, tex.H
        timg = tex.img.reshape(-1, 4)
        talpha = None if (tex.alpha is None or bool((tex.alpha >= 128).all())) else tex.alpha.reshape(-1)
        tnrm = None if tex.nrm is None else tex.nrm.reshape(-1, 3)
        temis = None if tex.emis is None else tex.emis.reshape(-1, 3)
    else:                                              # backface_check 등 텍스처 없는 호출
        tW = tH = 1
        timg = talpha = tnrm = temis = None
    emis_k = (1.0 if night else 0.35) / 255.0
    is_glass = (KIND == "glass")
    opq = np.nonzero(good & ~is_glass)[0]
    glass = np.nonzero(good & is_glass)[0]

    # ---- 불투명: 화면 크기별 버킷 → 배치 (픽셀당 최소 depth, 동률은 작은 인덱스)
    area = bw * bh
    kbit = np.clip(np.ceil(np.log2(np.maximum(area, 1))).astype(np.int32), 0, 12)
    big = opq if _NO_BATCH else opq[area[opq] > 4096]
    for kb in np.unique(kbit[opq]):
        if (1 << kb) > 4096:
            continue
        sel = opq[(kbit[opq] == kb) & (area[opq] <= 4096)]
        if not len(sel):
            continue
        K = 1 << int(kb)
        step = max(1, min(len(sel), MAX_FRAG // K))
        for c0 in range(0, len(sel), step):
            ids = sel[c0:c0 + step]
            n_ids = len(ids)
            # 버퍼를 각 배치마다 적절한 크기로 할당 (단순화, 정확성 우선)
            bwv = bw[ids][:, None]
            bhv = bh[ids][:, None]
            kk = np.arange(K, dtype=np.int32)[None, :]
            dx = np.minimum(kk % bwv, bwv - 1)
            dy = np.minimum(kk // bhv, bhv - 1)
            valid = kk < bwv * bhv
            pxs = bx0[ids][:, None] + dx
            pys = by0[ids][:, None] + dy
            ex = pxs + 0.5 - cx_[ids][:, None]
            ey = pys + 0.5 - cy_[ids][:, None]
            dv = den[ids][:, None]
            w0 = ((e0[ids][:, None] * ex) + (e1[ids][:, None] * ey)) / dv
            w1 = ((e2[ids][:, None] * ex) + (e3[ids][:, None] * ey)) / dv
            w2 = 1 - w0 - w1
            ins = valid & (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not ins.any():
                continue
            dep = w0 * da0[ids][:, None] + w1 * da1[ids][:, None] + w2 * da2[ids][:, None]
            pix = pys * W + pxs
            pix_flat = pix.ravel()
            prev = zb_flat[pix_flat]
            prev_own = owner[pix_flat]
            dep_flat = dep.ravel()
            tri_row = np.broadcast_to(ids[:, None], pix.shape).ravel()
            vis_flat = ins.ravel() & ((dep_flat < prev) | ((dep_flat == prev) & (tri_row < prev_own)))
            vis = vis_flat.reshape(pix.shape)
            if talpha is not None:
                u = w0 * U0[ids][:, None] + w1 * U1[ids][:, None] + w2 * U2[ids][:, None]
                v = w0 * V0[ids][:, None] + w1 * V1[ids][:, None] + w2 * V2[ids][:, None]
                tpx = np.clip((u * tW).astype(np.int32), 0, tW - 1)
                tpy = np.clip(((1 - v) * tH).astype(np.int32), 0, tH - 1)
                flat = tpy * tW + tpx
                vis &= talpha[flat] >= 128
            fidx = np.nonzero(vis.ravel())[0]
            if not len(fidx):
                continue
            depv = dep.ravel()[fidx]; pixv = pix_flat[fidx]
            o = np.lexsort((fidx, depv, pixv))          # 픽셀 → depth → 먼저 온 삼각형
            ps = pixv[o]
            first = np.empty(len(ps), bool); first[0] = True
            np.not_equal(ps[1:], ps[:-1], out=first[1:])
            win = o[first]
            wpix = pixv[win]
            zb_flat[wpix] = depv[win]
            owner[wpix] = ids[fidx[win] // K]

    # ---- 큰 불투명 삼각형: depth 와 소유 삼각형만 기록 (셰이딩은 아래에서 화면 픽셀당 한 번)
    own2 = owner.reshape(H, W)
    # 벡터화: 모든 큰 삼각형을 한 번에 처리
    if len(big) > 0:
        big = big.astype(np.int32)
        # 각 삼각형의 bbox를 이용한 벡터화된 접근
        for i in big:
            x0, x1 = int(bx0[i]), int(bx1[i])
            y0, y1 = int(by0[i]), int(by1[i])
            # 메모리 효율적인 슬라이스 처리
            gx = np.arange(x0, x1 + 1, dtype=np.float32) + 0.5
            gy = np.arange(y0, y1 + 1, dtype=np.float32) + 0.5
            # 브로드캐스팅으로 한 번에 계산
            gx_cx = gx[None, :] - cx_[i]
            gy_cy = gy[:, None] - cy_[i]
            w0 = (e0[i] * gx_cx + e1[i] * gy_cy) / den[i]
            w1 = (e2[i] * gx_cx + e3[i] * gy_cy) / den[i]
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not m.any():
                continue
            dep = w0 * da0[i] + w1 * da1[i] + w2 * da2[i]
            sub = zb[y0:y1 + 1, x0:x1 + 1]
            m &= dep < sub
            if talpha is not None and not mask:
                ys, xs = np.nonzero(m)
                if not len(ys):
                    continue
                a0, a1, a2 = w0[ys, xs], w1[ys, xs], w2[ys, xs]
                u = a0 * U0[i] + a1 * U1[i] + a2 * U2[i]
                v = a0 * V0[i] + a1 * V1[i] + a2 * V2[i]
                tpx = np.clip((u * tW).astype(np.int64), 0, tW - 1)
                tpy = np.clip(((1 - v) * tH).astype(np.int64), 0, tH - 1)
                keep = talpha[tpy * tW + tpx] >= 128
                ys, xs = ys[keep], xs[keep]
                sub[ys, xs] = dep[ys, xs]
                own2[y0:y1 + 1, x0:x1 + 1][ys, xs] = i
                continue
            sub[m] = dep[m]
            own2[y0:y1 + 1, x0:x1 + 1][m] = i

    # ---- 지연 셰이딩: 보이는 픽셀마다 소유 삼각형으로 무게중심 → UV → 텍스처를 한 번만 계산한다.
    # (가려질 면을 칠하지 않는다. 식과 연산 순서는 삼각형별 계산과 같아 결과가 비트 단위로 같다)
    seen = np.nonzero(owner != 0x7FFFFFFF)[0]
    if mask:
        img_flat[seen] = 1.0
        seen = seen[:0]
    # 사전 할당된 버퍼로 청크 처리 (메모리 할당 감소)
    max_chunk = min(SHADE_CHUNK, len(seen))
    if max_chunk > 0:
        tri_buf = np.empty(max_chunk, np.int64)
        ex_buf = np.empty(max_chunk, np.float32)
        ey_buf = np.empty(max_chunk, np.float32)
        dv_buf = np.empty(max_chunk, np.float32)
        w0_buf = np.empty(max_chunk, np.float32)
        w1_buf = np.empty(max_chunk, np.float32)
        w2_buf = np.empty(max_chunk, np.float32)
        u_buf = np.empty(max_chunk, np.float32)
        v_buf = np.empty(max_chunk, np.float32)
        tpx_buf = np.empty(max_chunk, np.float32)
        tpy_buf = np.empty(max_chunk, np.float32)
        flat_buf = np.empty(max_chunk, np.float32)
        bump_buf = np.empty(max_chunk, np.float32)
        sh_buf = np.empty(max_chunk, np.float32)
        for c0 in range(0, len(seen), SHADE_CHUNK):
            pix = seen[c0:c0 + SHADE_CHUNK]
            chunk_size = len(pix)
            tri = owner[pix]
            tri_buf[:chunk_size] = tri
            ex_buf[:chunk_size] = pix % W + 0.5 - cx_[tri]
            ey_buf[:chunk_size] = pix // W + 0.5 - cy_[tri]
            dv_buf[:chunk_size] = den[tri]
            np.multiply(e0[tri], ex_buf[:chunk_size], out=w0_buf[:chunk_size])
            np.add(w0_buf[:chunk_size], e1[tri] * ey_buf[:chunk_size], out=w0_buf[:chunk_size])
            np.divide(w0_buf[:chunk_size], dv_buf[:chunk_size], out=w0_buf[:chunk_size])
            np.multiply(e2[tri], ex_buf[:chunk_size], out=w1_buf[:chunk_size])
            np.add(w1_buf[:chunk_size], e3[tri] * ey_buf[:chunk_size], out=w1_buf[:chunk_size])
            np.divide(w1_buf[:chunk_size], dv_buf[:chunk_size], out=w1_buf[:chunk_size])
            np.subtract(1.0, w0_buf[:chunk_size], out=w2_buf[:chunk_size])
            np.subtract(w2_buf[:chunk_size], w1_buf[:chunk_size], out=w2_buf[:chunk_size])
            np.multiply(w0_buf[:chunk_size], U0[tri], out=u_buf[:chunk_size])
            np.add(u_buf[:chunk_size], w1_buf[:chunk_size] * U1[tri], out=u_buf[:chunk_size])
            np.add(u_buf[:chunk_size], w2_buf[:chunk_size] * U2[tri], out=u_buf[:chunk_size])
            np.multiply(w0_buf[:chunk_size], V0[tri], out=v_buf[:chunk_size])
            np.add(v_buf[:chunk_size], w1_buf[:chunk_size] * V1[tri], out=v_buf[:chunk_size])
            np.add(v_buf[:chunk_size], w2_buf[:chunk_size] * V2[tri], out=v_buf[:chunk_size])
            np.multiply(u_buf[:chunk_size], tW, out=tpx_buf[:chunk_size])
            np.clip(tpx_buf[:chunk_size], 0, tW - 1, out=tpx_buf[:chunk_size])
            np.subtract(1.0, v_buf[:chunk_size], out=v_buf[:chunk_size])
            np.multiply(v_buf[:chunk_size], tH, out=tpy_buf[:chunk_size])
            np.clip(tpy_buf[:chunk_size], 0, tH - 1, out=tpy_buf[:chunk_size])
            np.multiply(tpy_buf[:chunk_size], tW, out=flat_buf[:chunk_size])
            np.add(flat_buf[:chunk_size], tpx_buf[:chunk_size], out=flat_buf[:chunk_size])
            flat_chunk = flat_buf[:chunk_size].astype(np.int64)
            if tnrm is not None:
                nn = tnrm[flat_chunk] / 127.5 - 1
                np.multiply(nn[:, 0], 0.4, out=bump_buf[:chunk_size])
                np.subtract(bump_buf[:chunk_size], nn[:, 1] * 0.5, out=bump_buf[:chunk_size])
                np.multiply(bump_buf[:chunk_size], 0.6, out=bump_buf[:chunk_size])
                np.add(bump_buf[:chunk_size], 1.0, out=bump_buf[:chunk_size])
            else:
                bump_buf[:chunk_size] = 1.0
            np.multiply(shade[tri], bump_buf[:chunk_size], out=sh_buf[:chunk_size])
            np.divide(sh_buf[:chunk_size], 255.0, out=sh_buf[:chunk_size])
            if timg is not None:
                col = sh_buf[:chunk_size, None] * timg[flat_chunk][:, :3]
            else:
                col = sh_buf[:chunk_size, None] * 255.0
            if temis is not None:
                col = col + temis[flat_chunk] * emis_k
            img_flat[pix] = col

    # ---- 유리: 불투명 셰이딩이 끝난 뒤 순서대로 섞는다 (mask 모드에서는 불투명처럼 덮는다)
    for i in glass:
        i = int(i)
        x0, x1 = int(bx0[i]), int(bx1[i])
        y0, y1 = int(by0[i]), int(by1[i])
        gx = np.arange(x0, x1 + 1) + 0.5
        gy = np.arange(y0, y1 + 1) + 0.5
        w0 = (e0[i] * (gx[None, :] - cx_[i]) + e1[i] * (gy[:, None] - cy_[i])) / den[i]
        w1 = (e2[i] * (gx[None, :] - cx_[i]) + e3[i] * (gy[:, None] - cy_[i])) / den[i]
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        dep = w0 * da0[i] + w1 * da1[i] + w2 * da2[i]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        reg = img[y0:y1 + 1, x0:x1 + 1]
        upd = m & (dep < sub)
        if mask:
            sub[upd] = dep[upd]
            reg[upd] = 1.0
            continue
        reg[upd] = reg[upd] * 0.62 + GLS * 0.38 * (0.3 if night else 1)
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


_CTX = {}


def _view_job(arg):
    """한 뷰를 그린다 (프로세스마다 에셋·텍스처를 한 번만 읽어 재사용)."""
    (v, yaw, pitch, title), (path, size, zoom, box, night, label, mode) = arg
    if path not in _CTX:
        asset, M, texdir, man = load_asset(path)
        _CTX[path] = dict(asset=asset, M=M, texdir=texdir, man=man, tex={})
    c = _CTX[path]
    if v == "atlas":
        return atlas_view(c["texdir"], c["asset"], c["man"], size)
    M = c["M"]
    lod2 = v == "lod2"
    if lod2 not in c["tex"]:
        c["tex"][lod2] = Tex(c["texdir"], c["asset"], lod2, mode)
    tex = c["tex"][lod2]
    if v == "lod1":
        parts = [(M.get("lod1"), "s"), (M.get("lod1_win"), "window"), (M.get("lod1_gls"), "glass")]
    elif lod2:
        parts = [(M.get("lod2"), "s"), (M.get("lod2_win"), "window")]
    else:
        parts = [(M.get("main"), "s"), (M.get("win"), "window"), (M.get("gls"), "glass")]
    return render(parts, tex, yaw, pitch, size, title, zoom, box, night, label)


def _file_sig(h, path):
    """Content hash 대신 (이름, 크기, mtime). 4096² PNG 12장을 매번 읽지 않는다."""
    st = os.stat(path)
    h.update(f"{os.path.basename(path)}:{st.st_size}:{st.st_mtime_ns}".encode("utf-8"))


RENDER_CACHE_VERSION = 3


def render_cache_key(args):
    """Hash render inputs; texture-only changes invalidate, identical rerenders hit."""
    h = hashlib.sha256()
    for value in (str(RENDER_CACHE_VERSION), args.views, args.size, args.zoom or "", args.box or "", args.mode,
                  str(args.night), str(args.nolabel), os.path.abspath(args.path)):
        h.update(value.encode("utf-8"))
    path = os.path.abspath(args.path)
    asset_dir = path if os.path.isdir(path) else os.path.dirname(path)
    files = sorted(glob.glob(os.path.join(asset_dir, "*.png")) +
                   glob.glob(os.path.join(asset_dir, "_check", "*.obj")))
    for f in files:
        _file_sig(h, f)
    if args.photo and os.path.isfile(args.photo):
        _file_sig(h, os.path.abspath(args.photo))
    return h.hexdigest()


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
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    cache_dir = os.path.join(proj.ROOT, "previews", "_render_cache")
    cache_file = None
    if not a.no_cache:
        try:
            cache_file = os.path.join(cache_dir, render_cache_key(a) + ".png")
            if os.path.isfile(cache_file):
                os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
                shutil.copyfile(cache_file, a.out)          # 같은 PNG: 디코드·재압축 없이 복사
                print(f"[render] cached {a.out}")
                return
        except Exception:
            cache_file = None
    asset, M, texdir, man = load_asset(a.path)
    _CTX[a.path] = dict(asset=asset, M=M, texdir=texdir, man=man, tex={})    # 뷰 작업이 다시 읽지 않게
    size = tuple(int(s) for s in a.size.lower().split("x"))
    zoom = tuple(float(s) for s in a.zoom.split(",")) if a.zoom else None
    box = tuple(float(s) for s in a.box.split(",")) if a.box else None
    jobs = []
    for v in a.views.split(","):
        v = v.strip()
        if v == "atlas":
            jobs.append((v, None, None, None)); continue
        if v in PRESET:
            yaw, pitch = PRESET[v]
        else:
            yaw, pitch = 0.0, 8.0
            for tok in v.split(":"):
                if tok.startswith("yaw"):
                    yaw = float(tok[3:])
                elif tok.startswith("pitch"):
                    pitch = float(tok[5:])
        title = f"{v}  yaw {yaw:g} pitch {pitch:g}" + (f"  zoom {a.zoom}" if zoom else "")
        jobs.append((v, yaw, pitch, title))
    common = (a.path, size, zoom, box, a.night, not a.nolabel, a.mode)
    ims = None
    n_real = sum(1 for j in jobs if j[1] is not None)
    if n_real >= 2 and os.environ.get("RENDER_SERIAL") != "1":
        # 뷰마다 스레드로 병렬. 래스터라이저는 큰 numpy 연산이 대부분이라 GIL 을 놓는 시간이 길고,
        # 프로세스 풀과 달리 에셋·4096² 텍스처를 한 번만 읽는다 (프로세스 기동 + 재로드가 렌더보다 길었다).
        try:
            from concurrent.futures import ThreadPoolExecutor
            for lod2 in {j[0] == "lod2" for j in jobs if j[1] is not None}:      # 텍스처는 미리 한 번
                _CTX[a.path]["tex"][lod2] = Tex(texdir, asset, lod2, a.mode)
            with ThreadPoolExecutor(max_workers=min(n_real, os.cpu_count() or 2)) as ex:
                ims = list(ex.map(_view_job, [(j, common) for j in jobs]))
        except Exception as e:  # noqa
            print(f"[render] parallel failed ({type(e).__name__}); serial")
            ims = None
    if ims is None:
        ims = [_view_job((j, common)) for j in jobs]
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
    if cache_file:
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            sheet.save(cache_file)
        except Exception:
            pass
    print(f"[render] {a.out}  ({Wt}x{Ht}, {len(ims)} views)")


if __name__ == "__main__":
    main()
