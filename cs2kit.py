# -*- coding: utf-8 -*-
"""
cs2kit.py — Cities: Skylines II 건물 에셋 생성기 공통 라이브러리
생성기(.py)는 이 파일을 import 해서 형상만 만들면 됨. Blender 안/밖 모두 동작 (numpy 만 필요, PIL 불필요).

들어 있는 것
  MeshBuilder      quad / box(면별 영역, skip, 타일 UV 자동) / merge / shift
  face_pts, axbox, paint   벽면 기준 사각형·박스·칠 면 헬퍼 (바깥 법선이 맞게)
  curtainwall, corner_post  커튼월(룩) 한 면: 멀리언·트랜섬 메시 + 스팬드럴 칠 + 시야 유리 창 (모듈 폭·스팬드럴 높이 지정)
  Atlas            가변 크기 칸 아틀라스: 색·색상변형·메탈·광택·발광, 타일 재질(실제 크기 UV), 사진 조각 넣기,
                   칸 그림 그리기(painter), 노멀 높이맵, 블리드(밉맵 번짐 방지), JSON 배치표 저장
  WindowSet        창문 면 모으기 + 레퍼런스 25칸 UV 배정 (겹침 없음, 비율 유지)
  export_asset     피벗 맞추기 → 텍스처 5종(메인 + LOD1 + LOD2) → Blender 안이면 FBX/.blend, 밖이면 OBJ + manifest.json

좌표: 1 유닛 = 1 m, 지면 z = 0, 정면(도로) = -Y. 면 이름: front=-Y, back=+Y, left=-X, right=+X
사용 예: example_building_cs2.py 참고
"""

import json
import math
import os
import shutil
import struct
import sys
import zlib

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글·기호 출력 오류 방지
except Exception:
    pass

try:
    import bpy  # Blender 안에서만
except ImportError:
    bpy = None

# =============================================================================
# 설정 (CS2 규격)
# =============================================================================
FBX_SCALE_OPTION = "FBX_SCALE_NONE"   # CS2 는 FBX 단위 정보를 무시하고 cm 로 읽음 → FBX_SCALE_ALL 이면 1/100 크기
CELL_M = 8.0                          # 로트 한 칸
ZONED_MAX = 6                         # 구역 건물 최대 6x6
LOD1_MAX_RATIO = 0.5
LOD2_MAX_TRIS = 500
MAIN_SOFT_MAX = 95000
WIN_OFF = 0.02                        # 창문 면: 벽 앞 2 cm
LOD2_WIN_OFF = 0.05
PAINT_OFF = 0.01                      # 칠 면: 벽 앞 1 cm (layer 배수)
REF_GRID = 5                          # 창문 레퍼런스 25칸 = 5x5 로 가정
PARTS = ["main", "win", "gls", "lod1", "lod1_win", "lod1_gls", "lod2", "lod2_win"]
SUFFIX = {"main": "", "win": "_Win", "gls": "_Gls", "lod1": "_LOD1", "lod1_win": "_LOD1_Win",
          "lod1_gls": "_LOD1_Gls", "lod2": "_LOD2", "lod2_win": "_LOD2_Win"}


