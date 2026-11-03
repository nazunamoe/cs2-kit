# -*- coding: utf-8 -*-
"""scanlib.py - glb/gltf 스캔 읽기 + 형상 분석 공용 라이브러리.

다른 프로젝트에서도 그대로 쓸 수 있게 외부 의존은 numpy / Pillow / matplotlib 만 쓴다.
- read_glb / read_gltf : glTF 2.0 (GLB 또는 .gltf+.bin), float/정수 accessor, 노드 변환 지원
- plan_map             : 스캔 좌표 -> 분석 평면 좌표 (축 선택·부호·이동)
- slice_polygons       : 높이 z 단면 폴리곤 (1 cm 스냅으로 연결)
- up_components        : 위를 향한 면 -> 높이 레벨 -> 연결 성분(옥상판/띠/상자)
- min_area_rect        : 볼록껍질 + 회전 캘리퍼스로 최소 면적 사각형
- silhouette           : x-z / y-z 실루엣 래스터
- obj_triangles        : 키트가 내보낸 OBJ 읽기 (y=높이, z=깊이 중심)
"""
import json
import os
import struct

import numpy as np

COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
        5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


# ---------------------------------------------------------------- glTF 읽기
class Gltf:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        self.json = None
        self.bin = None
        self._load()

    def _load(self):
        p = self.path
        if p.lower().endswith(".glb"):
            raw = open(p, "rb").read()
            if raw[:4] != b"glTF":
                raise ValueError("GLB 가 아님: %s" % p)
            _magic, _ver, _len = struct.unpack_from("<4sII", raw, 0)
            off = 12
            while off < len(raw):
                clen, ctype = struct.unpack_from("<II", raw, off)
                off += 8
                data = raw[off:off + clen]
                off += clen
                if ctype == 0x4E4F534A:          # JSON
                    self.json = json.loads(data.decode("utf-8"))
                elif ctype == 0x004E4942:        # BIN
                    self.bin = data
        else:
            self.json = json.load(open(p, encoding="utf-8"))
            bufs = []
            for b in self.json.get("buffers", []):
                uri = b.get("uri", "")
                if uri.startswith("data:"):
                    import base64
                    bufs.append(base64.b64decode(uri.split(",", 1)[1]))
                elif uri:
                    bufs.append(open(os.path.join(self.dir, uri), "rb").read())
                else:
                    bufs.append(b"")
            self.bin = bufs[0] if bufs else b""
        if self.json is None:
            raise ValueError("glTF JSON 청크가 없음")
        need = self.json.get("extensionsRequired", [])
        if any(e in need for e in ("KHR_draco_mesh_compression",)):
            raise RuntimeError("Draco 압축 glb 는 이 도구로 못 읽습니다 "
                               "(Blender 로 풀거나 glb_measure 를 쓰세요)")

    # -- accessor -------------------------------------------------------
    def accessor(self, idx):
        a = self.json["accessors"][idx]
        n = NCOMP[a["type"]]
        fmt, size = COMP[a["componentType"]]
        if "bufferView" not in a:
            return np.zeros((a["count"], n), np.float64)
        bv = self.json["bufferViews"][a["bufferView"]]
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride") or (size * n)
        buf = self.bin
        if a["count"] == 1:
            vals = struct.unpack_from("<" + fmt * n, buf, base)
            arr = np.array(vals, np.float64).reshape(1, n)
        else:
            # byteStride 가 촘촘하지 않으면 한 줄씩 읽는다
            if stride == size * n:
                arr = np.frombuffer(buf, dtype=np.dtype("<" + fmt),
                                    count=a["count"] * n, offset=base)
                arr = arr.reshape(a["count"], n).astype(np.float64)
            else:
                out = np.empty((a["count"], n), np.float64)
                for i in range(a["count"]):
                    out[i] = struct.unpack_from("<" + fmt * n, buf, base + i * stride)
                arr = out
        if a.get("normalized"):
            if a["componentType"] == 5121:
                arr = arr / 255.0
            elif a["componentType"] == 5123:
                arr = arr / 65535.0
        return arr

    # -- nodes ----------------------------------------------------------
    @staticmethod
    def _node_matrix(node):
        if "matrix" in node:
            return np.array(node["matrix"], np.float64).reshape(4, 4).T
        m = np.eye(4)
        t = node.get("translation")
        r = node.get("rotation")
        s = node.get("scale")
        if t or r or s:
            T = np.eye(4)
            if t:
                T[:3, 3] = t
            R = np.eye(4)
            if r:
                x, y, z, w = r
                R[:3, :3] = np.array([
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            S = np.eye(4)
            if s:
                S[:3, :3] = np.diag(s)
            m = T @ R @ S
        return m

    def entries(self):
        """메시를 가진 노드 목록 [(표시이름, mesh인덱스, world행렬)]"""
        out = []

        def walk(ni, parent):
            node = self.json["nodes"][ni]
            m = parent @ self._node_matrix(node)
            if "mesh" in node:
                mi = node["mesh"]
                nm = node.get("name") or self.json["meshes"][mi].get("name") or str(mi)
                out.append((nm, mi, m))
            for c in node.get("children", []):
                walk(c, m)

        scene = self.json.get("scene", 0)
        for ni in self.json.get("scenes", [{}])[scene].get("nodes", []):
            walk(ni, np.eye(4))
        if not out:                                   # scene 정보가 없으면 전체
            for ni, node in enumerate(self.json.get("nodes", [])):
                if "mesh" in node:
                    out.append((node.get("name") or str(node["mesh"]), node["mesh"],
                                self._node_matrix(node)))
        return out

    def mesh_triangles(self, key):
        """key: 노드이름 | mesh 이름 | 인덱스 문자열. -> (V (n,3), F (m,3), 이름)"""
        key = str(key)
        ents = self.entries()
        pick = None
        for e in ents:
            if e[0] == key:
                pick = e
                break
        if pick is None:
            for e in ents:
                if self.json["meshes"][e[1]].get("name") == key:
                    pick = e
                    break
        if pick is None and key.isdigit():
            for e in ents:
                if e[1] == int(key):
                    pick = e
                    break
        if pick is None:
            raise KeyError("메시를 찾지 못함: %s (list 로 이름 확인)" % key)
        name, mi, M = pick
        V = []
        F = []
        base = 0
        for prim in self.json["meshes"][mi]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            pos = self.accessor(prim["attributes"]["POSITION"])[:, :3]
            if "indices" in prim:
                idx = self.accessor(prim["indices"]).astype(np.int64).ravel()
            else:
                idx = np.arange(len(pos))
            V.append(pos)
            F.append(idx.reshape(-1, 3) + base)
            base += len(pos)
        if not V:
            raise ValueError("삼각형이 없는 메시: %s" % key)
        V = np.vstack(V)
        F = np.vstack(F)
        V = (V @ M[:3, :3].T) + M[:3, 3]
        return V, F, name


def read_gltf(path):
    return Gltf(path)


# ---------------------------------------------------------------- 좌표 변환
class PlanMap:
    """스캔 좌표 -> 분석 평면 좌표.

    axes: (x축 이름, y축 이름) ex) ('x','-z')
    up  : 높이 축
    shift: (dx, dy, dz) 마지막에 더함
    """
    def __init__(self, up="y", axes=("x", "-z"), shift=(0.0, 0.0, 0.0),
                 ground=None):
        self.up = up
        self.axes = axes
        self.shift = np.array(shift, np.float64)
        self.ground = ground

    def apply(self, V):
        V = np.asarray(V, np.float64).copy()
        def comp(spec):
            s = 1.0
            ax = spec
            if ax.startswith("-"):
                s, ax = -1.0, ax[1:]
            return s * V[:, "xyz".index(ax)]
        x = comp(self.axes[0])
        y = comp(self.axes[1])
        z = V[:, "xyz".index(self.up)]
        out = np.c_[x, y, z] + self.shift
        if self.ground == "auto":
            out[:, 2] -= out[:, 2].min()
        elif self.ground is not None:
            out[:, 2] -= self.ground
        return out

    def describe(self):
        sh = ",".join("%.3f" % v for v in self.shift)
        return "plan=(%s,%s) up=%s shift=(%s) ground=%s" % (
            self.axes[0], self.axes[1], self.up, sh, self.ground)


# ---------------------------------------------------------------- 단면
def slice_polygons(V, F, z, snap=0.01, min_area=0.2):
    """높이 z 평면과 메시의 교선을 연결해 닫힌 폴리곤 목록을 돌려준다."""
    tri = V[F]
    n = tri[:, :, 2]
    sel = (n.max(axis=1) >= z) & (n.min(axis=1) <= z)
    segs = []
    for t in tri[sel]:
        zs = t[:, 2]
        pts = []
        for i in range(3):
            j = (i + 1) % 3
            za, zb = zs[i], zs[j]
            if abs(za - zb) < 1e-9:
                continue
            if (za - z) * (zb - z) < -1e-12:
                f = (z - za) / (zb - za)
                pts.append(t[i, :2] + f * (t[j, :2] - t[i, :2]))
        if len(pts) == 2:
            segs.append(pts)

    def key(p):
        return (round(p[0] / snap), round(p[1] / snap))

    adj = {}
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        adj.setdefault(ka, []).append(kb)
        adj.setdefault(kb, []).append(ka)
    used = set()
    polys = []
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka == kb or (ka, kb) in used or (kb, ka) in used:
            continue
        loop = [ka, kb]
        used.add((ka, kb))
        used.add((kb, ka))
        cur, prev = kb, ka
        while True:
            nxt = None
            for q in adj.get(cur, []):
                if q != prev and (cur, q) not in used:
                    nxt = q
                    break
            if nxt is None:
                break
            used.add((cur, nxt))
            used.add((nxt, cur))
            loop.append(nxt)
            prev, cur = cur, nxt
            if cur == loop[0]:
                break
        if len(loop) > 3:
            polys.append(np.array(loop, np.float64) * snap)
    out = []
    for p in polys:
        area = 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1))
                         - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
        if area >= min_area:
            out.append((p, area))
    out.sort(key=lambda t: -t[1])
    return out


