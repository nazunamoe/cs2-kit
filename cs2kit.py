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
    """사각면 목록. 면마다 꼭짓점 UV와 태그(아틀라스 칸 이름)."""

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

    def tri(self, pts, uv3, tag):
        i = len(self.verts)
        self.verts.extend(tuple(float(c) for c in p) for p in pts)
        self.faces.append((i, i + 1, i + 2))
        self.uvs.append([tuple(map(float, t)) for t in uv3])
        self.tags.append(tag)

    def rect(self, pts, region):
        """평면 사각형 하나에 영역 입히기. 타일 재질이면 실제 크기 타일로 쪼개 붙임."""
        A = self.atlas
        if A is not None and A.is_tiled(region) and self.split_tiles:
            self._tiled(pts, region)
        else:
            self.quad(pts, A.uv(region) if A is not None else [(0, 0), (1, 0), (1, 1), (0, 1)], region)

    def _tiled(self, pts, region):
        # 스칼라 계산은 순수 float 로 한다. 타일 하나마다 작은 numpy 배열을 만들면
        # ufunc 호출 오버헤드가 지배해 같은 작업이 약 3.6배 느려진다 (측정).
        (p0x, p0y, p0z), (p1x, p1y, p1z), _p2, (p3x, p3y, p3z) = pts
        dx, dy, dz = p1x - p0x, p1y - p0y, p1z - p0z
        W = (dx * dx + dy * dy + dz * dz) ** 0.5
        gx, gy, gz = p3x - p0x, p3y - p0y, p3z - p0z
        H = (gx * gx + gy * gy + gz * gz) ** 0.5
        if W < 1e-6 or H < 1e-6:
            return
        tw, th = self.atlas.tile_size(region)
        ex, ey, ez = dx / W, dy / W, dz / W            # 가로 단위벡터
        fx, fy, fz = gx / H, gy / H, gz / H            # 세로 단위벡터
        nx, ny = max(1, math.ceil(W / tw - 1e-6)), max(1, math.ceil(H / th - 1e-6))
        quad, uvt = self.quad, self.atlas.uv_tile
        for j in range(ny):
            b0 = j * th
            b1 = H if j == ny - 1 else (j + 1) * th       # 마지막 줄은 H 에서 자름
            bx0, by0, bz0 = fx * b0, fy * b0, fz * b0
            bx1, by1, bz1 = fx * b1, fy * b1, fz * b1
            for i in range(nx):
                a0 = i * tw
                a1 = W if i == nx - 1 else (i + 1) * tw
                ax0, ay0, az0 = ex * a0, ey * a0, ez * a0
                ax1, ay1, az1 = ex * a1, ey * a1, ez * a1
                q = [(p0x + ax0 + bx0, p0y + ay0 + by0, p0z + az0 + bz0),
                     (p0x + ax1 + bx0, p0y + ay1 + by0, p0z + az1 + bz0),
                     (p0x + ax1 + bx1, p0y + ay1 + by1, p0z + az1 + bz1),
                     (p0x + ax0 + bx1, p0y + ay0 + by1, p0z + az0 + bz1)]
                quad(q, uvt(region, a1 - a0, b1 - b0, variant=(i * 7 + j * 3)), region)

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
        return sum(len(face) - 2 for face in self.faces)


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
# 표준 평면 프리셋 + 소켓 장식 (아직 실제 건물로 검증 안 됨)
# -----------------------------------------------------------------------------
# BuildingMeta 가 들고 다니는 좌표계 규칙 (모두 이 규칙을 지켜야 서로 맞물림):
#   - normal_deg: atan2(nx, ny) % 360 식으로 구한 벽의 바깥 법선 방위각.
#     front(-Y 바깥)=180, back(+Y 바깥)=0, left(-X 바깥)=270, right(+X 바깥)=90.
#   - ROOF_PERIMETER / FLOOR_RINGS 의 각 링은 위에서 봤을 때 반시계(CCW) 순서로 둔다.
#     그래야 _wall_from_segment() 가 변마다 바깥쪽 axis/c/s 를 자동으로 맞게 구한다.
# =============================================================================
class QualityStage:
    """장식 디테일 단계. preset_*/attach_* 함수에 공통으로 넘긴다."""
    FULL = 0            # 원본: 베벨, 음각 홈, 난간 메시 봉+유리 전부
    SIMPLIFY_RAIL = 1   # 난간을 스트립/알파컷 패널로, 베벨 제거
    SIMPLIFY_TRIM = 2   # 보조 음각 홈·몰딩 생략, 창틀 단순화
    LOD_CULL = 3        # 장식 함수는 아무것도 만들지 않음(LOD1/LOD2 박스화용)


class BuildingMeta:
    """preset_* 가 반환하는, attach_*/apply_facade_paint_grid 가 참조하는 건물 매스 메타데이터.
    월드 좌표를 다시 계산하지 않도록, 장식·도색 함수는 전부 이 안의 값만 읽는다."""

    def __init__(self, mb):
        self.mb = mb
        self.WALLS = {}            # wall_id(str) -> dict(axis,c,s,a0,a1,z0,z1,normal_deg,row_z=[...])
        self.ROOF_PERIMETER = []   # [(x,y), ...] 옥상 외곽 링 (CCW)
        self.FLOOR_RINGS = {}      # floor_index(int) -> [(x,y), ...] 그 층 슬래브 상단 링 (CCW)
        self.ENTRANCE_SOCKETS = []  # [{"pos":(x,y), "facing_deg":.., "bay_index":N}]
        self.CORNER_WALLS = []     # [(wall_id_a, wall_id_b), ...] 커튼월 코너 처리가 필요한 벽 쌍


def _wall_from_segment(x0, y0, x1, y1):
    """ROOF_PERIMETER/FLOOR_RINGS 의 변(x0,y0)->(x1,y1) (축 정렬, CCW 링 전제)에서
    axbox/paint 가 쓰는 axis/c/s/a0/a1 을 구한다. 바깥 법선 = 진행 방향을 -90도 돌린 것."""
    dx, dy = x1 - x0, y1 - y0
    nx, ny = dy, -dx
    if abs(dy) < 1e-6:          # 가로 변 -> axis 'y' 벽
        return "y", y0, (1 if ny > 0 else -1), min(x0, x1), max(x0, x1)
    return "x", x0, (1 if nx > 0 else -1), min(y0, y1), max(y0, y1)