# =============================================================================
# 메시 빌더
# =============================================================================
class MeshBuilder:
    """사각면 목록. 면마다 UV 4개와 태그(아틀라스 칸 이름)."""

    def __init__(self, atlas=None, split_tiles=True):
        """split_tiles=False: tile materials are NOT cut into real-size pieces (one quad per face).
        Use it for LOD2 (<= 500 tris) - LOD2 = K.MeshBuilder(A, split_tiles=False)."""
        self.verts, self.faces, self.uvs, self.tags = [], [], [], []
        self.atlas = atlas
        self.split_tiles = split_tiles

    def quad(self, pts, uv4, tag):
        i = len(self.verts)
        self.verts.extend(tuple(float(c) for c in p) for p in pts)
        self.faces.append((i, i + 1, i + 2, i + 3))
        self.uvs.append([tuple(map(float, t)) for t in uv4])
        self.tags.append(tag)

    def rect(self, pts, region):
        """평면 사각형 하나에 영역 입히기. 타일 재질이면 실제 크기 타일로 쪼개 붙임."""
        A = self.atlas
        if A is not None and A.is_tiled(region) and self.split_tiles:
            self._tiled(pts, region)
        else:
            self.quad(pts, A.uv(region) if A is not None else [(0, 0), (1, 0), (1, 1), (0, 1)], region)

    def _tiled(self, pts, region):
        p0, p1, _p2, p3 = [np.array(p, float) for p in pts]
        W, H = np.linalg.norm(p1 - p0), np.linalg.norm(p3 - p0)
        if W < 1e-6 or H < 1e-6:
            return
        tw, th = self.atlas.tile_size(region)
        ex, ey = (p1 - p0) / W, (p3 - p0) / H
        nx, ny = max(1, math.ceil(W / tw - 1e-6)), max(1, math.ceil(H / th - 1e-6))
        for j in range(ny):
            b0, b1 = j * th, min(H, (j + 1) * th)
            for i in range(nx):
                a0, a1 = i * tw, min(W, (i + 1) * tw)
                q = [p0 + ex * a0 + ey * b0, p0 + ex * a1 + ey * b0, p0 + ex * a1 + ey * b1, p0 + ex * a0 + ey * b1]
                self.quad(q, self.atlas.uv_tile(region, a1 - a0, b1 - b0, variant=(i * 7 + j * 3)), region)

    def box(self, x0, x1, y0, y1, z0, z1, region, skip=()):
        """축 정렬 박스. region = 칸 이름 또는 면별 dict(front,back,left,right,top,bottom,default). skip = 만들지 않을 면."""
        if x1 - x0 < 1e-5 or y1 - y0 < 1e-5 or z1 - z0 < 1e-5:
            return
        F = {
            "front": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            "back": [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
            "left": [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
            "right": [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            "top": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
            "bottom": [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)],
        }
        for face, pts in F.items():
            if face in skip:
                continue
            reg = region if isinstance(region, str) else region.get(face, region.get("default"))
            if reg:
                self.rect(pts, reg)

    def merge(self, other):
        b = len(self.verts)
        self.verts.extend(other.verts)
        self.faces.extend(tuple(i + b for i in f) for f in other.faces)
        self.uvs.extend(other.uvs)
        self.tags.extend(other.tags)

    def shift(self, dx, dy):
        self.verts = [(x + dx, y + dy, z) for x, y, z in self.verts]

    @property
    def tri_count(self):
        return 2 * len(self.faces)


def face_pts(axis, c, s, a0, a1, z0, z1):
    """벽면 위 사각형. axis 'y' = 평면 y=c (s=-1 정면, +1 후면), axis 'x' = 평면 x=c (s=-1 왼쪽, +1 오른쪽).
    a = 면을 따라가는 월드 좌표(정면·후면은 x, 옆면은 y). 바깥에서 보면 p0 왼쪽 아래 → p1 오른쪽 아래 (창 UV 방향과 맞음)."""
    if axis == "y":
        if s > 0:
            a0, a1 = a1, a0
        return [(a0, c, z0), (a1, c, z0), (a1, c, z1), (a0, c, z1)]
    if s < 0:
        a0, a1 = a1, a0
    return [(c, a0, z0), (c, a1, z0), (c, a1, z1), (c, a0, z1)]


def axbox(mb, axis, c, s, a0, a1, o0, o1, z0, z1, region, skip=()):
    """벽면(axis, c, s)에 붙은 박스: a0..a1 면을 따라, o0..o1 바깥으로, z0..z1 높이.
    o0 = 0 (벽에 붙음) 이면 벽 쪽 면을 자동 생략 → 벽·이웃 부재와 같은 평면 겹침 방지."""
    if abs(o0) < 1e-9:
        skip = tuple(skip) + ({("y", -1): "back", ("y", 1): "front", ("x", -1): "right", ("x", 1): "left"}[(axis, s)],)
    if axis == "y":
        y0, y1 = sorted((c + s * o0, c + s * o1))
        mb.box(a0, a1, y0, y1, z0, z1, region, skip)
    else:
        x0, x1 = sorted((c + s * o0, c + s * o1))
        mb.box(x0, x1, a0, a1, z0, z1, region, skip)


def paint(mb, axis, c, s, a0, a1, z0, z1, region, layer=1):
    """벽 앞 칠 면 (layer 1 = 1 cm, 칠 위 칠은 layer 2 …)."""
    mb.rect(face_pts(axis, c + s * PAINT_OFF * layer, s, a0, a1, z0, z1), region)


def up_quad(q):
    """바닥에 까는 면이 위(+Z)를 보게 꼭짓점 순서 맞춤."""
    (ax, ay, _), (bx, by, _), _, (dx, dy, _) = q
    return q if (bx - ax) * (dy - ay) - (by - ay) * (dx - ax) > 0 else [q[1], q[0], q[3], q[2]]


def floor_quad(mb, x0, x1, y0, y1, z, region):
    mb.rect([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], region)


def curtainwall(mb, axis, c, s, a0, a1, z0, z1, fh, wins, lod1=None, lod2=None, module_w=1.5, modules=None,
                mullion=(0.06, 0.12), transom=(0.06, 0.08), spandrel_h=0.9, head_h=0.0, floor0=0, unit_modules=3,
                unit0=0, ends=(True, True), cell=None, show_mullion=True, show_transom=True,
                frame="frame", spandrel="spandrel", solid="spandrel", louver="louver", lod2_stride=1):
    """커튼월(또는 커튼월룩) 한 면을 실제 메시로 만든다: 세로 멀리언 + 층마다 가로 트랜섬 + 스팬드럴 패널(칠) + 시야 유리(_Win 창).
    벽(axis, c, s)은 몸체 박스의 면이고, 그 앞에 얹는다. a0..a1 = 면을 따라(정면·후면 x, 옆면 y), z0..z1 = 높이.
    fh = 층고(숫자 또는 층별 목록). 층 수 = round((z1-z0)/fh) (목록이면 len).
    module_w = 모듈 폭 목표(m). 면 폭에 맞게 같은 폭으로 나눠 실제 폭이 조금 달라진다. modules=[폭,...] 로 직접 줄 수도 있다.
    mullion=(폭, 튀어나옴)  transom=(높이, 튀어나옴)  — 튀어나옴 값이 달라서 앞면이 같은 평면으로 겹치지 않는다.
    spandrel_h = 층 바닥에서 시야 유리 시작 전까지 불투명 띠 높이(슬래브 앞 패널, 0 이면 바닥부터 유리).
    head_h = 층 위쪽 불투명 띠(0 이면 없음).  show_mullion / show_transom = False 로 세로선 또는 가로선만 보이게(리본형).
    cell(i, f) = None(기본: 유리) | "solid"(불투명 패널) | "louver"(환기 루버 칸, 칠) | "open"(아무것도 안 만듦, 발코니 개구부 등)
    ends=(왼쪽 끝 멀리언, 오른쪽 끝 멀리언). 건물 모서리에서 두 면이 만나면 한쪽만 끝 멀리언을 만들고 corner_post() 를 쓴다.
    wins = WindowSet, lod1/lod2 = (선택) 단순화 MeshBuilder — 층마다 스팬드럴 띠만 칠한다. 재질 영역 이름: frame / spandrel / louver.
    반환: dict(modules=N, module_w=실제 폭, floors=층 수)"""
    width = a1 - a0
    if modules is None:
        n = max(1, int(round(width / module_w)))
        modules = [width / n] * n
    else:
        if abs(sum(modules) - width) > 0.02:
            raise ValueError("curtainwall: sum(modules)=%.3f != width %.3f" % (sum(modules), width))
    mw, md = mullion
    th, td = transom
    fhs = list(fh) if isinstance(fh, (list, tuple)) else None
    nf = len(fhs) if fhs else max(1, int(round((z1 - z0) / fh)))
    if not fhs:
        fhs = [(z1 - z0) / nf] * nf
    if not (0.9 <= modules[0] <= 3.0):
        print("WARN curtainwall: module width %.2f m is unusual (0.9~3.0 m). check TASK.md / the photo" % modules[0])
    edges = [a0]
    for w in modules:
        edges.append(edges[-1] + w)
    nb = len(edges)
    # mullion x-range at every boundary (None = none): end mullions sit inside a0..a1, interior ones are centred on the boundary
    mull = []
    for j in range(nb):
        if j == 0:
            mull.append((edges[0], edges[0] + mw) if ends[0] else None)
        elif j == nb - 1:
            mull.append((edges[-1] - mw, edges[-1]) if ends[1] else None)
        else:
            mull.append((edges[j] - mw / 2, edges[j] + mw / 2))
    inner = []                                               # visible span of every module = between neighbouring mullion faces
    for i in range(len(modules)):
        lo = mull[i][1] if mull[i] else edges[i]
        hi = mull[i + 1][0] if mull[i + 1] else edges[i + 1]
        inner.append((lo, hi))
    if show_mullion:
        for m in mull:
            if m:
                axbox(mb, axis, c, s, m[0], m[1], 0, md, z0, z1, frame)
    z = z0
    for f in range(nf):
        zf, zt = z, z + fhs[f]
        last = f == nf - 1
        rails = [(zf, zf + th)]                                   # slab line rail
        sp_top = zf + spandrel_h if spandrel_h > th + 0.05 else zf + th
        if spandrel_h > th + 0.05:
            rails.append((sp_top, sp_top + th))                   # sill rail on top of the spandrel panel
        g0 = rails[-1][1]
        g1 = zt
        if head_h > 0.05:
            g1 = zt - head_h - th
            rails.append((g1, g1 + th))
        if last:
            g1 = min(g1, zt - th)
            rails.append((zt - th, zt))
        if show_transom:
            for i in range(len(modules)):
                lo, hi = inner[i]
                for r0, r1 in rails:
                    if r1 > r0 + 1e-6:
                        axbox(mb, axis, c, s, lo, hi, 0, td, r0, r1, frame)
        for i in range(len(modules)):
            lo, hi = inner[i]
            kind = cell(i, floor0 + f) if cell else None
            if kind == "open":
                continue
            pieces = []                                           # (z_from, z_to, region) of opaque paint
            if spandrel_h > th + 0.05:
                pieces.append((rails[0][1], sp_top, spandrel))
            if head_h > 0.05:
                pieces.append((g1 + th, zt - (th if last else 0), spandrel))
            if kind in ("solid", "louver"):
                pieces.append((g0, g1, louver if kind == "louver" else solid))
            else:
                wins.add_face(axis, c, s, lo, hi, g0, g1, floor=floor0 + f, unit=unit0 + i // max(1, unit_modules))
            for p0, p1, reg in pieces:
                if p1 > p0 + 1e-6:
                    paint(mb, axis, c, s, lo, hi, p0, p1, reg)
        if lod1 is not None:
            lo, hi = inner[0][0], inner[-1][1]
            paint(lod1, axis, c, s, lo, hi, zf, zf + max(spandrel_h, th), spandrel)
        if lod2 is not None and f % max(1, lod2_stride) == 0:
            paint(lod2, axis, c, s, inner[0][0], inner[-1][1], zf, zf + max(spandrel_h, th), spandrel)
        z = zt
    return dict(modules=len(modules), module_w=sum(modules) / len(modules), floors=nf)


def corner_post(mb, x, y, sx, sy, size, z0, z1, region="frame"):
    """건물 모서리 기둥: (x, y) 모서리에서 바깥(sx, sy = ±1)으로 size 만큼 나온 정사각 기둥.
    두 면의 curtainwall 에서 한쪽 끝 멀리언을 ends 로 끄고 이 기둥으로 이어 붙인다."""
    xa, xb = sorted((x, x + sx * size))
    ya, yb = sorted((y, y + sy * size))
    mb.box(xa, xb, ya, yb, z0, z1, region, skip=("bottom",))


# =============================================================================
# 아틀라스
# =============================================================================
class Atlas:
    """가변 크기 칸 아틀라스. add() 로 칸을 등록 → layout() 이 선반(shelf) 방식으로 배치 → render() 가 텍스처 5종을 그림.

    칸 속성
      color (r,g,b) 0~255, ctrl (r,g,b) 색상 변형 1/2/3 (겹치지 않게), metal 0~1, gloss 0~1, emissive (r,g,b) 또는 None
      px    칸 크기(px) — 중요한 재질일수록 크게 (텍셀 밀도)
      tile  (가로 m, 세로 m) 이면 타일 재질: 칸 전체 = 실제 크기 한 장, 면은 그 크기로 잘라 붙임
      image 사진 조각 경로(RGB 또는 RGBA PNG) — 칸 크기로 맞춰 넣음 (textures_src/*.png)
      normal_image, gloss_image  같은 크기의 노멀(RGB)·광택(L) 맵 (extract_texture.py 출력)
      painter  fn(ctx) — ctx.u, ctx.v (0~1 칸 안 좌표, v 아래=0), ctx.rgb, ctx.alpha, ctx.height, ctx.gloss, ctx.emis 를 고쳐 그림
    """

    def __init__(self, size=4096, pad=16):
        self.size, self.pad = size, pad
        self.cells = {}
        self.order = []
        self._laid = False

    def add(self, name, color=(200, 200, 200), ctrl=(0, 0, 0), metal=0.0, gloss=0.3, emissive=None,
            px=256, tile=None, image=None, normal_image=None, gloss_image=None, painter=None, variants=1, normal_strength=2.0):
        self.cells[name] = dict(color=color, ctrl=ctrl, metal=metal, gloss=gloss, emissive=emissive, px=int(px),
                                tile=tile, image=image, normal_image=normal_image, gloss_image=gloss_image,
                                painter=painter, variants=max(1, int(variants)), normal_strength=normal_strength)
        self.order.append(name)
        self._laid = False
        self._cache = None
        return name

    # ---- 배치
    def layout(self):
        if self._laid:
            return
        S, P = self.size, self.pad
        items = sorted(self.order, key=lambda n: -self.cells[n]["px"] * self.cells[n]["variants"])
        x = y = 0
        shelf_h = 0
        for n in items:
            c = self.cells[n]
            w = c["px"] * c["variants"]                      # 변형은 가로로 이어 붙임
            h = c["px"]
            if x + w + 2 * P > S:
                x, y = 0, y + shelf_h
                shelf_h = 0
            if y + h + 2 * P > S or w + 2 * P > S:
                raise ValueError(f"atlas {S}px: cell '{n}' does not fit - lower px or raise Atlas size")
            c["rect"] = (x + P, y + P, w, h)                  # (x, y, w, h) PNG 픽셀 (y 위→아래)
            x += w + 2 * P
            shelf_h = max(shelf_h, h + 2 * P)
        self._laid = True

    def _uvrect(self, name, variant=0):
        self.layout()
        c = self.cells[name]
        x, y, w, h = c["rect"]
        vw = w / c["variants"]
        v = variant % c["variants"]
        S = float(self.size)
        u0, u1 = (x + v * vw) / S, (x + (v + 1) * vw) / S
        v0, v1 = 1.0 - (y + h) / S, 1.0 - y / S             # UV 는 아래 = 0
        return u0, v0, u1, v1

    # ---- UV
    def is_tiled(self, name):
        return self.cells.get(name, {}).get("tile") is not None

    def tile_size(self, name):
        return self.cells[name]["tile"]

    def uv(self, name, inset=0.25):
        """단색 면: 칸 가운데 (기본 가운데 절반)."""
        u0, v0, u1, v1 = self._uvrect(name)
        du, dv = (u1 - u0) * inset, (v1 - v0) * inset
        return [(u0 + du, v0 + dv), (u1 - du, v0 + dv), (u1 - du, v1 - dv), (u0 + du, v1 - dv)]

    def uv_full(self, name, variant=0, margin=0.5):
        """칸 전체 (알파 그림·코트 선 등). margin = px 안쪽 여유."""
        u0, v0, u1, v1 = self._uvrect(name, variant)
        e = margin / self.size
        return [(u0 + e, v0 + e), (u1 - e, v0 + e), (u1 - e, v1 - e), (u0 + e, v1 - e)]

    def uv_sub(self, name, fu0, fv0, fu1, fv1, variant=0):
        """칸 안 일부 (0~1 비율)."""
        u0, v0, u1, v1 = self._uvrect(name, variant)
        U = lambda f: u0 + (u1 - u0) * f
        V = lambda f: v0 + (v1 - v0) * f
        return [(U(fu0), V(fv0)), (U(fu1), V(fv0)), (U(fu1), V(fv1)), (U(fu0), V(fv1))]

    def uv_tile(self, name, w_m, h_m, variant=0):
        """타일 재질: 왼쪽 아래부터 실제 크기(w_m x h_m)만큼 잘라낸 UV."""
        tw, th = self.cells[name]["tile"]
        e = 0.5 / self.size
        u0, v0, u1, v1 = self._uvrect(name, variant)
        fu, fv = min(1.0, w_m / tw), min(1.0, h_m / th)
        return [(u0 + e, v0 + e), (u0 + e + (u1 - u0 - 2 * e) * fu, v0 + e),
                (u0 + e + (u1 - u0 - 2 * e) * fu, v0 + e + (v1 - v0 - 2 * e) * fv), (u0 + e, v0 + e + (v1 - v0 - 2 * e) * fv)]

    def texel_density(self, name):
        """타일 재질의 px/m (가로, 세로)."""
        c = self.cells[name]
        if not c["tile"]:
            return None
        return c["px"] / c["tile"][0], c["px"] / c["tile"][1]

    # ---- 그리기
    def render(self, size=None):
        """텍스처 5종 배열 (BaseColor RGBA, ControlMask RGBA, MaskMap RGBA, Normal RGB, Emissive RGB). size 를 주면 줄여서."""
        self.layout()
        S = self.size
        cache = getattr(self, "_cache", None)
        if cache is not None and cache[0] == len(self.order):
            maps = {k: v.copy() for k, v in cache[1].items()}
            return self._finish(maps, size)
        base = np.zeros((S, S, 4), np.float32); base[..., 3] = 255
        ctrl = np.zeros((S, S, 4), np.float32); ctrl[..., 3] = 255
        mask = np.zeros((S, S, 4), np.float32)
        nrm = np.zeros((S, S, 3), np.float32); nrm[...] = (128, 128, 255)
        emis = np.zeros((S, S, 3), np.float32)
        filled = np.zeros((S, S), bool)
        for name in self.order:
            c = self.cells[name]
            x, y, w, h = c["rect"]
            sl = (slice(y, y + h), slice(x, x + w))
            ctx = _CellCtx(w, h, c)
            if c["image"]:
                img = _read_png(c["image"])
                ctx.rgb[...] = _resize(img[..., :3], w, h)
                if img.shape[2] == 4:
                    ctx.alpha[...] = _resize(img[..., 3:4], w, h)[..., 0]
            if c["painter"]:
                c["painter"](ctx)
            base[sl][..., :3] = ctx.rgb
            base[sl][..., 3] = ctx.alpha
            ctrl[sl][..., :3] = c["ctrl"]
            mask[sl][..., 0] = c["metal"] * 255
            mask[sl][..., 3] = np.clip(ctx.gloss, 0, 1) * 255
            if c["gloss_image"]:
                g = _read_png(c["gloss_image"])
                mask[sl][..., 3] = _resize(g[..., :1], w, h)[..., 0]
            if c["normal_image"]:
                nrm[sl] = _resize(_read_png(c["normal_image"])[..., :3], w, h)
            elif np.ptp(ctx.height) > 1e-6:
                nrm[sl] = height_to_normal(ctx.height, c["normal_strength"])
            if c["emissive"] is not None:
                emis[sl] = np.array(c["emissive"], np.float32) * ctx.emis[..., None]
            filled[sl] = True
        iy, ix = _bleed_index(filled, self.pad)
        base, ctrl, mask, nrm, emis = (a[iy, ix] for a in (base, ctrl, mask, nrm, emis))
        maps = dict(BaseColor=base, ControlMask=ctrl, MaskMap=mask, Normal=nrm, Emissive=emis)
        self._cache = (len(self.order), {k: v.copy() for k, v in maps.items()})
        return self._finish(maps, size)

    def _finish(self, maps, size):
        S = self.size
        if size and size != S:
            k = S // size
            for key in maps:
                a = maps[key].reshape(size, k, size, k, -1).mean(axis=(1, 3))
                if key == "Normal":
                    v = a / 127.5 - 1.0
                    v /= np.linalg.norm(v, axis=-1, keepdims=True) + 1e-6
                    a = (v + 1.0) * 127.5
                maps[key] = a
        return {k: np.clip(v, 0, 255).astype(np.uint8) for k, v in maps.items()}

    def to_json(self):
        self.layout()
        return dict(size=self.size, pad=self.pad, cells={n: dict(rect=self.cells[n]["rect"], tile=self.cells[n]["tile"],
                                                                variants=self.cells[n]["variants"], px=self.cells[n]["px"])
                                                         for n in self.order})


class _CellCtx:
    """painter 에 넘기는 칸 그리기 상태. 배열은 [행(위→아래), 열]. u, v 는 0~1 (v 아래 = 0)."""

    def __init__(self, w, h, c):
        self.w, self.h = w, h
        yy, xx = np.mgrid[0:h, 0:w]
        self.u = ((xx + 0.5) / w).astype(np.float32)
        self.v = (1.0 - (yy + 0.5) / h).astype(np.float32)
        self.variants = c["variants"]
        self.vu = (self.u * self.variants) % 1.0         # 변형 칸 안 u
        self.vi = np.minimum((self.u * self.variants).astype(int), self.variants - 1)   # 변형 번호
        self.tile = c["tile"]
        self.rgb = np.zeros((h, w, 3), np.float32); self.rgb[...] = c["color"]
        self.alpha = np.full((h, w), 255.0, np.float32)
        self.height = np.zeros((h, w), np.float32)       # 노멀맵용 높이 (홈 = 음수)
        self.gloss = np.full((h, w), c["gloss"], np.float32)
        self.emis = np.ones((h, w), np.float32)
        self.rng = np.random.default_rng(abs(hash(str(c["color"]))) % (2 ** 31))

    def meters(self):
        """타일 재질: 칸 안 좌표를 미터로 (x 가로, y 세로, 아래 = 0). 변형마다 0 부터."""
        tw, th = self.tile
        return self.vu * tw, self.v * th

    def noise(self, scale_px=8, amp=1.0, octaves=3, seed=0):
        """부드러운 값 노이즈 (h, w), 평균 0."""
        rng = np.random.default_rng(seed)
        out = np.zeros((self.h, self.w), np.float32)
        a, s = 1.0, scale_px
        for _ in range(octaves):
            gh, gw = max(2, int(self.h / s) + 2), max(2, int(self.w / s) + 2)
            g = rng.standard_normal((gh, gw)).astype(np.float32)
            out += a * _resize(g[..., None], self.w, self.h, smooth=True)[..., 0]
            a *= 0.5
            s = max(1, s / 2)
        return out * amp / (np.std(out) + 1e-6)

    # 자주 쓰는 무늬
    def joints(self, cols, rows, width_m=0.01, depth=1.0, stagger=0.0, darken=0.25, tone=4.0, seed=1):
        """판석·패널 줄눈 (타일 재질 전용). cols x rows 장, stagger = 홀수 줄 엇갈림 비율(0.5 = 반 장)."""
        tw, th = self.tile
        mx, my = self.meters()
        rh = th / rows
        row = np.minimum((my / rh).astype(int), rows - 1)
        cw = tw / cols
        sx = mx / cw - (row % 2) * stagger
        col = np.floor(sx).astype(int) % cols
        dx = np.minimum(sx - np.floor(sx), np.ceil(sx) - sx) * cw
        fy = my / rh
        dy = np.minimum(fy - np.floor(fy), np.ceil(fy) - fy) * rh
        d = np.clip(1.0 - np.minimum(dx, dy) / max(width_m, 1e-4), 0, 1)
        rng = np.random.default_rng(seed)
        tones = rng.normal(0, tone, (self.variants, rows, cols)).astype(np.float32)
        self.rgb += tones[self.vi, row, col][..., None]
        self.rgb *= (1.0 - darken * d)[..., None]
        self.height -= depth * d
        return d

    def stains(self, amount=0.08, scale_px=64, streaks=0.0, seed=2):
        """얼룩·빗물 자국 (세로로 늘어진 노이즈). amount = 어두워지는 정도."""
        n = self.noise(scale_px, 1.0, 3, seed)
        if streaks > 0:
            sn = self.noise(max(2, scale_px // 8), 1.0, 2, seed + 7)
            col = sn.mean(axis=0, keepdims=True)
            n = n * (1 - streaks) + np.repeat(col, self.h, axis=0) * streaks * (1.2 - self.v)
        k = np.clip(0.5 + 0.5 * n / 2.0, 0, 1)
        self.rgb *= (1.0 - amount * k)[..., None]
        self.gloss *= (1.0 - 0.3 * amount * k)
        return k

    def grain(self, amp=6.0, scale_px=2, height=0.3, seed=3):
        """표면 결 (석재 반점·콘크리트 거칠기)."""
        n = self.noise(scale_px, 1.0, 2, seed)
        self.rgb += amp * n[..., None]
        self.height += height * n * 0.1


def height_to_normal(h, strength=2.0):
    """높이맵 → OpenGL 노멀 (RGB 0~255). 행이 아래로 증가하므로 y 는 뒤집음."""
    gx = np.gradient(h, axis=1) * strength
    gy = -np.gradient(h, axis=0) * strength
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    return np.stack([-gx * nz, -gy * nz, nz], -1) * 127.5 + 127.5


def _bleed_index(filled, n):
    """칸 바깥 여백 n px 를 가장 가까운 칸 픽셀로 채우기 위한 (행, 열) 인덱스 (한 번만 계산해 모든 맵에 사용)."""
    H, W = filled.shape
    iy, ix = np.mgrid[0:H, 0:W].astype(np.int32)
    f = filled.copy()
    for _ in range(n):
        if f.all():
            break
        new = f.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(np.roll(f, dy, 0), dx, 1)
            take = src & ~new
            if take.any():
                iy[take] = np.roll(np.roll(iy, dy, 0), dx, 1)[take]
                ix[take] = np.roll(np.roll(ix, dy, 0), dx, 1)[take]
                new |= take
        f = new
    return iy, ix


def _resize(img, w, h, smooth=False):
    """간단 리사이즈 (PIL 없이). 축소 = 면적 평균, 확대 = 쌍선형."""
    img = np.asarray(img, np.float32)
    H, W = img.shape[:2]
    if H == h and W == w:
        return img.copy()
    if not smooth and H % h == 0 and W % w == 0:
        return img.reshape(h, H // h, w, W // w, -1).mean(axis=(1, 3))
    ys = (np.arange(h) + 0.5) * H / h - 0.5
    xs = (np.arange(w) + 0.5) * W / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H - 1); y1 = np.clip(y0 + 1, 0, H - 1); fy = np.clip(ys - y0, 0, 1)[:, None, None]
    x0 = np.clip(np.floor(xs).astype(int), 0, W - 1); x1 = np.clip(x0 + 1, 0, W - 1); fx = np.clip(xs - x0, 0, 1)[None, :, None]
    a = img[y0][:, x0] * (1 - fx) + img[y0][:, x1] * fx
    b = img[y1][:, x0] * (1 - fx) + img[y1][:, x1] * fx
    return a * (1 - fy) + b * fy


# =============================================================================
# PNG 읽기·쓰기 (PIL 없이 — Blender 파이썬에서도 동작)
# =============================================================================
def write_png(path, arr):
    arr = np.ascontiguousarray(np.clip(arr, 0, 255).astype(np.uint8))
    h, w = arr.shape[:2]
    c = 1 if arr.ndim == 2 else arr.shape[2]
    ct = {1: 0, 3: 2, 4: 6}[c]
    raw = np.zeros((h, w * c + 1), np.uint8)
    raw[:, 1:] = arr.reshape(h, w * c)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)))
        f.write(chunk(b"IEND", b""))


def _png_channels(path):
    with open(path, "rb") as f:
        head = f.read(26)
    return {0: 1, 2: 3, 4: 2, 6: 4}.get(head[25], 3) if head[:8] == b"\x89PNG\r\n\x1a\n" else 3


def _read_png(path):
    """8비트 PNG 읽기 (회색/RGB/RGBA, 비인터레이스). PIL 이 있으면 PIL 사용."""
    try:
        from PIL import Image
        im = Image.open(path)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else ("L" if im.mode == "L" else "RGB"))
        a = np.asarray(im, np.float32)
        return a[..., None] if a.ndim == 2 else a
    except ImportError:
        pass
    if bpy is not None:   # Blender 파이썬에는 PIL 이 없음 → Blender 이미지로 읽기 (빠름)
        img = bpy.data.images.load(os.path.abspath(path), check_existing=False)
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        a = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(a)
        bpy.data.images.remove(img)
        a = (a.reshape(h, w, 4)[::-1] * 255.0)          # Blender 는 아래 줄부터
        return a if path.lower().endswith(".png") and _png_channels(path) == 4 else a[..., :3]
    with open(path, "rb") as f:
        data = f.read()
    pos, idat, w = 8, b"", None
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        t = data[pos + 4:pos + 8]
        d = data[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", d[:10])
        elif t == b"IDAT":
            idat += d
        pos += 12 + n
    c = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    raw = np.frombuffer(zlib.decompress(idat), np.uint8)
    stride = w * c
    out = np.zeros((h, stride), np.int32)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)].astype(np.int32)
        cur = np.zeros(stride, np.int32)
        for i in range(stride):
            a = cur[i - c] if i >= c else 0
            b = prev[i]
            cc = prev[i - c] if i >= c else 0
            x = line[i]
            if ft == 1:
                x += a
            elif ft == 2:
                x += b
            elif ft == 3:
                x += (a + b) // 2
            elif ft == 4:
                p = a + b - cc
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - cc)
                x += a if (pa <= pb and pa <= pc) else (b if pb <= pc else cc)
            cur[i] = x & 255
        out[y] = cur
        prev = cur
    return out.reshape(h, w, c).astype(np.float32)


