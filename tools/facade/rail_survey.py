# 옥상 난간 조사 2단계 (Blender): rail_edges.json 의 외벽 조각마다 바깥에서 벽 쪽으로 광선을 쏴 스캔 텍스처 색을 읽는다.
# usage: blender -b -P scripts/rail_survey.py -- <scan.gltf> <rail_edges.json> <out.json> [dong,dong]
# 동마다 스캔 메시를 생성기 프레임으로: -yaw 회전, x 가운데, 최소 y = 0, 최소 z = 0, 모델 z = 스캔 z - dz.
# 샘플: 조각을 따라 0.5 m 마다, 지붕 + 0.2 / 0.5 / 0.8 / 1.1 / 1.4 m. 가운데 점은 지붕 -0.6 .. +1.9 (0.1 m) 세로 단면도.
import bpy, sys, json, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform
a = sys.argv[sys.argv.index("--") + 1:]
src, edges_path, out_path = a[0], a[1], a[2]
only = a[3].split(",") if len(a) > 3 else None
SHIFT = [float(v) for v in a[4].split(",")] if len(a) > 4 else [0.0, 0.0]   # extra (dx, dy) of the scan in the generator frame
SEARCH = len(a) > 5
SR, SS = (float(a[5]), float(a[6])) if len(a) > 6 else (3.0, 0.25)
FRAME = {"101": ("939940", 6.0, 2.0), "102": ("939939", 6.5, 3.4), "103": ("939936", 94.5, 3.4), "104": ("939927", 6.5, 3.2),
         "105": ("942970", -84.5, 2.0), "106": ("939923", 27.4, 2.0), "107": ("939915", 56.1, 2.15), "108": ("939916", -33.9, 2.1)}
edges = json.load(open(edges_path))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
pix_cache = {}


def img_of(mat):
    if mat is None or not mat.use_nodes:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            return n.image
    return None


def pixels(img):
    if img.name not in pix_cache:
        w, h = img.size
        p = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
        pix_cache[img.name] = (w, h, p)
    return pix_cache[img.name]


res = []
for dong, (mname, yaw, dz) in FRAME.items():
    if only and dong not in only:
        continue
    E = [e for e in edges if e["dong"] == dong]
    if not E:
        continue
    ob = [o for o in bpy.data.objects if o.type == "MESH" and (mname in o.name or mname in o.data.name)][0]
    me = ob.data
    R = Matrix.Rotation(math.radians(-yaw), 4, "Z")
    V = [R @ (ob.matrix_world @ v.co) for v in me.vertices]
    cx = (min(v.x for v in V) + max(v.x for v in V)) / 2
    y0 = min(v.y for v in V)
    z0 = min(v.z for v in V)
    V = [Vector((v.x - cx + SHIFT[0], v.y - y0 + SHIFT[1], v.z - z0 - dz)) for v in V]
    polys = [tuple(p.vertices) for p in me.polygons]
    bvh = BVHTree.FromPolygons(V, polys)
    uvl = me.uv_layers.active.data
    loops = [tuple(p.loop_indices) for p in me.polygons]
    mats = [img_of(ob.material_slots[p.material_index].material) if ob.material_slots else None for p in me.polygons]

    def sample(x, y, z, nx, ny):
        o = Vector((x + nx * 4.0, y + ny * 4.0, z))
        hit, nrm, fi, dist = bvh.ray_cast(o, Vector((-nx, -ny, 0.0)), 8.0)
        if hit is None:
            return None
        img = mats[fi]
        off = 4.0 - dist                                   # + = surface in front of the expected wall line
        if img is None:
            return dict(off=off, rgb=None)
        vi = polys[fi][:3]
        li = loops[fi][:3]
        uv = barycentric_transform(hit, V[vi[0]], V[vi[1]], V[vi[2]],
                                   Vector((*uvl[li[0]].uv, 0)), Vector((*uvl[li[1]].uv, 0)), Vector((*uvl[li[2]].uv, 0)))
        w, h, p = pixels(img)
        px, py = int((uv.x % 1.0) * (w - 1)), int((uv.y % 1.0) * (h - 1))
        return dict(off=off, rgb=[int(255 * c) for c in p[py, px, :3]])

    if SEARCH:                                             # grid search of the frame shift: hits within 0.3 m of the wall line
        best = []
        for sx in np.arange(-SR, SR + 0.01, SS):
            for sy in np.arange(-SR, SR + 0.01, SS):
                good = 0
                for e in E[::2]:
                    rot, (mx, my) = math.radians(e["rot"]), e["move"]
                    cr, sr = math.cos(rot), math.sin(rot)
                    t = (e["a0"] + e["a1"]) / 2
                    px, py = (t, e["c"]) if e["axis"] == "y" else (e["c"], t)
                    nr = (0.0, float(e["s"])) if e["axis"] == "y" else (float(e["s"]), 0.0)
                    x, y = cr * px - sr * py + mx - sx, sr * px + cr * py + my - sy
                    nx, ny = cr * nr[0] - sr * nr[1], sr * nr[0] + cr * nr[1]
                    q = sample(x, y, e["slab"] - 3.0, nx, ny)
                    good += q is not None and abs(q["off"]) < 0.3
                best.append((good, sx, sy))
        best.sort(reverse=True)
        print("SEARCH", dong, best[:6])
        continue
    for e in E:
        rot, (mx, my) = math.radians(e["rot"]), e["move"]
        cr, sr = math.cos(rot), math.sin(rot)
        tw = lambda x, y: (cr * x - sr * y + mx, sr * x + cr * y + my)
        if e["axis"] == "y":
            nrm = (0.0, float(e["s"]))
            pt = lambda t: (t, e["c"])
        else:
            nrm = (float(e["s"]), 0.0)
            pt = lambda t: (e["c"], t)
        nx, ny = cr * nrm[0] - sr * nrm[1], sr * nrm[0] + cr * nrm[1]
        L = e["a1"] - e["a0"]
        n = max(1, int(L / 0.5))
        S = []
        for k in range(n):
            t = e["a0"] + (k + 0.5) * L / n
            x, y = tw(*pt(t))
            S.append([t, [sample(x, y, e["slab"] + dzb, nx, ny) for dzb in (0.2, 0.5, 0.8, 1.1, 1.4)]])
        x, y = tw(*pt((e["a0"] + e["a1"]) / 2))
        prof = [[round(dzb, 2), sample(x, y, e["slab"] + dzb, nx, ny)] for dzb in np.arange(-0.6, 1.95, 0.1)]
        res.append(dict(e, samples=S, profile=prof))
    print("done", dong, len(E))
json.dump(res, open(out_path, "w"))
