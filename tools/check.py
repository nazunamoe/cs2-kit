# -*- coding: utf-8 -*-
"""
check.py — CS2 에셋 검증 (생성기와 무관: output/<asset>/ 의 OBJ + PNG 만 봄)

사용:  python tools/check.py output/<asset>            (폴더 하나)
       python tools/check.py output                     (안의 에셋 전부)
옵션:  --list N   문제 예시를 N 개까지 출력 (기본 5)
       --json report.json   결과 저장
       --fast     같은 평면 겹침을 메인만 검사
       --ray 1.5  창문 앞 가림 검사 거리 (m)
종료 코드: 오류 있으면 1, 경고만 있으면 0

검사 항목 (오류 = ✗, 경고 = !)
  ✗ 이름 규칙 <Name>_L<lvl>_<w>x<d>, 이름 안 밑줄 / 필수 파일
  ✗ 바닥 z < 0, 피벗이 바닥 중앙에서 5 cm 이상 벗어남, 지면(z=0) 아래 보는 면
  ✗ LOD1 >= 메인 50%, LOD2 > 500 tris
  ✗ 같은 평면 겹침 (방향 같은 면끼리, 회전 면 포함 — 실제 다각형 교차 넓이 1e-3 m² 초과)
  ✗ 창문 UV: 0~1 밖, 서로 겹침, 가로세로 비율 불일치(1%)
  ✗ 창문 앞 가림: 창 가운데·두 모서리에서 법선 방향으로 --ray m 안에 불투명 면 (BaseColor 알파 50% 기준 — 알파로 뚫린 곳은 통과)
  ! 창문 뒤 벽 없음 (뒤 1 m 안에 메인 면이 없음 → 방향이 뒤집혔거나 떠 있는 창)
  ✗ 텍스처: 정사각·2의 거듭제곱·5종 같은 크기, LOD2 텍스처가 메인보다 작거나 같음
  ✗ (manifest 있으면) 면 UV 가 아틀라스 칸 하나 안에 있음
  ! 텍셀 밀도(px/m) 분포, 1 m² 넘는 면 중 64 px/m 미만 비율
  ! 퇴화 면, 평면이 아닌 사각형, 메인 tris 9.5만 초과, 로트 6x6 초과(시그니처로)
"""
import argparse
import json
import math
import os
import re
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)
from objio import MAPS, load_asset, tex_path  # noqa: E402
from agent_actions import agent_summary as _agent_summary  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass

NAME_RE = re.compile(r"^([A-Za-z0-9]+)_L(\d)_(\d+)x(\d+)$")


# ---------------------------------------------------------------- 기하
def normals(Q):
    n = np.cross(Q[:, 1] - Q[:, 0], Q[:, 3] - Q[:, 0]) + np.cross(Q[:, 2] - Q[:, 1], Q[:, 0] - Q[:, 1])
    a = np.linalg.norm(n, axis=1)
    return n / np.maximum(a, 1e-12)[:, None], a / 2


def _clip_vectorized(poly_arr, a, b):
    """여러 폴리곤을 한 번에 클리핑 (배치 처리).
    poly_arr: (n, m, 2) - 각 폴리곤은 (m, 2) 크기, 패딩된 직사각형 형태.
    반환: (n, m_out, 2) - 클리핑된 폴리곤들 (각각 다른 크기 가능하므로 리스트 반환)"""
    # 이 함수는 벡터화하기 복잡하므로, 대신 Python 루프를 최적화
    pass


def _clip(poly, a, b):
    out = []
    side = lambda p: (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def _area(P):
    return 0.5 * abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P))))


def _ccw(P):
    s = sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
    return P if s > 0 else P[::-1]