def preset_plate_apartment(A, W, D, floors, floor_h, ground_h=4.5, bays=4,
                            core="back", balcony=True, railing="glass",
                            paint_main="wall", quality_stage=QualityStage.FULL):
    """판상형 4베이 주동 매스: 가로 W x 깊이 D 상자, 저층부(ground_h) + floors 개 상층(floor_h).
    발코니 슬래브(옵션)·후면 계단실 코어까지 만들고, 창·난간 디테일은 attach_*/생성기 쪽 몫으로 남긴다.
    반환: BuildingMeta (WALLS: front/back/left/right, FLOOR_RINGS, ENTRANCE_SOCKETS 1개)."""
    mb = MeshBuilder(A)
    meta = BuildingMeta(mb)
    z_top = ground_h + floors * floor_h
    mb.box(-W / 2, W / 2, 0, D, 0, z_top, paint_main, skip=("bottom",))
    meta.WALLS["front"] = dict(axis="y", c=0, s=-1, a0=-W / 2, a1=W / 2, z0=0, z1=z_top, normal_deg=180.0)
    meta.WALLS["back"] = dict(axis="y", c=D, s=1, a0=-W / 2, a1=W / 2, z0=0, z1=z_top, normal_deg=0.0)
    meta.WALLS["left"] = dict(axis="x", c=-W / 2, s=-1, a0=0, a1=D, z0=0, z1=z_top, normal_deg=270.0)
    meta.WALLS["right"] = dict(axis="x", c=W / 2, s=1, a0=0, a1=D, z0=0, z1=z_top, normal_deg=90.0)
    row_z = [0.0, ground_h] + [ground_h + f * floor_h for f in range(1, floors + 1)]
    for w in meta.WALLS.values():
        w["row_z"] = row_z
    meta.ROOF_PERIMETER = [(-W / 2, 0), (W / 2, 0), (W / 2, D), (-W / 2, D)]
    for f in range(floors + 1):
        meta.FLOOR_RINGS[f] = list(meta.ROOF_PERIMETER)
    if core == "back":
        core_w = min(W * 0.3, 6.0)
        mb.box(-core_w / 2, core_w / 2, D, D + 3.0, 0, z_top, "core", skip=("bottom",))
    if balcony and quality_stage < QualityStage.LOD_CULL:
        depth = 1.2
        for f in range(floors):
            z0 = ground_h + f * floor_h
            mb.box(-W / 2 + 1.0, W / 2 - 1.0, -depth, 0, z0, z0 + 0.15, "slab", skip=("top",))
            # 난간(railing)은 유리/철제 종류에 따라 생성기가 K.paint/K.axbox 로 직접 올린다 (TASK.md railing 규칙).
    meta.ENTRANCE_SOCKETS.append(dict(pos=(0.0, 0.0), facing_deg=180.0, bay_index=bays // 2))
    return meta


def preset_tower_l_core(A, wing_a, wing_b, floors, floor_h, core_pos="corner",
                         corner_curtainwall=True, quality_stage=QualityStage.FULL):
    """타워형 L자 코어 매스. wing_a=(length_x, width_y): 원점에서 +X로 뻗는 날개.
    wing_b=(length_y, width_x): wing_a 의 +Y 쪽(끝에서 폭 by_w 만큼)에서 +Y로 뻗는 날개(두 날개가
    (0, ax_w)~(by_w, ax_w) 구간에서 맞물려 L자가 된다). 반환: BuildingMeta.
    corner_curtainwall=True 면 두 날개가 만나는 바깥 모서리 두 벽을 CORNER_WALLS 에 적어 두고(실제
    커튼월 메시는 생성기가 K.curtainwall + K.corner_post 로 직접 만든다 — 프리셋은 좌표만 알려준다)."""
    ax_len, ax_w = wing_a
    by_len, by_w = wing_b
    z_top = floors * floor_h
    mb = MeshBuilder(A)
    meta = BuildingMeta(mb)
    mb.box(0, ax_len, 0, ax_w, 0, z_top, "wall", skip=("bottom",))
    mb.box(0, by_w, ax_w, ax_w + by_len, 0, z_top, "wall", skip=("bottom",))
    meta.WALLS["wing_a_front"] = dict(axis="y", c=0, s=-1, a0=0, a1=ax_len, z0=0, z1=z_top, normal_deg=180.0)
    meta.WALLS["wing_a_end"] = dict(axis="x", c=ax_len, s=1, a0=0, a1=ax_w, z0=0, z1=z_top, normal_deg=90.0)
    meta.WALLS["wing_b_side"] = dict(axis="x", c=0, s=-1, a0=ax_w, a1=ax_w + by_len, z0=0, z1=z_top, normal_deg=270.0)
    meta.WALLS["wing_b_end"] = dict(axis="y", c=ax_w + by_len, s=1, a0=0, a1=by_w, z0=0, z1=z_top, normal_deg=0.0)
    row_z = [floor_h * f for f in range(floors + 1)]
    for w in meta.WALLS.values():
        w["row_z"] = row_z
    meta.ROOF_PERIMETER = [(0, 0), (ax_len, 0), (ax_len, ax_w), (by_w, ax_w),
                            (by_w, ax_w + by_len), (0, ax_w + by_len)]
    for f in range(floors + 1):
        meta.FLOOR_RINGS[f] = list(meta.ROOF_PERIMETER)
    if core_pos == "corner":
        cw = min(by_w, ax_w)
        mb.box(0, cw, ax_w - cw, ax_w, 0, z_top, "core", skip=("bottom",))
    if corner_curtainwall:
        meta.CORNER_WALLS.append(("wing_a_end", "wing_b_side"))
    meta.ENTRANCE_SOCKETS.append(dict(pos=(by_w / 2, ax_w / 2), facing_deg=180.0, bay_index=0))
    return meta


def preset_piloti_base(meta, piloti_h, column_grid, lobby_bay, quality_stage=QualityStage.FULL):
    """기존 BuildingMeta 의 'front'(또는 'wing_a_front') 벽 1층에 필로티 기둥 배열 + 공동현관
    로비 매스를 덧붙인다. lobby_bay = (a0, a1): 로비가 막는 구간(그 구간엔 기둥을 안 세운다).
    주의: 기둥을 벽 앞면 바로 바깥(깊이 column_grid*0 ~ 0.5m)에만 둔다 — 실제 필로티는
    보통 건물 가장자리에서 더 안쪽으로 들어간 구조이므로, 건물마다 사진으로 실제 기둥 깊이를 확인해야 한다."""
    front = meta.WALLS.get("front") or meta.WALLS.get("wing_a_front")
    if front is None:
        raise ValueError("preset_piloti_base: meta has no 'front' wall")
    a0, a1 = front["a0"], front["a1"]
    col_size = 0.5
    lb0, lb1 = lobby_bay
    if quality_stage < QualityStage.LOD_CULL:
        a = a0 + column_grid
        while a < a1 - 1e-6:
            if not (lb0 - col_size <= a <= lb1 + col_size):
                axbox(meta.mb, front["axis"], front["c"], front["s"], a - col_size / 2, a + col_size / 2,
                      0, col_size, 0, piloti_h, "column")
            a += column_grid
    axbox(meta.mb, front["axis"], front["c"], front["s"], lb0, lb1, 0, 2.0, 0, piloti_h, "wall")
    meta.ENTRANCE_SOCKETS.append(dict(pos=((lb0 + lb1) / 2, 0.0), facing_deg=front["normal_deg"], bay_index=0))
    return meta


def attach_roof_crown(meta, style="parapet_light", height=1.2, quality_stage=QualityStage.FULL):
    """ROOF_PERIMETER 를 따라 파라펫(+선택적 경관 조명 띠)을 붙인다. style: plain | parapet_light | mechanical_screen."""
    if quality_stage >= QualityStage.LOD_CULL or not meta.ROOF_PERIMETER:
        return
    z_tops = [w["z1"] for w in meta.WALLS.values() if isinstance(w, dict) and "z1" in w]
    if not z_tops:
        return
    z0 = max(z_tops)
    depth = 0.6 if style == "mechanical_screen" else 0.3
    ring = meta.ROOF_PERIMETER
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        if math.hypot(x1 - x0, y1 - y0) < 0.5:
            continue
        axis, c, s, a0, a1 = _wall_from_segment(x0, y0, x1, y1)
        axbox(meta.mb, axis, c, s, a0, a1, 0, depth, z0, z0 + min(height, 0.9), "parapet")
        if quality_stage < QualityStage.SIMPLIFY_TRIM:
            axbox(meta.mb, axis, c, s, a0, a1, depth * 0.6, depth, z0 + min(height, 0.9),
                  z0 + min(height, 0.9) + 0.1, "coping")
        if style == "parapet_light" and quality_stage < QualityStage.SIMPLIFY_RAIL:
            paint(meta.mb, axis, c, s, a0, a1, z0 + min(height, 0.9) - 0.05, z0 + min(height, 0.9), "light_strip")


def attach_cornice_band(meta, target_floors, depth=0.15, height=0.3, quality_stage=QualityStage.FULL):
    """FLOOR_RINGS[f] 를 따라 돌출 몰딩(코니스) 띠를 붙인다. target_floors = 적용할 층 인덱스 목록."""
    if quality_stage >= QualityStage.LOD_CULL:
        return
    for f in target_floors:
        ring = meta.FLOOR_RINGS.get(f)
        if not ring:
            continue
        z = None
        for w in meta.WALLS.values():
            if isinstance(w, dict) and "row_z" in w and f < len(w["row_z"]):
                z = w["row_z"][f]
                break
        if z is None:
            continue
        n = len(ring)
        for i in range(n):
            x0, y0 = ring[i]
            x1, y1 = ring[(i + 1) % n]
            if math.hypot(x1 - x0, y1 - y0) < 0.3:
                continue
            axis, c, s, a0, a1 = _wall_from_segment(x0, y0, x1, y1)
            axbox(meta.mb, axis, c, s, a0, a1, 0, depth, z, z + height, "cornice")


def attach_entrance_canopy(meta, bay_index, style="flat", quality_stage=QualityStage.FULL):
    """ENTRANCE_SOCKETS[bay_index] 자리에 문주 캐노피를 붙인다(얇은 슬래브 + 기둥, LESSONS 규칙).
    style: flat(평슬래브) | gable(박공, 아직 flat 과 동일 - 추후 보강)."""
    if quality_stage >= QualityStage.LOD_CULL:
        return
    if bay_index >= len(meta.ENTRANCE_SOCKETS):
        raise IndexError("attach_entrance_canopy: no ENTRANCE_SOCKETS[%d]" % bay_index)
    sock = meta.ENTRANCE_SOCKETS[bay_index]
    px, py = sock["pos"]
    rad = math.radians(sock["facing_deg"])
    ndx, ndy = math.sin(rad), math.cos(rad)   # normal_deg 규약과 맞춘 바깥 방향 단위벡터
    depth, width = 1.8, 3.0
    h0, h1 = 3.0, 3.3
    ex, ey = px + ndx * depth, py + ndy * depth
    if abs(ndx) > abs(ndy):
        x0, x1 = sorted((px, ex))
        y0, y1 = py - width / 2, py + width / 2
    else:
        y0, y1 = sorted((py, ey))
        x0, x1 = px - width / 2, px + width / 2
    meta.mb.box(x0, x1, y0, y1, h0, h1, "canopy", skip=("bottom",))
    if quality_stage < QualityStage.SIMPLIFY_TRIM:
        post = 0.25
        for cx, cy in ((x0, y0), (x1, y1)):
            meta.mb.box(cx - post / 2, cx + post / 2, cy - post / 2, cy + post / 2, 0, h0, "canopy", skip=("bottom",))


def _ring_area(ring):
    return 0.5 * sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
                     for i in range(len(ring)))


def _point_in_triangle(p, a, b, c):
    def cross(q, r, s):
        return (r[0] - q[0]) * (s[1] - q[1]) - (r[1] - q[1]) * (s[0] - q[0])
    values = (cross(a, b, p), cross(b, c, p), cross(c, a, p))
    return min(values) >= -1e-9


def _triangulate_ring(ring):
    pts = list(ring)
    triangles = []
    guard = 0
    while len(pts) > 3 and guard < len(ring) * len(ring):
        guard += 1
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 1e-9:
                continue
            if any(_point_in_triangle(p, a, b, c) for j, p in enumerate(pts)
                   if j not in (i - 1, i, (i + 1) % len(pts))):
                continue
            triangles.append((a, b, c))
            del pts[i]
            break
        else:
            raise ValueError("footprint must be a simple non-self-intersecting polygon")
    if len(pts) == 3:
        triangles.append(tuple(pts))
    return triangles


def volume_prism(A, footprint, height, z0=0.0, volume_id="volume", wall="wall", roof=None,
                 quality_stage=QualityStage.FULL, meta=None, mb=None, wall_ids=None):
    """Create one arbitrary simple polygon volume and wall-linked metadata."""
    ring = [(float(x), float(y)) for x, y in footprint]
    if len(ring) < 3:
        raise ValueError("volume footprint needs at least 3 points")
    if _ring_area(ring) < 0:
        ring.reverse()
    if abs(_ring_area(ring)) < 1e-6 or height <= 0:
        raise ValueError("volume footprint area and height must be positive")
    mb = mb or MeshBuilder(A)
    meta = meta or BuildingMeta(mb)
    if not hasattr(meta, "VOLUMES"):
        meta.VOLUMES = {}
    z1 = z0 + height
    volume = dict(volume_id=volume_id, footprint=ring, z0=z0, z1=z1,
                  roof_perimeter=ring, wall_ids=[])
    meta.VOLUMES[volume_id] = volume
    for i, p0 in enumerate(ring):
        p1 = ring[(i + 1) % len(ring)]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = dy / length, -dx / length
        wall_id = None
        if isinstance(wall_ids, dict):
            wall_id = wall_ids.get(str(i))
        elif wall_ids and i < len(wall_ids):
            wall_id = wall_ids[i]
        wall_id = wall_id or f"{volume_id}:edge_{i:02d}"
        axis, c, s, a0, a1 = _wall_from_segment(*p0, *p1)
        meta.WALLS[wall_id] = dict(wall_id=wall_id, volume_id=volume_id, axis=axis, c=c, s=s,
                                   a0=a0, a1=a1, z0=z0, z1=z1, length_m=length,
                                   p0=p0, p1=p1, normal_xy=[nx, ny],
                                   normal_deg=math.degrees(math.atan2(nx, ny)) % 360,
                                   box=[min(p0[0], p1[0]) - 0.3, max(p0[0], p1[0]) + 0.3,
                                        min(p0[1], p1[1]) - 0.3, max(p0[1], p1[1]) + 0.3, z0, z1],
                                   row_z=[z0, z1])
        volume["wall_ids"].append(wall_id)
        mb.rect([(p0[0], p0[1], z0), (p1[0], p1[1], z0),
                 (p1[0], p1[1], z1), (p0[0], p0[1], z1)], wall)
    roof_region = roof or wall
    for a, b, c in _triangulate_ring(ring):
        mb.tri([(a[0], a[1], z1), (b[0], b[1], z1), (c[0], c[1], z1)],
               A.uv(roof_region)[:3], roof_region)
    if not meta.ROOF_PERIMETER:
        meta.ROOF_PERIMETER = ring
    front = [meta.WALLS[w] for w in volume["wall_ids"] if meta.WALLS[w]["normal_xy"][1] < -0.5]
    if front:
        w = min(front, key=lambda item: (item["p0"][1] + item["p1"][1]) / 2)
        meta.ENTRANCE_SOCKETS.append(dict(pos=((w["p0"][0] + w["p1"][0]) / 2,
                                                (w["p0"][1] + w["p1"][1]) / 2),
                                           facing_deg=w["normal_deg"], bay_index=0, wall_id=w["wall_id"]))
    return meta


def wall_quad(wall, u0, u1, z0, z1, offset=0.0):
    """Normalized wall coordinates to an outward-facing quad, including angled walls."""
    if "p0" not in wall:
        a0 = wall["a0"] + (wall["a1"] - wall["a0"]) * u0
        a1 = wall["a0"] + (wall["a1"] - wall["a0"]) * u1
        return face_pts(wall["axis"], wall["c"] + wall["s"] * offset, wall["s"], a0, a1, z0, z1)
    p0, p1 = wall["p0"], wall["p1"]
    nx, ny = wall["normal_xy"]
    x0, y0 = p0[0] + (p1[0] - p0[0]) * u0 + nx * offset, p0[1] + (p1[1] - p0[1]) * u0 + ny * offset
    x1, y1 = p0[0] + (p1[0] - p0[0]) * u1 + nx * offset, p0[1] + (p1[1] - p0[1]) * u1 + ny * offset
    return [(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1)]


def feature_panel(meta, wall_id, u0, u1, z0, z1, region, offset=0.02):
    meta.mb.rect(wall_quad(meta.WALLS[wall_id], u0, u1, z0, z1, offset), region)


def wall_solid(meta, wall_id, u0, u1, z0, z1, region, offset=0.0, thickness=0.04):
    """Closed thin prism on any wall, used where a one-sided rail would disappear from behind."""
    wall = meta.WALLS[wall_id]
    back = wall_quad(wall, u0, u1, z0, z1, offset)
    front = wall_quad(wall, u0, u1, z0, z1, offset + thickness)
    b0, b1, b2, b3 = back
    f0, f1, f2, f3 = front
    faces = [list(reversed(back)), front,
             [b1, f1, f0, b0], [b2, b3, f3, f2],
             [b0, f0, f3, b3], [b1, b2, f2, f1]]
    for points in faces:
        meta.mb.rect(points, region)


def feature_window_band(meta, wins, wall_id, u0, u1, z0, z1, bays=1,
                        floor=0, unit=0, quality_stage=QualityStage.FULL):
    """Measured normalized window band; frames are omitted only at trim-cull stages."""
    wall = meta.WALLS[wall_id]
    bays = max(1, int(bays))
    width = wall.get("length_m", abs(wall["a1"] - wall["a0"]))
    for i in range(bays):
        a = u0 + (u1 - u0) * i / bays
        b = u0 + (u1 - u0) * (i + 1) / bays
        wins.add_pts(wall_quad(wall, a, b, z0, z1, WIN_OFF),
                     wall_quad(wall, a, b, z0, z1, LOD2_WIN_OFF),
                     width * (b - a), z1 - z0, floor, unit)
    if quality_stage < QualityStage.SIMPLIFY_TRIM:
        frame = 0.06
        feature_panel(meta, wall_id, u0, u1, z0, min(z1, z0 + frame), "frame", WIN_OFF + 0.02)
        feature_panel(meta, wall_id, u0, u1, max(z0, z1 - frame), z1, "frame", WIN_OFF + 0.02)
        for i in range(1, bays):
            u = u0 + (u1 - u0) * i / bays
            du = frame / max(width, 0.1) / 2
            feature_panel(meta, wall_id, max(u0, u - du), min(u1, u + du), z0 + frame, z1 - frame, "frame", WIN_OFF + 0.02)


def generic_sign_slot(meta, wall_id, u0, u1, z0, z1, quality_stage=QualityStage.FULL):
    if quality_stage < QualityStage.LOD_CULL:
        feature_panel(meta, wall_id, u0, u1, z0, z1, "sign_slot", 0.025)


def feature_shopfront(meta, wins, wall_id, u0=0.05, u1=0.95, z0=0.2, z1=2.8,
                      bays=4, sign_z=None, canopy_index=None, quality_stage=QualityStage.FULL):
    feature_window_band(meta, wins, wall_id, u0, u1, z0, z1, bays, 0, 0, quality_stage)
    if sign_z:
        generic_sign_slot(meta, wall_id, u0, u1, sign_z[0], sign_z[1], quality_stage)
    if canopy_index is not None:
        attach_entrance_canopy(meta, canopy_index, quality_stage=quality_stage)


def feature_louver_zone(meta, wall_id, u0, u1, z0, z1, spacing=0.12,
                        quality_stage=QualityStage.FULL):
    if quality_stage >= QualityStage.LOD_CULL:
        return
    feature_panel(meta, wall_id, u0, u1, z0, z1, "louver_back", 0.015)
    z = z0
    while z < z1 - 1e-6:
        feature_panel(meta, wall_id, u0, u1, z, min(z1, z + 0.035), "louver", 0.05)
        z += spacing


def feature_railing_zone(meta, gls, wall_id, u0, u1, z0, z1, spacing=0.12,
                         glass=True, quality_stage=QualityStage.FULL):
    if quality_stage >= QualityStage.LOD_CULL:
        return
    wall_solid(meta, wall_id, u0, u1, z1 - 0.06, z1, "railing", 0.025, 0.04)
    if glass:
        gls.rect(wall_quad(meta.WALLS[wall_id], u0, u1, z0, z1, 0.025), "glass")
    if quality_stage == QualityStage.FULL:
        length = meta.WALLS[wall_id].get("length_m", 1.0)
        count = max(2, int(length / spacing))
        for i in range(count + 1):
            u = u0 + (u1 - u0) * i / count
            du = min(0.008, 0.0125 / max(length, 0.1))
            wall_solid(meta, wall_id, max(u0, u - du), min(u1, u + du), z0, z1 - 0.06,
                       "railing", 0.03, 0.03)


def feature_roof_equipment(meta, volume_id, size=(2.0, 2.0), height=1.2, center=None,
                           quality_stage=QualityStage.FULL):
    if quality_stage >= QualityStage.LOD_CULL:
        return
    volume = meta.VOLUMES[volume_id]
    ring = volume["footprint"]
    cx, cy = center or ((min(x for x, _ in ring) + max(x for x, _ in ring)) / 2,
                        (min(y for _, y in ring) + max(y for _, y in ring)) / 2)
    w, d = size
    z0 = volume["z1"]
    meta.mb.box(cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2, z0, z0 + height,
                "roof_equipment", skip=("bottom",))


def feature_covered_link(meta, start, end, width=3.0, height=3.0, z0=0.0,
                         volume_id="link", quality_stage=QualityStage.FULL):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 0.1:
        raise ValueError("covered link endpoints must differ")
    nx, ny = -dy / length * width / 2, dx / length * width / 2
    ring = [(start[0] + nx, start[1] + ny), (end[0] + nx, end[1] + ny),
            (end[0] - nx, end[1] - ny), (start[0] - nx, start[1] - ny)]
    return volume_prism(meta.mb.atlas, ring, height, z0, volume_id, "canopy", "canopy",
                        quality_stage, meta, meta.mb)


def validate_volume_spec(spec):
    """Validate IDs, footprints, references, normalized ranges, and vertical ranges."""
    errors = []
    volumes = spec.get("volumes", [])
    ids = [v.get("id") for v in volumes]
    if not volumes:
        errors.append("volumes must not be empty")
    if len(set(ids)) != len(ids):
        errors.append("volume ids must be unique")
    wall_ids = set()
    for volume in volumes:
        if not volume.get("id"):
            errors.append("volume id is required")
        if len(volume.get("footprint", [])) < 3:
            errors.append(f"{volume.get('id')}: footprint needs 3 points")
        if volume.get("height", 0) <= 0:
            errors.append(f"{volume.get('id')}: height must be positive")
        named = volume.get("wall_ids")
        generated = [named.get(str(i)) if isinstance(named, dict) else named[i] if named and i < len(named)
                     else f"{volume.get('id')}:edge_{i:02d}" for i in range(len(volume.get("footprint", [])))]
        for wall_id in generated:
            if wall_id in wall_ids:
                errors.append(f"duplicate wall id: {wall_id}")
            wall_ids.add(wall_id)
    for i, item in enumerate(spec.get("openings", []) + spec.get("attachments", [])):
        wall = item.get("wall")
        if wall and wall not in wall_ids:
            errors.append(f"feature {i}: unknown wall {wall}")
        if "u0" in item and not (0 <= item["u0"] < item.get("u1", 1) <= 1):
            errors.append(f"feature {i}: invalid normalized u range")
        if "z0" in item and item.get("z1", item["z0"]) <= item["z0"]:
            errors.append(f"feature {i}: z1 must be above z0")
    if errors:
        raise ValueError("invalid volume spec: " + "; ".join(errors))
    return True


def build_volume_spec(A, spec, quality_stage=QualityStage.FULL):
    """Build a data-driven collection of volumes and wall features at one LOD stage."""
    validate_volume_spec(spec)
    mb = MeshBuilder(A, split_tiles=quality_stage < QualityStage.LOD_CULL)
    meta = BuildingMeta(mb)
    meta.VOLUMES = {}
    wins, gls = WindowSet(), MeshBuilder(A)
    for volume in spec.get("volumes", []):
        volume_prism(A, volume["footprint"], volume["height"], volume.get("z0", 0.0),
                     volume["id"], volume.get("wall", "wall"), volume.get("roof"),
                     quality_stage, meta, mb, volume.get("wall_ids"))
    features = spec.get("openings", []) + spec.get("attachments", [])
    for item in features:
        kind = item["type"]
        if kind == "window_band":
            feature_window_band(meta, wins, item["wall"], item.get("u0", 0.05), item.get("u1", 0.95),
                                item["z0"], item["z1"], item.get("bays", 1), item.get("floor", 0),
                                item.get("unit", 0), quality_stage)
        elif kind == "shopfront":
            feature_shopfront(meta, wins, item["wall"], item.get("u0", 0.05), item.get("u1", 0.95),
                              item.get("z0", 0.2), item.get("z1", 2.8), item.get("bays", 4),
                              item.get("sign_z"), item.get("canopy_index"), quality_stage)
        elif kind == "sign_slot":
            generic_sign_slot(meta, item["wall"], item["u0"], item["u1"], item["z0"], item["z1"], quality_stage)
        elif kind == "louver_zone":
            feature_louver_zone(meta, item["wall"], item["u0"], item["u1"], item["z0"], item["z1"],
                                item.get("spacing", 0.12), quality_stage)
        elif kind == "railing_zone":
            feature_railing_zone(meta, gls, item["wall"], item["u0"], item["u1"], item["z0"], item["z1"],
                                 item.get("spacing", 0.12), item.get("glass", True), quality_stage)
        elif kind == "roof_equipment":
            feature_roof_equipment(meta, item["volume"], item.get("size", (2.0, 2.0)),
                                   item.get("height", 1.2), item.get("center"), quality_stage)
        elif kind == "covered_link":
            feature_covered_link(meta, item["start"], item["end"], item.get("width", 3.0),
                                 item.get("height", 3.0), item.get("z0", 0.0),
                                 item.get("id", "link"), quality_stage)
        elif kind == "entrance_canopy":
            attach_entrance_canopy(meta, item.get("index", 0), quality_stage=quality_stage)
        else:
            raise ValueError(f"unknown feature type: {kind}")
    return dict(meta=meta, mb=mb, windows=wins, gls=gls,
                metadata=dict(volumes=meta.VOLUMES, walls=meta.WALLS))


def match_wall_ids(meta, slices, tol_deg=20.0):
    """glb_slices.py/facade_read.py 가 뽑은 wall_N(normal_deg 보유)을 meta.WALLS 의 이름 있는
    wall_id 에 각도로 최근접 매칭한다. 반환: {slices_wall_id: meta_wall_id}. tol_deg 넘으면 뺀다."""
    named = [(k, w["normal_deg"]) for k, w in meta.WALLS.items() if isinstance(w, dict) and "normal_deg" in w]
    out = {}
    for sw in slices.get("walls", []):
        best, best_d = None, 1e9
        for name, deg in named:
            d = abs((sw["normal_deg"] - deg + 180) % 360 - 180)
            if d < best_d:
                best, best_d = name, d
        if best is not None and best_d <= tol_deg:
            out[sw["id"]] = best
    return out


def hex_to_rgb(hexcol):
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _merge_grid_rects(cell_id, rows, cols):
    """rows x cols 라벨 그리드 -> (r0,r1,c0,c1,label) 사각형 목록(행 단위로 합치는 방식 — 최소
    개수는 아니지만 서로 안 겹치고 빠르다). r1/c1 은 포함(inclusive) 인덱스."""
    used = [[False] * cols for _ in range(rows)]
    rects = []
    for r in range(rows):
        c = 0
        while c < cols:
            if used[r][c]:
                c += 1
                continue
            label = cell_id[r][c]
            c2 = c
            while c2 < cols and not used[r][c2] and cell_id[r][c2] == label:
                c2 += 1
            r2 = r
            while r2 + 1 < rows and all(not used[r2 + 1][k] and cell_id[r2 + 1][k] == label for k in range(c, c2)):
                r2 += 1
            for rr in range(r, r2 + 1):
                for cc in range(c, c2):
                    used[rr][cc] = True
            rects.append((r, r2, c, c2 - 1, label))
            c = c2
    return rects


def apply_facade_paint_grid(mb, atlas, wall_meta, paint_grid, palette, layer_base=1):
    """band_scan.py 의 paint_grid.json 결과를 벽에 칠한다 (실제 메시 분할이 아니라 K.paint 오버레이 —
    docs/archive/PROPOSAL_pipeline_v2.md 의 A안). wall_meta: dict(axis,c,s,row_z=[...], col_a=[...]) — row_z/col_a 는
    그리드 행/열 경계를 실제 z/벽 거리(a)로 준 목록(len = rows+1 / cols+1). palette 의 색은 atlas 에
    없으면 "paintgrid_<id>" 이름으로 자동 등록한다. cell_id=-1 의 미확정 칸은 칠하지 않고
    기본 벽 재질로 남긴다. 반환: 실제로 칠한 사각형 목록(디버그/보고용)."""
    row_z, col_a = wall_meta["row_z"], wall_meta["col_a"]
    rows, cols = paint_grid["rows"], paint_grid["cols"]
    cell_id = paint_grid["cell_id"]
    if len(row_z) < rows + 1 or len(col_a) < cols + 1:
        raise ValueError("apply_facade_paint_grid: row_z/col_a shorter than the grid (rows=%d cols=%d)" % (rows, cols))
    for key, hexcol in palette.items():
        name = "paintgrid_%s" % key
        if name not in atlas.cells:
            atlas.add(name, color=hex_to_rgb(hexcol))
    rects = _merge_grid_rects(cell_id, rows, cols)
    layer = layer_base
    painted = []
    for (r0, r1, c0, c1, label) in rects:
        if label < 0:
            continue
        a0, a1 = col_a[c0], col_a[c1 + 1]
        z0, z1 = row_z[r0], row_z[r1 + 1]
        region = "paintgrid_%s" % label
        paint(mb, wall_meta["axis"], wall_meta["c"], wall_meta["s"], a0, a1, z0, z1, region, layer=layer)
        painted.append((a0, a1, z0, z1, region, layer))
        layer += 1
    return painted


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
        self._cache = None

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
        cache = self._cache
        if cache is not None and cache[0] == len(self.order):
            # 캐시는 float32(1.2 GB)가 아니라 완성된 uint8 맵이다. 복사도, 재클램프도 필요 없다.
            return _downscale_maps(cache[1], size, S) if (size and size != S) else dict(cache[1])
        # 맵을 처음부터 uint8 로 잡고 칸 단위로만 클램프한다. 전체 4096² 맵을 float32 로 만든 뒤
        # clip+astype 하던 0.8 s(맵당 268 MB 임시배열)가 사라진다. 칸 면적 합은 아틀라스의 일부뿐이다.
        base = np.zeros((S, S, 4), np.uint8); base[..., 3] = 255
        ctrl = np.zeros((S, S, 4), np.uint8); ctrl[..., 3] = 255
        mask = np.zeros((S, S, 4), np.uint8)
        nrm = np.zeros((S, S, 3), np.uint8); nrm[...] = (128, 128, 255)
        emis = np.zeros((S, S, 3), np.uint8)
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
            base[sl][..., :3] = np.clip(ctx.rgb, 0, 255)
            base[sl][..., 3] = np.clip(ctx.alpha, 0, 255)
            ctrl[sl][..., :3] = np.clip(c["ctrl"], 0, 255)
            mask[sl][..., 0] = min(255.0, max(0.0, c["metal"] * 255))
            mask[sl][..., 3] = np.clip(ctx.gloss, 0, 1) * 255
            if c["gloss_image"]:
                g = _read_png(c["gloss_image"])
                mask[sl][..., 3] = np.clip(_resize(g[..., :1], w, h)[..., 0], 0, 255)
            if c["normal_image"]:
                nrm[sl] = np.clip(_resize(_read_png(c["normal_image"])[..., :3], w, h), 0, 255)
            elif np.ptp(ctx.height) > 1e-6:
                nrm[sl] = np.clip(height_to_normal(ctx.height, c["normal_strength"]), 0, 255)
            if c["emissive"] is not None:
                emis[sl] = np.clip(np.array(c["emissive"], np.float32) * ctx.emis[..., None], 0, 255)
        for a in (base, ctrl, mask, nrm, emis):
            _bleed_cells(a, [self.cells[n]["rect"] for n in self.order], self.pad)
        out = dict(BaseColor=base, ControlMask=ctrl, MaskMap=mask, Normal=nrm, Emissive=emis)
        self._cache = (len(self.order), out)
        return _downscale_maps(out, size, S) if (size and size != S) else dict(out)

    def _finish(self, maps):
        """호환용. render 가 이제 uint8 을 직접 만들므로 클램프·캐스팅이 필요 없다."""
        return maps


    # ---- 캐시 키: 아틀라스 정의가 같으면 텍스처 렌더·PNG 쓰기를 건너뛴다 (export_asset)
    def signature(self):
        """칸 속성 + painter 코드(상수·전역값·클로저 포함) + 사진 파일 내용 + cs2kit 렌더 코드의 해시.
        painter 안에서 정체를 알 수 없는 객체를 쓰면 None(=항상 다시 그림)."""
        import hashlib
        h = hashlib.sha1()
        h.update(repr((self.size, self.pad)).encode())
        h.update(_RENDER_SRC_SIG.encode())
        for n in self.order:
            c = self.cells[n]
            for k in sorted(c):
                v = c[k]
                if k == "painter":
                    v = _fn_sig(v) if v else None
                    if v is None and c[k]:
                        return None
                elif k in ("image", "normal_image", "gloss_image") and v:
                    try:
                        v = (v, hashlib.sha1(open(v, "rb").read()).hexdigest())
                    except OSError:
                        return None
                h.update(repr((n, k, v)).encode())
        return h.hexdigest()

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
        self.rng = np.random.default_rng(zlib.crc32(str(c["color"]).encode()) % (2 ** 31))   # hash() 는 실행마다 달라 crc32 사용

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


def _bleed_cells(arr, rects, pad):
    """칸 바깥 pad px 를 칸 가장자리 픽셀로 채운다(칸별 clamp, 제자리). 전체 이미지 roll 반복보다 수십 배 빠름.
    칸 사이 간격이 2*pad 라 서로 겹치지 않는다."""
    H, W = arr.shape[:2]
    for x, y, w, h in rects:
        y0, y1, x0, x1 = max(0, y - pad), min(H, y + h + pad), max(0, x - pad), min(W, x + w + pad)
        ys = np.clip(np.arange(y0, y1), y, y + h - 1)
        xs = np.clip(np.arange(x0, x1), x, x + w - 1)
        arr[y0:y1, x0:x1] = arr[np.ix_(ys, xs)]


def _downscale_maps(maps, size, S):
    """uint8 맵을 box filter 로 S→size 로 줄인다. float32 왕복·전체 복사 없이 uint32 누적으로 처리."""
    if not size or size == S:
        return dict(maps)
    out = {}
    if S % size:                                   # 정수배가 아니면 일반 리사이즈로 폴백
        for key, a in maps.items():
            v = _resize(a, size, size)
            if key == "Normal":
                n = v / 127.5 - 1.0
                n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
                v = (n + 1.0) * 127.5
            out[key] = np.clip(v, 0, 255).astype(np.uint8)
        return out
    k = S // size
    area = k * k
    for key, a in maps.items():
        acc = a.reshape((size, k, size, k) + a.shape[2:]).sum(axis=1, dtype=np.uint32)
        acc = acc.sum(axis=2, dtype=np.uint32)
        v = (acc + area // 2) // area              # 반올림 box 평균
        if key == "Normal":
            n = v.astype(np.float32) / 127.5 - 1.0
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
            v = (n + 1.0) * 127.5
        out[key] = np.clip(v, 0, 255).astype(np.uint8)
    return out


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


def _fn_sig(fn, _depth=0):
    """함수의 바이트코드·상수·기본값·클로저 값·참조하는 전역 값으로 만든 문자열. 알 수 없으면 None."""
    import types
    if _depth > 4:
        return None
    parts = []

    def code_sig(co):
        out = [co.co_code.hex(), repr(co.co_names), repr(co.co_varnames)]
        for k in co.co_consts:
            out.append(code_sig(k) if isinstance(k, types.CodeType) else repr(k))
        return "|".join(out)

    def val(v):
        if isinstance(v, (int, float, str, bool, bytes, type(None), tuple, list, dict, set)):
            r = repr(v)
        elif isinstance(v, np.ndarray):
            r = v.tobytes().hex()[:4096] + str(v.shape)
        elif isinstance(v, types.FunctionType):
            r = _fn_sig(v, _depth + 1)
        elif isinstance(v, types.ModuleType) or isinstance(v, type):
            r = getattr(v, "__name__", "?")
        elif isinstance(v, np.generic):
            r = repr(v)
        else:
            r = repr(v)
        return None if (r is None or " at 0x" in r) else r

    f = fn.func if hasattr(fn, "func") else fn           # functools.partial
    if not isinstance(f, types.FunctionType):
        return None
    parts.append(code_sig(f.__code__))
    for name in f.__code__.co_names:
        if name in f.__globals__:
            r = val(f.__globals__[name])
            if r is None:
                return None
            parts.append(name + "=" + r)
    for d in (f.__defaults__ or ()):
        r = val(d)
        if r is None:
            return None
        parts.append(r)
    for cell in (f.__closure__ or ()):
        try:
            r = val(cell.cell_contents)
        except ValueError:
            r = "empty"
        if r is None:
            return None
        parts.append(r)
    if hasattr(fn, "args"):
        parts.append(repr((fn.args, sorted(fn.keywords.items()))))
    return "\n".join(parts)


def _src_sig():
    import hashlib
    try:
        return hashlib.sha1(open(__file__, "rb").read()).hexdigest()
    except OSError:
        return str(__import__("time").time_ns())


_RENDER_SRC_SIG = _src_sig()


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
    a = np.asarray(arr)
    if a.dtype != np.uint8:                       # 이미 uint8 이면 clip/astype 복사(맵당 134 MB)를 건너뛴다
        a = np.clip(a, 0, 255).astype(np.uint8)
    if not a.flags.c_contiguous:
        a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    c = 1 if a.ndim == 2 else a.shape[2]
    ct = {1: 0, 3: 2, 4: 6}[c]
    raw = np.empty((h, w * c + 1), np.uint8)
    raw[:, 0] = 0                                 # 필터 타입 0
    raw[:, 1:] = a.reshape(h, w * c)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))     # 버퍼를 그대로 넘겨 tobytes 복사(67 MB) 생략
        f.write(chunk(b"IEND", b""))


