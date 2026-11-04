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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proj  # noqa: E402,F401  (decides the project folder, chdir; must come before argparse)
from objio import MAPS, load_asset, load_png, tex_path  # noqa: E402

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
    """같은 방향·같은 평면(1 mm) 위에서 실제로 겹치는 면 쌍. 반대 방향 면끼리는 허용."""
    Q = mesh.quads()
    N, A = normals(Q)
    groups = {}
    for i in range(len(Q)):
        if A[i] < 1e-8:
            continue
        n = N[i]
        d = float(n @ Q[i].mean(0))
        for key in ((tuple(np.round(n, 3)), round(d, 3)),):
            groups.setdefault(key, []).append(i)
    # 반올림 경계 보정: 평면 거리 키가 1 mm 차이 나는 이웃 그룹도 합침
    merged = {}
    for (n, d), idx in groups.items():
        merged.setdefault(n, []).append((d, idx))
    bad = []
    for n, lst in merged.items():
        lst.sort()
        nv = np.array(n, float)
        nv /= np.linalg.norm(nv)
        if abs(nv[2]) > 0.99:
            u, v = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
        else:
            u = np.cross([0, 0, 1.0], nv); u /= np.linalg.norm(u); v = np.cross(nv, u)
        k = 0
        while k < len(lst):
            d0 = lst[k][0]
            idx = []
            while k < len(lst) and lst[k][0] - d0 <= 0.0015:
                idx += lst[k][1]; k += 1
            if len(idx) < 2:
                continue
            P = [_ccw([(float(q @ u), float(q @ v)) for q in _uniq(Q[i])]) for i in idx]
            bb = np.array([(min(x for x, _ in p), min(y for _, y in p), max(x for x, _ in p), max(y for _, y in p)) for p in P])
            order = np.argsort(bb[:, 0])
            for a_ in range(len(order)):
                i = order[a_]
                for b_ in range(a_ + 1, len(order)):
                    j = order[b_]
                    if bb[j, 0] >= bb[i, 2]:
                        break
                    if not (bb[i, 1] < bb[j, 3] and bb[j, 1] < bb[i, 3]):
                        continue
                    inter = P[i]
                    for e in range(len(P[j])):
                        inter = _clip(inter, P[j][e], P[j][(e + 1) % len(P[j])])
                        if not inter:
                            break
                    if inter and _area(inter) > min_area:
                        bad.append(dict(faces=(int(idx[i]), int(idx[j])), area=round(_area(inter), 4),
                                        at=np.round(Q[idx[i]].mean(0), 2).tolist(), normal=list(n)))
    return bad


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
        T, UV = [], []
        for f, uv in zip(mesh.faces, mesh.uvs):
            for k in range(1, len(f) - 1):
                T.append(mesh.verts[[f[0], f[k], f[k + 1]]]); UV.append(uv[[0, k, k + 1]])
        self.T = np.array(T).reshape(-1, 3, 3)
        self.UV = np.array(UV).reshape(-1, 3, 2)
        self.alpha = alpha
        self.lo = self.T.min(1); self.hi = self.T.max(1)

    def hit(self, o, d, maxd):
        """가장 가까운 불투명 교차 거리 (없으면 inf)."""
        end = o + d * maxd
        lo, hi = np.minimum(o, end) - 1e-6, np.maximum(o, end) + 1e-6
        m = np.all((self.hi >= lo) & (self.lo <= hi), axis=1)
        if not m.any():
            return np.inf
        T, UV = self.T[m], self.UV[m]
        v0, v1, v2 = T[:, 0], T[:, 1], T[:, 2]
        e1, e2 = v1 - v0, v2 - v0
        h = np.cross(d, e2); a = (e1 * h).sum(1)
        ok = np.abs(a) > 1e-12
        f = np.where(ok, 1.0 / np.where(ok, a, 1), 0)
        s = o - v0
        uu = f * (s * h).sum(1)
        q = np.cross(s, e1)
        vv = f * (q * d).sum(1)
        t = f * (e2 * q).sum(1)
        hitm = ok & (uu >= -1e-9) & (vv >= -1e-9) & (uu + vv <= 1 + 1e-9) & (t > 1e-4) & (t < maxd)
        if not hitm.any():
            return np.inf
        ids = np.nonzero(hitm)[0]
        for i in ids[np.argsort(t[ids])]:
            if self.alpha is None:
                return t[i]
            uv = UV[i, 0] * (1 - uu[i] - vv[i]) + UV[i, 1] * uu[i] + UV[i, 2] * vv[i]
            H, W = self.alpha.shape
            px = int(np.clip(uv[0] * W, 0, W - 1)); py = int(np.clip((1 - uv[1]) * H, 0, H - 1))
            if self.alpha[py, px] >= 127.5:
                return t[i]
        return np.inf


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
    npl = [i for i in range(len(Q)) if len(main.faces[i]) == 4 and A[i] > 1e-6 and abs((Q[i, 2] - Q[i, 0]) @ N[i]) > 2e-3]
    if npl:
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
            from PIL import Image
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
        alpha = load_png(bp)[..., 3]
    if tex_path(texdir, asset, "Normal"):
        nm = load_png(tex_path(texdir, asset, "Normal"), "RGB").reshape(-1, 3).mean(0)
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
        for i, uv in enumerate(main.uvs):
            u0, v0 = uv.min(0); u1, v1 = uv.max(0)
            e = 1.0 / AS
            if not np.any((boxes[:, 0] - e <= u0) & (boxes[:, 1] - e <= v0) & (boxes[:, 2] + e >= u1) & (boxes[:, 3] + e >= v1)):
                out.append(np.round(Q[i].mean(0), 2).tolist())
        if out:
            err("atlas", f"ATLAS_UV: {len(out)} faces with UV outside a single atlas cell (neighbour color bleeds)", out)
    def _uvarea(uv):
        a, b = uv[2] - uv[0], (uv[3] if len(uv) > 3 else uv[2]) - uv[1]
        return 0.5 * abs(a[0] * b[1] - a[1] * b[0]) if len(uv) > 3 else 0.5 * abs((uv[1] - uv[0])[0] * a[1] - (uv[1] - uv[0])[1] * a[0])
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
            for i in range(len(Wq)):
                p, n = Wq[i], Wn[i]
                for o in (p.mean(0), p[0] * 0.85 + p[2] * 0.15, p[2] * 0.85 + p[0] * 0.15):
                    if rm.hit(o + n * 0.005, n, args.ray) < args.ray:
                        blocked.append(np.round(p.mean(0), 2).tolist()); break
                if wk == "win" and rm.hit(p.mean(0) - n * 0.001, -n, 1.0) == np.inf:
                    behind.append(np.round(p.mean(0), 2).tolist())
            info["win_blocked"][wk] = len(blocked)
            if blocked:
                err("win_block_" + wk, f"WIN_BLOCKED {wk}: {len(blocked)} windows blocked by a part within {args.ray} m in front. example = window center xyz", blocked)
            if behind:
                warn("win_behind", f"{len(behind)} windows have no wall within 1 m behind (flipped or floating?)", behind)
    info["time_s"] = round(time.time() - t0, 1)
    return dict(asset=asset, errors=E, warnings=W, info=info)