# =============================================================================
# 창문
# =============================================================================
class WindowSet:
    """창문 면 모음. add() 로 창(바깥에서 본 왼쪽 아래부터 반시계 4점)을 넣고, 같은 세대·층(unit, floor)끼리 묶어 UV 배정."""

    def __init__(self):
        self.items = []

    def add_face(self, axis, c, s, a0, a1, z0, z1, floor, unit):
        """벽면 기준 창: 벽 앞 WIN_OFF, LOD2 는 LOD2_WIN_OFF."""
        self.items.append(dict(pts=face_pts(axis, c + s * WIN_OFF, s, a0, a1, z0, z1),
                               pts2=face_pts(axis, c + s * LOD2_WIN_OFF, s, a0, a1, z0, z1),
                               ww=a1 - a0, hh=z1 - z0, floor=floor, unit=unit))

    def add_pts(self, pts, pts_lod2, ww, hh, floor, unit):
        self.items.append(dict(pts=pts, pts2=pts_lod2, ww=ww, hh=hh, floor=floor, unit=unit))

    def build(self, grid=REF_GRID):
        """UV 배정 후 (main/LOD1 용, LOD2 용) MeshBuilder 반환."""
        cells = grid * grid
        units = max([w["unit"] for w in self.items] + [0]) + 1
        stride = 7 if math.gcd(7, cells) == 1 else 11
        per = {}
        for w in self.items:
            per.setdefault(((w["floor"] * units + w["unit"]) * stride) % cells, []).append(w)
        n = max(1, math.ceil(math.sqrt(max([len(v) for v in per.values()] + [1]))))
        cs = 1.0 / grid
        slot = cs / n
        pad = slot * 0.08
        inner = slot - 2 * pad
        for cell, lst in per.items():
            cx, cy = cell % grid, cell // grid
            for j, w in enumerate(lst):
                u0 = cx * cs + (j % n) * slot + pad
                v0 = cy * cs + (j // n) * slot + pad
                k = inner / max(w["ww"], w["hh"])
                w["uv"] = [(u0, v0), (u0 + w["ww"] * k, v0), (u0 + w["ww"] * k, v0 + w["hh"] * k), (u0, v0 + w["hh"] * k)]
        a, b = MeshBuilder(), MeshBuilder()
        for w in self.items:
            a.quad(w["pts"], w["uv"], "window")
            b.quad(w["pts2"], w["uv"], "window")
        return a, b


# =============================================================================
# 내보내기
# =============================================================================
def write_obj(path, mb):
    """OBJ (Y-up: x, z, -y). 면마다 UV 4개."""
    with open(path, "w") as f:
        for x, y, z in mb.verts:
            f.write("v %.5f %.5f %.5f\n" % (x, z, -y))
        for uv4 in mb.uvs:
            for u, v in uv4:
                f.write("vt %.6f %.6f\n" % (u, v))
        for fi, face in enumerate(mb.faces):
            f.write("f " + " ".join("%d/%d" % (vi + 1, fi * 4 + k + 1) for k, vi in enumerate(face)) + "\n")


def asset_name(base, level, size_xy, front_yard=6.0, margin=2.0, lot=None):
    w, d = size_xy
    lw = lot[0] if lot else math.ceil((w + margin) / CELL_M)
    ld = lot[1] if lot else max(2, math.ceil((d + front_yard) / CELL_M))
    return f"{base}_L{level}_{lw}x{ld}", (lw, ld)


def export_asset(name_base, level, meshes, atlas, out_root, lod2_tex=1024, lot=None, front_yard=6.0, notes=None):
    """meshes: {"main","lod1","lod2", 선택: "gls","lod1_gls"} MeshBuilder + "windows": WindowSet.
    피벗을 바닥 중앙으로 옮기고, 이름(로트 포함)을 정한 뒤, 텍스처·OBJ(또는 FBX)·manifest.json 을 씀. 반환: (폴더, 요약 dict)"""
    lod2_tex = min(lod2_tex, atlas.size)
    win_main, win_lod2 = meshes["windows"].build() if meshes.get("windows") else (MeshBuilder(), MeshBuilder())
    parts = {k: meshes.get(k) or MeshBuilder() for k in ("main", "lod1", "lod2", "gls", "lod1_gls")}
    parts.update(win=win_main, lod1_win=_copy(win_main), lod2_win=win_lod2)
    M = parts["main"]
    xs = [v[0] for v in M.verts]; ys = [v[1] for v in M.verts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    for k in PARTS:
        parts[k].shift(-cx, -cy)
    size = (max(xs) - min(xs), max(ys) - min(ys), max(v[2] for v in M.verts))
    asset, lot_wd = asset_name(name_base, level, size[:2], front_yard=front_yard, lot=lot)
    folder = os.path.join(out_root, asset)
    os.makedirs(folder, exist_ok=True)
    # 텍스처. 게임은 메시 이름으로 <메시>_<맵>.png 를 찾으므로 LOD1 맵도 같은 내용으로 반드시 있어야 한다.
    # 없으면 LOD1 이 유리처럼 그려져 중간 거리에서 벽이 비친다(lod_check 의 NO_TEXTURE 검사).
    for suffix, arr in atlas.render().items():
        path = os.path.join(folder, f"{asset}_{suffix}.png")
        write_png(path, arr)
        shutil.copyfile(path, os.path.join(folder, f"{asset}_LOD1_{suffix}.png"))
    for suffix, arr in atlas.render(size=lod2_tex).items():
        write_png(os.path.join(folder, f"{asset}_LOD2_{suffix}.png"), arr)
    warns = []
    if "_" in name_base:
        warns.append("underscore inside name is not allowed")
    if max(lot_wd) > ZONED_MAX:
        warns.append(f"lot {lot_wd[0]}x{lot_wd[1]} > 6x6 -> register as signature building")
    if parts["lod1"].tri_count >= LOD1_MAX_RATIO * M.tri_count:
        warns.append("LOD1 >= 50% of main tris")
    if parts["lod2"].tri_count > LOD2_MAX_TRIS:
        warns.append("LOD2 > 500 tris")
    if M.tri_count > MAIN_SOFT_MAX:
        warns.append("main > 95000 tris")
    summary = dict(asset=asset, lot=lot_wd, size=[round(s, 3) for s in size], pivot_shift=[-cx, -cy],
                   tris={k: parts[k].tri_count for k in PARTS}, windows=len(win_main.faces), tex=atlas.size,
                   lod1_tex=atlas.size, lod2_tex=lod2_tex, warnings=warns, notes=notes or {})
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(dict(summary, atlas=atlas.to_json(), tags={k: sorted(set(parts[k].tags)) for k in PARTS}), f,
                  ensure_ascii=False, indent=1)
    chk = os.path.join(folder, "_check")                  # 검사·미리보기용 OBJ (게임에 넣지 않음)
    os.makedirs(chk, exist_ok=True)
    for k in PARTS:
        if parts[k].faces:
            write_obj(os.path.join(chk, asset + SUFFIX[k] + ".obj"), parts[k])
    if bpy is None:
        mode = "OBJ only (no Blender - FBX needs run_blender.py)"
    else:
        _bl_export(asset, folder, parts)
        mode = "FBX + .blend"
    print(f"[cs2kit] {asset}  [{mode}{' Blender %d.%d' % bpy.app.version[:2] if bpy else ''}]  size {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} m  lot {lot_wd[0]}x{lot_wd[1]}")
    print("[cs2kit] tris " + ", ".join(f"{k}={v}" for k, v in summary["tris"].items() if v) + f", windows {summary['windows']}")
    for w in warns:
        print("[cs2kit][WARN] " + w)
    return folder, summary


def _copy(mb):
    c = MeshBuilder()
    c.merge(mb)
    return c


# ---- Blender
def _bl_material(name, tex_path):
    """Blender 4.x / 5.x 공통. 5.0 부터 use_nodes 는 폐기(항상 노드 사용) → 버전에 따라 건너뜀,
    기본 노드가 없으면 Principled BSDF + 출력 노드를 직접 만듦."""
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.abspath(tex_path), check_existing=True)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs:
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    return mat


def _bl_object(mb, name, coll, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(mb.verts, [], mb.faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for k, li in enumerate(poly.loop_indices):
            uv.data[li].uv = mb.uvs[poly.index][k]
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def _bl_export(asset, folder, parts):
    names = [asset + SUFFIX[k] for k in PARTS]
    for n in names:
        if bpy.data.objects.get(n):
            bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
    coll = bpy.data.collections.new("CS2_" + asset)
    bpy.context.scene.collection.children.link(coll)
    objs = {}
    for k in PARTS:
        if not parts[k].faces:
            continue
        mat = None
        if k in ("main", "lod1"):
            mat = _bl_material(asset + SUFFIX[k], os.path.join(folder, f"{asset}_BaseColor.png"))
        elif k == "lod2":
            mat = _bl_material(asset + SUFFIX[k], os.path.join(folder, f"{asset}_LOD2_BaseColor.png"))
        objs[k] = _bl_object(parts[k], asset + SUFFIX[k], coll, mat)
    for k, ob in objs.items():
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.export_scene.fbx(filepath=os.path.join(folder, ob.name + ".fbx"), use_selection=True,
                                 object_types={"MESH"}, apply_unit_scale=True, apply_scale_options=FBX_SCALE_OPTION,
                                 axis_forward="-Z", axis_up="Y", bake_space_transform=True, mesh_smooth_type="FACE",
                                 add_leaf_bones=False, bake_anim=False, path_mode="STRIP", embed_textures=False)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, asset + ".blend"), copy=True)
    except Exception as e:  # noqa
        print("[cs2kit] .blend save failed:", e)


def out_dir_from_argv(default="output"):
    """blender --python gen.py -- --out 폴더  /  python gen.py --out 폴더"""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if "--out" in argv:
        return argv[argv.index("--out") + 1]
    try:   # default = <folder of the generator script>/output  (the project folder), not the current folder
        main_file = os.path.abspath(sys.modules["__main__"].__file__)
        return os.path.join(os.path.dirname(main_file), default)
    except Exception:
        return default