def _write_pngs(jobs, workers=4):
    """여러 PNG 를 스레드로 동시에 압축한다. zlib 은 압축 중 GIL 을 놓아주므로 실제로 빨라진다.
    한 장이라도 실패하면 순차 실행으로 폴백한다."""
    if len(jobs) < 2 or (os.cpu_count() or 1) < 2:
        for p, a in jobs:
            write_png(p, a)
        return
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as ex:
            for _ in ex.map(lambda j: write_png(*j), jobs):
                pass
    except Exception:                                  # noqa: BLE001
        for p, a in jobs:
            write_png(p, a)


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
def wall_window_layout(length, spec=None):
    """Length-based window bays with optional per-wall overrides.

    spec keys: kind ("windows" or "blank"), bays, width, margin, min_width, gap.
    Returns (spans, gaps), where spans are (s0, s1, width) and gaps are
    (centre, width).  This is the table-friendly version used by facade edits:

        WALL_WINDOWS = {
            "mass_01_00:edge_06": dict(bays=3, width=1.20, margin=0.45),
            "mass_01_00:edge_10": dict(bays=2, width=0.80, margin=0.20),
            "mass_01_00:edge_05": dict(kind="blank"),
        }
        spans, gaps = K.wall_window_layout(wall["length_m"],
                                           WALL_WINDOWS.get(wall["wall_id"]))
    """
    spec = dict(spec or {})
    if spec.get("kind") in ("blank", "none", "solid"):
        return [], []
    length = float(length)
    if length < 1.45:
        return [], []
    margin = float(spec.get("margin", min(0.55, max(0.22, length * 0.06))))
    usable = length - 2.0 * margin
    if usable < 1.0:
        return [], []
    width = float(spec.get("width", 1.85))
    min_width = float(spec.get("min_width", 0.90))
    bays = spec.get("bays")
    if bays is None:
        bays = max(1, int(round(usable / float(spec.get("target_pitch", 2.75)))))
    bays = max(1, int(bays))
    gap = float(spec.get("gap", 0.30))
    ww = min(width, (usable - (bays - 1) * gap) / bays)
    if ww < min_width:
        bays = 1
        ww = min(width, usable)
    pitch = usable / bays
    spans = []
    for i in range(bays):
        c = margin + pitch * (i + 0.5)
        spans.append((c - ww / 2.0, c + ww / 2.0, ww))
    gaps = []
    for i in range(len(spans) - 1):
        g0, g1 = spans[i][1], spans[i + 1][0]
        gaps.append(((g0 + g1) / 2.0, g1 - g0))
    return spans, gaps


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

    def build(self, grid=REF_GRID, atlas=None):
        """UV 배정 후 (main/LOD1 용, LOD2 용) MeshBuilder 반환.

        atlas is given: the 0..1 reference grid is mapped into the atlas
        "window" cell, so the win mesh samples the window texture instead of
        every atlas cell (which showed wall/stone control colours at night).
        """
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
        wr = None
        if atlas is not None and "window" in getattr(atlas, "cells", {}):
            wr = atlas._uvrect("window")
        a, b = MeshBuilder(), MeshBuilder()
        for w in self.items:
            uv = w["uv"]
            if wr:
                u0, v0, u1, v1 = wr
                du, dv = u1 - u0, v1 - v0
                uv = [(u0 + u * du, v0 + v * dv) for u, v in uv]
            a.quad(w["pts"], uv, "window")
            b.quad(w["pts2"], uv, "window")
        return a, b