# ---------------------------------------------------------------- 옥상(위를 향한 면)
def up_components(V, F, level_tol=0.15, up_thresh=0.7, snap=0.01):
    """위를 향한 면을 높이 레벨로 묶고, 레벨마다 연결 성분을 낸다.

    스캔 메시는 정점 감기가 뒤집힌 경우가 있어 |nz| 로 판정하고, 실제로 위를 향한
    면이 하나도 없으면 winding 이 반대라고 경고한다.
    """
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    a2 = np.linalg.norm(n, axis=1)
    ok = a2 > 1e-9
    nz = np.zeros(len(tri))
    nz[ok] = n[ok, 2] / a2[ok]
    area = a2 / 2.0
    a_up = area[nz > up_thresh].sum()
    a_dn = area[nz < -up_thresh].sum()
    flipped = a_dn > a_up
    up_mask = (nz < -up_thresh) if flipped else (nz > up_thresh)
    T = tri[up_mask]
    A = area[up_mask]
    Hm = T[:, :, 2].mean(axis=1)

    # 높이 레벨 (면적 가중 평균으로 합친다)
    order = np.argsort(Hm)
    levels = []          # [{'z':값,'tris':[idx...]}]
    for i in order:
        h = Hm[i]
        if levels and abs(h - levels[-1]["z"]) <= level_tol:
            g = levels[-1]
            g["z"] = (g["z"] * g["area"] + h * A[i]) / (g["area"] + A[i])
            g["area"] += A[i]
            g["tris"].append(i)
        else:
            levels.append({"z": h, "area": A[i], "tris": [i]})
    levels.sort(key=lambda g: -g["z"])

    # 레벨마다 연결 성분
    for g in levels:
        idx = np.array(g["tris"])
        comps = _components(T[idx], A[idx], snap)
        g["comp"] = comps
        g["ncomp"] = len(comps)
    return levels, flipped