def coplanar(mesh, min_area=1e-3):
    """같은 방향·같은 평면(1 mm) 위에서 실제로 겹치는 면 쌍. 반대 방향 면끼리는 허용.

    평면 묶기·투영·경계 상자·후보 쌍 찾기는 numpy 로 한 번에 하고, 상자가 실제로 겹치는 쌍만
    다각형 교차(_clip)를 계산한다."""
    Q = mesh.quads()
    N, A = normals(Q)
    live = np.nonzero(A >= 1e-8)[0]
    if not len(live):
        return []
    nkey = np.round(N[live], 3) + 0.0                        # -0.0 -> 0.0
    dkey = np.round(np.einsum("ij,ij->i", N[live], Q[live].mean(1)), 3) + 0.0
    _, first, inv = np.unique(nkey, axis=0, return_index=True, return_inverse=True)
    inv = np.ravel(inv)
    by_normal = np.argsort(inv, kind="stable")
    bounds = np.concatenate(([0], np.cumsum(np.bincount(inv, minlength=len(first)))))
    bad = []
    for g in np.argsort(first, kind="stable"):               # 법선이 처음 나온 순서 (예시 출력 순서 유지)
        members = by_normal[bounds[g]:bounds[g + 1]]          # live 안의 위치, 면 번호 오름차순
        if len(members) < 2:
            continue
        n = nkey[members[0]]
        nv = n / np.linalg.norm(n)
        if abs(nv[2]) > 0.99:
            u, v = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
        else:
            u = np.cross([0, 0, 1.0], nv); u /= np.linalg.norm(u); v = np.cross(nv, u)
        dm = dkey[members]
        o = np.argsort(dm, kind="stable")
        members, dm = members[o], dm[o]
        k = 0
        while k < len(members):
            # 반올림 경계 보정: 평면 거리 키가 1 mm 차이 나는 이웃 그룹도 합침
            k1 = k + 1
            while k1 < len(members) and dm[k1] - dm[k] <= 0.0015:
                k1 += 1
            idx = live[members[k:k1]]
            k = k1
            if len(idx) >= 2:
                _coplanar_group(Q, idx, u, v, n, min_area, bad)
    return bad


def _coplanar_group(Q, idx, u, v, n, min_area, bad):
    """한 평면 위의 면들(idx)에서 겹치는 쌍을 bad 에 추가.
    최적화: 경계 상자 테스트를 벡터화하고, 실제 클리핑이 필요한 쌍만 선별."""
    pts = Q[idx]                                              # (m,4,3)
    px = pts[..., 0] * u[0] + pts[..., 1] * u[1] + pts[..., 2] * u[2]
    py = pts[..., 0] * v[0] + pts[..., 1] * v[1] + pts[..., 2] * v[2]
    step = np.linalg.norm(pts - np.roll(pts, 1, axis=1), axis=2)
    simple = (step[:, 1:] > 1e-9).all(1) & (step[:, 0] >= 1e-9)
    t = px * np.roll(py, -1, axis=1) - np.roll(px, -1, axis=1) * py
    flip = (((t[:, 0] + t[:, 1]) + t[:, 2]) + t[:, 3]) <= 0
    bb = np.stack((px.min(1), py.min(1), px.max(1), py.max(1)), 1)
    polys = {}

    def poly(i):
        if i not in polys:
            if simple[i]:
                P = list(zip(px[i].tolist(), py[i].tolist()))
                polys[i] = P[::-1] if flip[i] else P
            else:
                polys[i] = _ccw([(float(q @ u), float(q @ v)) for q in _uniq(Q[idx[i]])])
        return polys[i]

    # 벡터화된 경계 상자 중첩 테스트
    x0s = bb[:, 0]
    x1s = bb[:, 2]
    y0s = bb[:, 1]
    y1s = bb[:, 3]

    order = np.argsort(x0s, kind="stable")
    x0s_ord = x0s[order]
    x1s_ord = x1s[order]
    y0s_ord = y0s[order]
    y1s_ord = y1s[order]

    # 각 i에 대해 x0[j] < x1[i] 인 j의 범위 찾기 (이진 검색)
    end_idx = np.searchsorted(x0s_ord, x1s_ord, side="left")

    limit = 1 << 22
    for oi, i in enumerate(order):
        # x-축 겹침: j > oi 이면서 x0[j] < x1[i]
        start = oi + 1
        end = end_idx[oi]
        if start >= end:
            continue

        # y-축 겹침 추가 체크 (벡터화)
        y0_cand = y0s_ord[start:end]
        y1_cand = y1s_ord[start:end]
        hit = (y0s[oi] < y1_cand) & (y0_cand < y1s[oi])
        if not hit.any():
            continue

        j_indices = order[start:end][hit]
        if not len(j_indices):
            continue

        # 후보 쌍들에 대해 실제 클리핑 수행
        Pi = poly(i)
        for j in j_indices:
            Pj = poly(j)
            inter = Pi
            for e in range(len(Pj)):
                inter = _clip(inter, Pj[e], Pj[(e + 1) % len(Pj)])
                if not inter:
                    break
            if inter and _area(inter) > min_area:
                bad.append(dict(faces=(int(idx[i]), int(idx[j])), area=round(_area(inter), 4),
                                at=np.round(Q[idx[i]].mean(0), 2).tolist(), normal=list(n)))