# =============================================================================
# 내보내기
# =============================================================================
def write_obj(path, mb):
    """OBJ (Y-up: x, z, -y). 면마다 꼭짓점 UV.
    같은 내용을 <path>.npz 로도 남긴다 - check/render/backface_check 가 OBJ 텍스트를 다시 파싱하지 않는다."""
    with open(path, "w") as f:
        for x, y, z in mb.verts:
            f.write("v %.5f %.5f %.5f\n" % (x, z, -y))
        for uv4 in mb.uvs:
            for u, v in uv4:
                f.write("vt %.6f %.6f\n" % (u, v))
        offset = 0
        for face in mb.faces:
            f.write("f " + " ".join("%d/%d" % (vi + 1, offset + k + 1) for k, vi in enumerate(face)) + "\n")
            offset += len(face)
    _write_obj_cache(path, mb)


OBJ_CACHE_VERSION = 1


def _write_obj_cache(path, mb):
    """OBJ 옆에 npz 사이드카. 실패해도 빌드는 계속한다 (캐시는 최적화일 뿐)."""
    try:
        n = len(mb.faces)
        if not n:
            return
        st = os.stat(path)
        key = f"{OBJ_CACHE_VERSION}:{st.st_size}:{st.st_mtime_ns}"
        # OBJ 는 %.5f/%.6f 로 반올림해 쓰므로, 캐시도 같은 정밀도로 맞춘다.
        # (텍스트 경로와 캐시 경로가 다른 좌표를 내면 검사 결과가 환경에 따라 달라진다)
        raw = np.array(mb.verts, np.float64).reshape(-1, 3)
        V = np.round(raw, 5)          # OBJ 는 %.5f 로 쓰고 로더가 원좌표로 되돌리므로 캐시도 같은 값
        F = np.array([f if len(f) == 4 else (f[0], f[1], f[2], f[2]) for f in mb.faces], np.int32)
        FL = np.array([len(f) for f in mb.faces], np.uint8)
        UVT = np.round(np.array([p for quad in mb.uvs for p in quad], np.float64).reshape(-1, 2), 6)
        UVO = np.zeros(n, np.int32)
        UVO[1:] = np.cumsum(FL[:-1], dtype=np.int32)
        tmp = path + ".npz.tmp"
        with open(tmp, "wb") as fh:
            np.savez(fh, key=np.array(key), V=V, F=F, FL=FL, UVT=UVT, UVO=UVO)
        os.replace(tmp, path + ".npz")
    except Exception:                                     # noqa: BLE001 - 캐시 실패는 무시
        pass