def _components(T, A, snap):
    """삼각형들을 정점 공유로 묶는다 (1 cm 스냅)."""
    n = len(T)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    vert = {}
    for i, t in enumerate(T):
        for p in t:
            k = (round(p[0] / snap), round(p[1] / snap))
            if k in vert:
                union(i, vert[k])
            else:
                vert[k] = i
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        tri_m = T[np.array(members)]
        pts = tri_m[:, :, :2].reshape(-1, 2)
        ar = A[np.array(members)].sum()
        cen = pts.mean(axis=0)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        hull = convex_hull(pts)
        rw, rh, ang = min_area_rect(hull)
        out.append({"area": ar, "centroid": cen, "bbox": (x0, y0, x1, y1),
                    "rect_w": rw, "rect_h": rh, "rect_angle": ang,
                    "npts": len(pts), "tris": len(members)})
    out.sort(key=lambda c: -c["area"])
    return out


def convex_hull(points):
    pts = np.unique(np.round(points, 6), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def min_area_rect(hull):
    """회전 캘리퍼스: 최소 면적 사각형 (w, h, 각도 deg)."""
    if len(hull) < 3:
        if len(hull) == 0:
            return 0.0, 0.0, 0.0
        d = hull[:, None, :] - hull[None, :, :]
        dd = (d ** 2).sum(axis=2)
        i, j = np.unravel_index(np.argmax(dd), dd.shape)
        w = float(np.sqrt(dd[i, j]))
        return w, 0.0, 0.0
    best = None
    n = len(hull)
    for i in range(n):
        p0 = hull[i]
        p1 = hull[(i + 1) % n]
        e = p1 - p0
        L = np.hypot(*e)
        if L < 1e-9:
            continue
        ux, uy = e / L
        vx, vy = -uy, ux
        pu = hull[:, 0] * ux + hull[:, 1] * uy
        pv = hull[:, 0] * vx + hull[:, 1] * vy
        w = pu.max() - pu.min()
        h = pv.max() - pv.min()
        area = w * h
        if best is None or area < best[0]:
            ang = np.degrees(np.arctan2(uy, ux))
            best = (area, w, h, ang)
    return best[1], best[2], best[3]


# ---------------------------------------------------------------- 래스터
def raster_triangles(T2, size=512, bbox=None):
    """2D 삼각형을 채운 불리언 마스크. T2: (n,3,2)"""
    if bbox is None:
        pts = T2.reshape(-1, 2)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
    else:
        x0, y0, x1, y1 = bbox
    w = max(x1 - x0, 1e-6)
    h = max(y1 - y0, 1e-6)
    sc = (size - 1) / max(w, h)
    W = int(np.ceil(w * sc)) + 1
    H = int(np.ceil(h * sc)) + 1
    mask = np.zeros((H, W), bool)
    for t in T2:
        xs = (t[:, 0] - x0) * sc
        ys = (t[:, 1] - y0) * sc
        px0, px1 = int(np.floor(xs.min())), int(np.ceil(xs.max()))
        py0, py1 = int(np.floor(ys.min())), int(np.ceil(ys.max()))
        px0, py0 = max(px0, 0), max(py0, 0)
        px1, py1 = min(px1, W - 1), min(py1, H - 1)
        if px1 < px0 or py1 < py0:
            continue
        yy, xx = np.mgrid[py0:py1 + 1, px0:px1 + 1]
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        l1 = ((ys[1] - ys[2]) * (xx - xs[2]) + (xs[2] - xs[1]) * (yy - ys[2])) / d
        l2 = ((ys[2] - ys[0]) * (xx - xs[2]) + (xs[0] - xs[2]) * (yy - ys[2])) / d
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        mask[yy[inside], xx[inside]] = True
    return mask, (x0, y0, sc)


def silhouette(T, size=512, bbox=None):
    """3D 삼각형 -> (x, z) 실루엣 마스크"""
    return raster_triangles(T[:, :, [0, 2]], size=size, bbox=bbox)


def read_obj(path):
    """OBJ 읽기. 키트 내보내기 축: x, y=높이, z=깊이(중심) -> (x, Y, 높이)"""
    V, F = [], []
    for line in open(path, encoding="utf-8", errors="ignore"):
        if line.startswith("v "):
            p = line.split()
            V.append([float(p[1]), float(p[2]), float(p[3])])
        elif line.startswith("f "):
            idx = [int(x.split("/")[0]) - 1 for x in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                F.append([idx[0], idx[i], idx[i + 1]])
    V = np.array(V, np.float64)
    F = np.array(F, np.int64)
    # 키트 내보내기: y=높이, z=깊이(가운데 0, 모델 y 와 부호가 반대) -> y = -z
    return np.c_[V[:, 0], -V[:, 2], V[:, 1]], F


def load_mesh(path, key=None, up="y", axes=("x", "-z"), shift=(0, 0, 0),
              ground=None):
    g = read_gltf(path)
    if key is None:
        ents = g.entries()
        if len(ents) != 1:
            raise ValueError("메시가 여러 개입니다. --mesh 로 고르세요: %s"
                             % ", ".join(e[0] for e in ents[:12]))
        key = ents[0][0]
    V, F, name = g.mesh_triangles(key)
    V0 = V.copy()
    pm = PlanMap(up=up, axes=axes, shift=shift, ground=ground)
    V = pm.apply(V0)
    return dict(V=V, F=F, name=name, map=pm, raw=V0)