def _uniq(q):
    out = []
    for p in q:
        if not out or np.linalg.norm(p - out[-1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and np.linalg.norm(out[0] - out[-1]) < 1e-9:
        out.pop()
    return out


class RayMesh:
    """메인 메시 삼각형 + 알파 샘플링 (알파로 뚫린 곳은 통과)."""

    def __init__(self, mesh, alpha=None):
        F, L, UVp = mesh.padded()
        if UVp is not None and len(L) and L.min() >= 3 and L.max() <= 4:     # 면마다 (0,1,2) [, (0,2,3)] 를 한 번에
            V = np.asarray(mesh.verts, float)[F]
            two = np.stack((np.ones(len(L), bool), L == 4), 1)                   # 삼각형은 첫 조각만
            self.T = np.stack((V[:, [0, 1, 2]], V[:, [0, 2, 3]]), 1)[two]
            self.UV = np.stack((UVp[:, [0, 1, 2]], UVp[:, [0, 2, 3]]), 1)[two]
        else:
            T, UV = [], []
            for f, uv in zip(mesh.faces, mesh.uvs):
                for k in range(1, len(f) - 1):
                    T.append(mesh.verts[[f[0], f[k], f[k + 1]]]); UV.append(uv[[0, k, k + 1]])
            self.T = np.array(T).reshape(-1, 3, 3)
            self.UV = np.array(UV).reshape(-1, 3, 2)
        self.alpha = alpha
        self.lo = self.T.min(1); self.hi = self.T.max(1)

    def hit(self, o, d, maxd):
        return self.hits(np.asarray([o]), np.asarray([d]), maxd)[0]

    def hits(self, origins, directions, maxd):
        """Nearest opaque hit for each ray, using only AABB candidates in each batch."""
        origins = np.asarray(origins, float)
        directions = np.asarray(directions, float)
        result = np.full(len(origins), np.inf)
        for start in range(0, len(origins), 32):
            O = origins[start:start + 32, None, :]
            D = directions[start:start + 32, None, :]
            end = O + D * maxd
            lo, hi = np.minimum(O, end) - 1e-6, np.maximum(O, end) + 1e-6
            broad = (self.hi[None, :, 0] >= lo[:, :, 0]) & (self.lo[None, :, 0] <= hi[:, :, 0])   # 축별로 (큰 3D 임시 배열 없이)
            for ax in (1, 2):
                broad &= self.hi[None, :, ax] >= lo[:, :, ax]
                broad &= self.lo[None, :, ax] <= hi[:, :, ax]
            candidates = [np.nonzero(row)[0] for row in broad]
            width = max((len(ids) for ids in candidates), default=0)
            if not width:
                continue
            indices = np.zeros((len(O), width), dtype=np.int32)
            valid = np.zeros((len(O), width), dtype=bool)
            for b, ids in enumerate(candidates):
                if len(ids):
                    indices[b, :len(ids)] = ids
                    valid[b, :len(ids)] = True
            T = self.T[indices]
            UV = self.UV[indices]
            v0, v1, v2 = T[:, :, 0], T[:, :, 1], T[:, :, 2]
            e1, e2 = v1 - v0, v2 - v0
            h = np.cross(D, e2)
            a = (e1 * h).sum(2)
            ok = np.abs(a) > 1e-12
            f = np.where(ok, 1.0 / np.where(ok, a, 1), 0)
            s = O - v0
            uu = f * (s * h).sum(2)
            q = np.cross(s, e1)
            vv = f * (q * D).sum(2)
            t = f * (e2 * q).sum(2)
            hitm = valid & ok & (uu >= -1e-9) & (vv >= -1e-9) & (uu + vv <= 1 + 1e-9) & (t > 1e-4) & (t < maxd)
            for b in range(len(O)):
                ids = np.nonzero(hitm[b])[0]
                if not len(ids):
                    continue
                ids = ids[np.argsort(t[b, ids])]
                if self.alpha is None:
                    result[start + b] = t[b, ids[0]]
                    continue
                for i in ids:
                    uv = UV[b, i, 0] * (1 - uu[b, i] - vv[b, i]) + UV[b, i, 1] * uu[b, i] + UV[b, i, 2] * vv[b, i]
                    H, W = self.alpha.shape
                    px = int(np.clip(uv[0] * W, 0, W - 1)); py = int(np.clip((1 - uv[1]) * H, 0, H - 1))
                    if self.alpha[py, px] >= 127.5:
                        result[start + b] = t[b, i]
                        break
        return result


def rect_overlaps(R, eps=1e-7):
    R = np.array(R).reshape(-1, 4)
    out = []
    order = np.argsort(R[:, 0])
    for a in range(len(order)):
        i = order[a]
        for b in range(a + 1, len(order)):
            j = order[b]
            if R[j, 0] >= R[i, 2] - eps:
                break
            if R[i, 1] < R[j, 3] - eps and R[j, 1] < R[i, 3] - eps:
                out.append((int(i), int(j)))
    return out


# ---------------------------------------------------------------- 검사 본체
def check_asset(path, args):
    t0 = time.time()
    asset, M, texdir, man = load_asset(path)
    E, W, info = [], [], {}
    err = lambda k, msg, ex=None: E.append(dict(key=k, msg=msg, examples=(ex or [])[:args.list]))
    warn = lambda k, msg, ex=None: W.append(dict(key=k, msg=msg, examples=(ex or [])[:args.list]))

    # 이름
    m = NAME_RE.match(asset)
    if not m:
        err("name", f"name '{asset}' is not <Name>_L<lvl>_<w>x<d> (no underscore inside Name)")
    lot = (int(m.group(3)), int(m.group(4))) if m else None
    for need in ("main", "win", "lod1", "lod2"):
        if need not in M:
            (err if need in ("main", "lod1", "lod2") else warn)("files", f"{need} OBJ missing")
    if "main" not in M:
        return dict(asset=asset, errors=E, warnings=W, info=info)
    main = M["main"]

    # 크기·피벗·바닥
    V = main.verts
    lo, hi = V.min(0), V.max(0)
    info["size"] = np.round(hi - lo, 2).tolist()
    info["pivot_offset"] = np.round([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2], 3).tolist()
    info["zmin"] = round(float(lo[2]), 4)
    if lo[2] < -1e-3:
        err("zmin", f"lowest z = {lo[2]:.3f} < 0 (below ground)")
    if abs(lo[2]) > 0.05:
        warn("zmin", f"lowest z = {lo[2]:.3f} (building floats above ground)")
    if max(abs(x) for x in info["pivot_offset"]) > 0.05:
        err("pivot", f"pivot is {info['pivot_offset']} m off bottom-center")
    # 이후 예시 좌표는 '생성기 좌표'로 (export_asset 이 피벗을 옮긴 만큼 되돌림 → 생성기 코드의 숫자와 바로 비교 가능)
    sh = (man or {}).get("pivot_shift")
    if sh:
        for mm in M.values():
            mm.verts = mm.verts - np.array([sh[0], sh[1], 0.0])
        info["coords"] = "generator coordinates (before pivot move)"
        V = main.verts
    if max(info["size"][:2]) > 2000 or max(info["size"]) < 1.0:
        err("scale", f"size {info['size']} m - unit scale problem (x100 or x0.01)?")
    Q = main.quads()
    N, A = normals(Q)
    ground_down = np.nonzero((N[:, 2] < -0.99) & (np.abs(Q[:, :, 2].max(1)) < 1e-3))[0]
    if len(ground_down):
        err("ground", f"BOTTOM_FACE: {len(ground_down)} faces at z=0 facing down - add skip=(\"bottom\",)",
            [np.round(Q[i].mean(0), 2).tolist() for i in ground_down])
    degen = np.nonzero(A < 1e-6)[0]
    if len(degen):
        warn("degenerate", f"{len(degen)} zero-area faces", [np.round(Q[i].mean(0), 2).tolist() for i in degen])
    is_quad = np.fromiter((len(f) == 4 for f in main.faces), bool, len(main.faces))
    npl = np.nonzero(is_quad & (A > 1e-6) & (np.abs(np.einsum("ij,ij->i", Q[:, 2] - Q[:, 0], N)) > 2e-3))[0]
    if len(npl):
        warn("nonplanar", f"{len(npl)} non-planar quads", [np.round(Q[i].mean(0), 2).tolist() for i in npl])
    if lot:
        w_need = math.ceil(info["size"][0] / 8.0)
        if lot[0] < w_need:
            warn("lot", f"lot width {lot[0]} cells < building width {info['size'][0]} m / 8 = {w_need}")
        if max(lot) > 6:
            warn("lot", f"lot {lot[0]}x{lot[1]} > 6x6 -> not zonable, register as signature building")

    # tris
    tris = {k: M[k].tri_count for k in M}
    info["tris"] = tris
    info["verts"] = {k: len(M[k].verts) for k in M}
    if "lod1" in M and tris["lod1"] >= 0.5 * tris["main"]:
        err("lod1", f"LOD1_TOO_BIG: LOD1 {tris['lod1']} >= 50% of main {tris['main']} - remove small parts from LOD1")
    if "lod2" in M and tris["lod2"] > 500:
        err("lod2", f"LOD2_TOO_BIG: LOD2 {tris['lod2']} > 500 tris - fewer boxes, use paint")
    if tris["main"] > 95000:
        warn("tris", f"main {tris['main']} tris > 95000 (game performance)")

    # 같은 평면 겹침
    cp_keys = ["main"] if args.fast else [k for k in ("main", "lod1", "lod2", "gls", "lod1_gls", "win") if k in M]
    info["coplanar"] = {}
    for k in cp_keys:
        bad = coplanar(M[k])
        info["coplanar"][k] = len(bad)
        if bad:
            err("coplanar_" + k, f"COPLANAR {k}: {len(bad)} overlapping face pairs on the same plane (z-fighting). example = [center xyz, overlap m2]", [(b["at"], b["area"]) for b in bad])

    # 텍스처
    sizes = {}
    for lod2 in (False, True):
        for mp in MAPS:
            p = tex_path(texdir, asset, mp, lod2)
            if not p:
                (err if mp in ("BaseColor", "Normal", "MaskMap") and not lod2 else warn)(
                    "tex", f"{'LOD2_' if lod2 else ''}{mp}.png missing")
                continue
            with Image.open(p) as im:
                sizes[("LOD2_" if lod2 else "") + mp] = (im.size, im.mode)
    info["textures"] = {k: f"{v[0][0]}x{v[0][1]} {v[1]}" for k, v in sizes.items()}
    for k, ((w, h), mode) in sizes.items():
        if w != h or (w & (w - 1)):
            err("tex", f"{k} {w}x{h} - not square power of two")
    for grp in ("", "LOD2_"):
        s = {v[0] for k, v in sizes.items() if k.startswith(grp) and (grp or not k.startswith("LOD2_"))}
        if len(s) > 1:
            err("tex", f"{grp or 'main '}texture sizes differ {s}")
    if "BaseColor" in sizes and sizes["BaseColor"][1] != "RGBA":
        warn("tex", f"BaseColor is {sizes['BaseColor'][1]} (RGBA needed for alpha cut)")
    if "BaseColor" in sizes and "LOD2_BaseColor" in sizes and sizes["LOD2_BaseColor"][0][0] > sizes["BaseColor"][0][0]:
        err("tex", "LOD2 texture is larger than main")
    alpha = None
    bp = tex_path(texdir, asset, "BaseColor")
    if bp:
        alpha = _alpha_u8(bp)
    if tex_path(texdir, asset, "Normal"):
        from PIL import ImageStat
        with Image.open(tex_path(texdir, asset, "Normal")) as im:      # 채널 평균만 필요: 히스토그램으로 (float 배열 없이)
            nm = np.array(ImageStat.Stat(im.convert("RGB")).mean)
        if nm[2] < 180:
            warn("tex", f"Normal mean {np.round(nm).tolist()} - is it really a normal map (expected ~128,128,255)?")

    # 아틀라스 칸 / 텍셀 밀도
    S = sizes.get("BaseColor", ((1024, 1024), ""))[0][0]
    if man and man.get("atlas"):
        at = man["atlas"]
        rects = {n: c["rect"] for n, c in at["cells"].items()}
        AS = at["size"]
        boxes = np.array([(x / AS, 1 - (y + h) / AS, (x + w) / AS, 1 - y / AS) for x, y, w, h in rects.values()])
        out = []
        e = 1.0 / AS
        if main.uvs and len(boxes):
            UVp = main.padded()[2]
            if UVp is not None:                                   # 채운 점은 마지막 점의 복사라 최소·최대가 같다
                lo_uv, hi_uv = UVp.min(1), UVp.max(1)             # (F,2)
            else:
                lo_uv = np.array([uv.min(0) for uv in main.uvs])
                hi_uv = np.array([uv.max(0) for uv in main.uvs])
            # 면 x 칸 포함 여부를 한 번에 (같은 UV 상자를 쓰는 면이 많으므로 고유 상자만 검사)
            key, inv = np.unique(np.hstack((lo_uv, hi_uv)), axis=0, return_inverse=True)
            inside = ((boxes[None, :, 0] - e <= key[:, None, 0]) & (boxes[None, :, 1] - e <= key[:, None, 1]) &
                      (boxes[None, :, 2] + e >= key[:, None, 2]) & (boxes[None, :, 3] + e >= key[:, None, 3])).any(1)
            out = [np.round(Q[i].mean(0), 2).tolist() for i in np.nonzero(~inside[np.ravel(inv)])[0]]
        elif main.uvs:
            out = [np.round(Q[i].mean(0), 2).tolist() for i in range(len(main.uvs))]
        if out:
            err("atlas", f"ATLAS_UV: {len(out)} faces with UV outside a single atlas cell (neighbour color bleeds)", out)
    def _uvarea(uv):
        a, b = uv[2] - uv[0], (uv[3] if len(uv) > 3 else uv[2]) - uv[1]
        return 0.5 * abs(a[0] * b[1] - a[1] * b[0]) if len(uv) > 3 else 0.5 * abs((uv[1] - uv[0])[0] * a[1] - (uv[1] - uv[0])[1] * a[0])
    _, FLn, UVp = main.padded()
    if UVp is not None and len(FLn) and FLn.min() >= 3:
        ua, ub, uc = UVp[:, 2] - UVp[:, 0], UVp[:, 3] - UVp[:, 1], UVp[:, 1] - UVp[:, 0]
        uva = np.where(FLn > 3, 0.5 * np.abs(ua[:, 0] * ub[:, 1] - ua[:, 1] * ub[:, 0]),
                       0.5 * np.abs(uc[:, 0] * ua[:, 1] - uc[:, 1] * ua[:, 0]))
    else:
        uva = np.array([_uvarea(uv) for uv in main.uvs])
    dens = np.sqrt(np.maximum(uva, 0) * S * S / np.maximum(A, 1e-9))
    big = (A > 1.0) & (uva > 1e-9)
    if big.any():
        d = dens[big]
        info["texel_px_per_m"] = dict(p10=round(float(np.percentile(d, 10)), 1), median=round(float(np.median(d)), 1),
                                      p90=round(float(np.percentile(d, 90)), 1))
        low = float((d < 64).mean())
        if low > 0.25:
            warn("texel", f"TEXEL: {low * 100:.0f}% of faces > 1 m2 are below 64 px/m (blurry). Ignore for plain-color faces")

    # 창문
    info["windows"] = len(M["win"].faces) if "win" in M else 0
    audit = ((man or {}).get("metadata") or {}).get("window_audit") or {}
    info["win_dropped"] = int(audit.get("dropped") or 0)
    if info["win_dropped"]:
        warn("win_dropped",
             f"WIN_DROPPED {info['win_dropped']} window(s) within 0.05 m of a wall-piece end were dropped by the zone builder",
             (audit.get("items") or [])[:5])
    if "win" in M:
        win = M["win"]
        R, bad_uv, bad_aspect = [], [], []
        WQ = win.quads()
        WN, WA = normals(WQ)
        for i, uv in enumerate(win.uvs):
            if uv.min() < -1e-6 or uv.max() > 1 + 1e-6:
                bad_uv.append(np.round(WQ[i].mean(0), 2).tolist())
            R.append((*uv.min(0), *uv.max(0)))
            if len(uv) == 4:
                ww, hh = np.linalg.norm(WQ[i, 1] - WQ[i, 0]), np.linalg.norm(WQ[i, 3] - WQ[i, 0])
                uw, vh = np.linalg.norm(uv[1] - uv[0]), np.linalg.norm(uv[3] - uv[0])
                if hh > 1e-6 and vh > 1e-9 and abs((uw / vh) / (ww / hh) - 1) > 0.01:
                    bad_aspect.append(np.round(WQ[i].mean(0), 2).tolist())
        if bad_uv:
            err("win_uv", f"WIN_UV: {len(bad_uv)} window UVs outside 0..1", bad_uv)
        ov = rect_overlaps(R)
        if ov:
            err("win_uv", f"WIN_UV: {len(ov)} overlapping window UV pairs", [np.round(WQ[i].mean(0), 2).tolist() for i, _ in ov])
        if bad_aspect:
            err("win_uv", f"WIN_UV: {len(bad_aspect)} window UVs with wrong aspect ratio", bad_aspect)
        info["win_blocked"] = {}
        for wk, mk in (("win", "main"), ("lod1_win", "lod1"), ("lod2_win", "lod2")):
            if wk not in M or mk not in M:
                continue
            rm = RayMesh(M[mk], alpha if mk != "lod2" else _lod2_alpha(texdir, asset))
            Wq = M[wk].quads()
            Wn, _ = normals(Wq)
            blocked, behind = [], []
            if len(Wq):
                centers = Wq.mean(1)
                sample_points = np.stack((centers, Wq[:, 0] * 0.85 + Wq[:, 2] * 0.15,
                                          Wq[:, 2] * 0.85 + Wq[:, 0] * 0.15), axis=1)
                origins = (sample_points + Wn[:, None, :] * 0.005).reshape(-1, 3)
                directions = np.repeat(Wn[:, None, :], 3, axis=1).reshape(-1, 3)
                distances = rm.hits(origins, directions, args.ray).reshape(-1, 3)
                blocked = [np.round(centers[i], 2).tolist() for i in range(len(Wq)) if (distances[i] < args.ray).any()]
                if wk == "win":
                    back_distances = rm.hits(centers - Wn * 0.001, -Wn, 1.0)
                    behind = [np.round(centers[i], 2).tolist() for i in range(len(Wq)) if back_distances[i] == np.inf]
            info["win_blocked"][wk] = len(blocked)
            if blocked:
                err("win_block_" + wk, f"WIN_BLOCKED {wk}: {len(blocked)} windows blocked by a part within {args.ray} m in front. example = window center xyz", blocked)
            if behind:
                warn("win_behind", f"{len(behind)} windows have no wall within 1 m behind (flipped or floating?)", behind)
    info["time_s"] = round(time.time() - t0, 1)
    return dict(asset=asset, errors=E, warnings=W, info=info)


def _alpha_u8(path):
    """BaseColor 알파만 uint8 로 (4096² RGBA 를 float32 로 바꾸면 256 MB·0.1 s). 비교는 >= 127.5 그대로 성립."""
    with Image.open(path) as im:
        if im.mode in ("RGB", "L") and "transparency" not in im.info:
            return np.full((im.size[1], im.size[0]), 255, np.uint8)
        return np.asarray(im.convert("RGBA").getchannel("A"))


def _lod2_alpha(texdir, asset):
    p = tex_path(texdir, asset, "BaseColor", lod2=True)
    return _alpha_u8(p) if p else None


def print_report(r):
    i = r["info"]
    ok = "OK" if not r["errors"] else f"errors {len(r['errors'])}"
    print(f"== {r['asset']}  [{ok}, warnings {len(r['warnings'])}]  ({i.get('time_s', 0)} s)")
    if "size" in i:
        print(f"   size {i['size']} m  pivot_offset {i['pivot_offset']}  zmin {i['zmin']}")
        print("   tris " + ", ".join(f"{k}={v}" for k, v in i["tris"].items()) + f"  windows {i.get('windows', 0)}")
        print(f"   coplanar {i.get('coplanar')}  win_blocked {i.get('win_blocked')}")
        if "texel_px_per_m" in i:
            print(f"   texel_px_per_m {i['texel_px_per_m']}  textures {i.get('textures')}")
    for tag, lst in (("ERROR", r["errors"]), ("WARN", r["warnings"])):
        for e in lst:
            print(f"   {tag} {e['msg']}")
            for ex in e["examples"]:
                print(f"       e.g. {ex}")


def agent_summary(r):
    """r = check_asset() 의 반환값. action_tags 는 [CS2_AGENT_SUMMARY] 로 호출 에이전트에게
    기계적으로 파싱 가능한 한 줄 JSON 으로 내보낸다 (TOOLS_CLAUDE.md 의 대응표와 agent_actions.FIX_TEXT 가 같은 내용)."""
    return _agent_summary(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--list", type=int, default=5)
    ap.add_argument("--json")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--ray", type=float, default=1.5)
    args = ap.parse_args()
    targets = [args.path]
    p = os.path.abspath(args.path)
    if os.path.isdir(p) and not any(f.endswith(".obj") for f in os.listdir(p)) and not os.path.isdir(os.path.join(p, "_check")):
        subs = [os.path.join(p, d) for d in sorted(os.listdir(p)) if os.path.isdir(os.path.join(p, d))]
        if subs:
            targets = subs
    reports = [check_asset(t, args) for t in targets]
    for r in reports:
        print_report(r)
        print("[CS2_AGENT_SUMMARY] " + json.dumps(agent_summary(r), ensure_ascii=False))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=1)
    sys.exit(1 if any(r["errors"] for r in reports) else 0)


if __name__ == "__main__":
    main()