def asset_name(base, level, size_xy, front_yard=6.0, margin=2.0, lot=None):
    w, d = size_xy
    lw = lot[0] if lot else math.ceil((w + margin) / CELL_M)
    ld = lot[1] if lot else max(2, math.ceil((d + front_yard) / CELL_M))
    return f"{base}_L{level}_{lw}x{ld}", (lw, ld)


def export_asset(name_base, level, meshes, atlas, out_root, lod2_tex=1024, lot=None, front_yard=6.0, notes=None, metadata=None):
    """meshes: {"main","lod1","lod2", 선택: "gls","lod1_gls"} MeshBuilder + "windows": WindowSet.
    피벗을 바닥 중앙으로 옮기고, 이름(로트 포함)을 정한 뒤, 텍스처·OBJ(또는 FBX)·manifest.json 을 씀. 반환: (폴더, 요약 dict)"""
    lod2_tex = min(lod2_tex, atlas.size)
    win_main, win_lod2 = (meshes["windows"].build(atlas=atlas) if meshes.get("windows")
                          else (MeshBuilder(), MeshBuilder()))
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
    # 아틀라스 정의(칸·painter·사진)가 지난번과 같고 PNG 가 다 있으면 렌더·쓰기를 건너뛴다 (기하만 고칠 때 14초 -> 0초).
    maps = ("BaseColor", "ControlMask", "MaskMap", "Normal", "Emissive")
    chk0 = os.path.join(folder, "_check")
    os.makedirs(chk0, exist_ok=True)
    keyf = os.path.join(chk0, "atlas.key")
    sig = atlas.signature()
    key = f"{sig} lod2={lod2_tex}" if sig else None
    files = [f"{asset}_{m}.png" for m in maps] + [f"{asset}_LOD1_{m}.png" for m in maps] + [f"{asset}_LOD2_{m}.png" for m in maps]
    cached = False
    if key and os.path.exists(keyf) and all(os.path.exists(os.path.join(folder, f)) for f in files):
        try:
            cached = open(keyf, encoding="utf-8").read().strip() == key
        except OSError:
            pass
    if cached:
        print("[cs2kit] atlas textures unchanged - reused (cache)")
    else:
        if os.path.exists(keyf):
            os.remove(keyf)
        full = atlas.render()
        lod2 = atlas.render(size=lod2_tex)
        jobs = [(os.path.join(folder, f"{asset}_{s}.png"), a) for s, a in full.items()]
        jobs += [(os.path.join(folder, f"{asset}_LOD2_{s}.png"), a) for s, a in lod2.items()]
        _write_pngs(jobs)
        for suffix in full:
            shutil.copyfile(os.path.join(folder, f"{asset}_{suffix}.png"),
                            os.path.join(folder, f"{asset}_LOD1_{suffix}.png"))
        if key:
            with open(keyf, "w", encoding="utf-8") as f:
                f.write(key)
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
        json.dump(dict(summary, atlas=atlas.to_json(), tags={k: sorted(set(parts[k].tags)) for k in PARTS},
                       metadata=metadata or {}), f, ensure_ascii=False, indent=1)
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