def _lod2_alpha(texdir, asset):
    p = tex_path(texdir, asset, "BaseColor", lod2=True)
    return load_png(p)[..., 3] if p else None


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


_FIX_TEXT = {
    "APPLY_STAGE_1": "quality_stage 를 모든 preset_*/attach_* 호출에서 +1 올리고 cycle.py 재실행",
    "APPLY_STAGE_2": "quality_stage=2 로 올리고, bay 수/반복 디테일 밀도도 줄여서 cycle.py 재실행",
    "APPLY_STAGE_3_LOD_CULL": "LOD1/LOD2 생성 시 quality_stage=3 전달(장식 함수가 자동으로 아무것도 안 만듦)",
    "CLAMP_UV": "custom quad 의 UV 를 A.uv_full/A.uv_tile 로 교체 (손으로 만든 UV 좌표 금지)",
    "MERGE_VERTICES": "같은 preset_*/attach_* 호출이 루프 들여쓰기 등으로 중복 실행되는지 확인",
}


def agent_summary(r):
    """r = check_asset() 의 반환값. action_tags 는 [CS2_AGENT_SUMMARY] 로 호출 에이전트에게
    기계적으로 파싱 가능한 한 줄 JSON 으로 내보낸다 (TOOLS_CLAUDE.md 의 대응표와 _FIX_TEXT 가 같은 내용)."""
    i = r["info"]
    err_keys = {e["key"] for e in r["errors"]}
    warn_keys = {w["key"] for w in r["warnings"]}
    tags = []
    tris = i.get("tris", {})
    main_tris = tris.get("main", 0)
    ratio = main_tris / 50000.0 if main_tris else 0.0
    if 1.0 < ratio <= 1.15:
        tags.append("APPLY_STAGE_1")
    elif ratio > 1.15:
        tags.append("APPLY_STAGE_2")
    if "lod1" in err_keys or "lod2" in err_keys:
        tags.append("APPLY_STAGE_3_LOD_CULL")
    if "atlas" in err_keys or "win_uv" in err_keys:
        tags.append("CLAMP_UV")
    if "degenerate" in warn_keys:
        tags.append("MERGE_VERTICES")
    fix = "; ".join(_FIX_TEXT[t] for t in tags) if tags else "no fix needed"
    lod_name = {"main": "LOD0", "lod1": "LOD1", "lod2": "LOD2"}
    verts = {lod_name[k]: v for k, v in i.get("verts", {}).items() if k in lod_name}
    return dict(status="FAIL" if r["errors"] else "PASS", verts=verts,
                action_tags=tags, exact_fix_instruction=fix)


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