def _bl_ensure_fbx():
    """bpy 모듈(pip)에서는 FBX 내보내기 애드온이 기본 비활성일 수 있다."""
    try:
        if "io_scene_fbx" in bpy.context.preferences.addons:
            return
        bpy.ops.preferences.addon_enable(module="io_scene_fbx")
    except Exception:                                   # noqa: BLE001 - 앱 모드에서는 이미 켜져 있음
        pass


FBX_KW = dict(use_selection=True, object_types={"MESH"}, apply_unit_scale=True, apply_scale_options=FBX_SCALE_OPTION,
              axis_forward="-Z", axis_up="Y", bake_space_transform=True, mesh_smooth_type="FACE",
              add_leaf_bones=False, bake_anim=False, path_mode="STRIP", embed_textures=False)


def _bl_fbx(filepath):
    """파트 FBX 한 개 쓰기. Blender 5.x 에는 C++ exporter(wm.fbx_export)만 있을 수 있다."""
    _bl_ensure_fbx()
    try:
        bpy.ops.export_scene.fbx(filepath=filepath, **FBX_KW)
        return
    except Exception as e:                              # noqa: BLE001
        old_err = e
    alt = dict(export_selected_objects=True, apply_unit_scale=True, bake_space_transform=True,
               mesh_smooth_type="FACE", add_leaf_bones=False, bake_anim=False, path_mode="STRIP",
               embed_textures=False, forward_axis="NEGATIVE_Z", up_axis="Y")
    props = {p.identifier for p in bpy.ops.wm.fbx_export.get_rna_type().properties}
    try:
        bpy.ops.wm.fbx_export(filepath=filepath, **{k: v for k, v in alt.items() if k in props})
    except Exception:
        raise old_err


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
