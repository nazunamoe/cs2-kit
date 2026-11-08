# Blender 안에서 도는 부분 (lod_check.py 가 부른다). Blender 앱과 bpy 모듈 둘 다에서 동작한다.
# 게임처럼 뒷면을 그리지 않고(backface culling) 메인 / LOD1 / LOD2 의 실루엣을 여러 각도에서 그려,
# 메인은 막혀 있는데 LOD 는 뒤가 보이는 픽셀(= 게임에서 "투명해 보이는" 곳)을 센다.
# 사용: blender -b <asset.blend> -P lod_check_bl.py -- <asset.blend> <out_dir> <res> <n_az> <elevs,>
#       python lod_check_bl.py -- <asset.blend> <out_dir> <res> <n_az> <elevs,>      (bpy 모듈)
import bpy, sys, math, os, json
from mathutils import Vector
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
blend, out_dir, res, n_az = a[0], a[1], int(a[2]), int(a[3])
elevs = [float(e) for e in a[4].split(",")]
if blend and os.path.abspath(blend) != os.path.abspath(bpy.data.filepath or ""):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))   # bpy 모듈: -b 로 열지 않으므로 직접 연다
os.makedirs(out_dir, exist_ok=True)

sc = bpy.context.scene
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name != "Cube"]
base = min((o.name for o in meshes), key=len)            # 메인 = 이름이 가장 짧은 것
groups = {
    "main": [o for o in meshes if o.name in (base, base + "_Win")],
    "lod1": [o for o in meshes if o.name in (base + "_LOD1", base + "_LOD1_Win")],
    "lod2": [o for o in meshes if o.name in (base + "_LOD2", base + "_LOD2_Win")],
}
groups = {k: v for k, v in groups.items() if v}

sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "FLAT"
sh.color_type = "SINGLE"
sh.single_color = (1, 1, 1)
sh.show_backface_culling = True                            # 게임과 같게: 뒷면은 안 보임
sh.background_type = "VIEWPORT"
sh.background_color = (0, 0, 0)
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = False
sc.render.resolution_x = sc.render.resolution_y = res
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "BW"
# 마스크는 >0.5 이진 판정이라 AA 가 경계만 흐리고 느리다 (512² 132 ms -> 28 ms).
# 컴포지터/시퀀서도 마스크 렌더에는 필요 없다.
sc.display.render_aa = "OFF"
sc.render.use_compositing = False
sc.render.use_sequencer = False

pts = [o.matrix_world @ Vector(c) for o in groups["main"] for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr, size = (lo + hi) / 2, (hi - lo).length

# 땅: 아래에서 올려다볼 때 건물 바닥(원래 면이 없음)이 보이지 않게 검은 판으로 가린다 (게임에서도 땅에 가려짐)
sh.color_type = "OBJECT"
for o in meshes:
    o.color = (1, 1, 1, 1)
bpy.ops.mesh.primitive_cube_add(size=1)
ground = bpy.context.active_object
ground.scale = (size * 20, size * 20, 0.98)
ground.location = (ctr.x, ctr.y, -0.51)
ground.color = (0, 0, 0, 1)
for o in bpy.data.objects:                                 # 내보내기 남은 기본 Cube 등은 숨김
    if o.type == "MESH" and o not in meshes and o is not ground:
        o.hide_render = True

cd = bpy.data.cameras.new("chk")
cd.type = "ORTHO"
cd.ortho_scale = size * 1.02
cd.clip_end = size * 10
cam = bpy.data.objects.new("chk", cd)
sc.collection.objects.link(cam)
sc.camera = cam


_PX = np.empty(res * res * 4, np.float32)      # 재사용 버퍼 (pixels[:] 는 67 ms, foreach_get 은 0.8 ms)


def render_mask(objs, path, cull=True):
    sh.show_backface_culling = cull
    for o in meshes:
        o.hide_render = o not in objs
    ground.hide_render = False
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path, check_existing=False)
    img.pixels.foreach_get(_PX)
    px = _PX.reshape(res, res, 4)[::-1, :, 0]
    bpy.data.images.remove(img)
    return px > 0.5


def locate(objs, hole, d, n=4):
    """구멍 픽셀 덩어리(16 px 칸) 큰 것 n 개: 그 픽셀로 광선을 쏴 처음 맞는 면(= 비쳐 보이는 뒷면)의 위치·법선·객체"""
    rr, cc = np.nonzero(hole)
    if not len(rr):
        return []
    bins = {}
    for r, c in zip(rr, cc):
        bins.setdefault((r // 16, c // 16), []).append((r, c))
    out = []
    right, up = cam.matrix_world.col[0].xyz.normalized(), cam.matrix_world.col[1].xyz.normalized()
    for pts_ in sorted(bins.values(), key=len, reverse=True)[:n]:
        r, c = pts_[len(pts_) // 2]
        u, v = (c + 0.5) / res - 0.5, 0.5 - (r + 0.5) / res
        org = cam.location + right * u * cd.ortho_scale + up * v * cd.ortho_scale
        best = None
        for o in objs:
            mi = o.matrix_world.inverted()
            ok, loc, nrm, _ = o.ray_cast(mi @ org, (mi.to_3x3() @ (-d)).normalized())
            if ok:
                wl = o.matrix_world @ loc
                dist = (wl - org).length
                if best is None or dist < best[0]:
                    best = (dist, wl, (o.matrix_world.to_3x3() @ nrm).normalized(), o.name)
        if best:
            out.append(dict(px=len(pts_), xyz=[round(v_, 2) for v_ in best[1]], normal=[round(v_, 2) for v_ in best[2]],
                            obj=best[3]))
    return out


rows = []
tmp = os.path.join(out_dir, "_tmp.png")
for el in elevs:
    for k in range(n_az):
        az = 360.0 * k / n_az
        d = Vector((math.sin(math.radians(az)) * math.cos(math.radians(el)),
                    -math.cos(math.radians(az)) * math.cos(math.radians(el)),
                    math.sin(math.radians(el))))
        cam.location = ctr + d * size * 3
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        masks = {g: render_mask(objs, tmp) for g, objs in groups.items()}
        ref = masks["main"]
        n_ref = max(int(ref.sum()), 1)
        for g in ("lod1", "lod2", "main"):
            if g not in masks:
                continue
            # 투명 = 앞면이 없어서 건물 안쪽의 뒷면이 비치는 곳: 뒷면을 그리면 막히고(cull off) 안 그리면 뚫림(cull on).
            # (LOD 가 일부러 뺀 크라운 틀 같은 단순화는 뒤에 아무것도 없으니 세지 않는다)
            back = render_mask(groups[g], tmp, cull=False)
            hole = back & ~masks[g]
            if g != "main":
                hole &= ref                                   # 메인도 막혀 있는 자리만
            h_in = hole
            pct = 100.0 * h_in.sum() / n_ref
            rows.append(dict(lod=g, az=az, el=el, hole_pct=round(pct, 3), hole_px=int(h_in.sum()),
                             where=locate(groups[g], h_in, d) if pct > 0 else []))
            if pct > 0.02:                                    # 임계 근접 구멍도 그림/좌표로 남김: 흰 = 메인, 빨강 = 구멍
                rgb = np.zeros((res, res, 3), np.uint8)
                rgb[ref] = (90, 90, 90)
                rgb[masks[g]] = (220, 220, 220)
                rgb[h_in] = (255, 0, 0)
                im = bpy.data.images.new("dbg", res, res)
                rgba = np.concatenate([rgb[::-1].astype(np.float32) / 255, np.ones((res, res, 1), np.float32)], axis=2)
                im.pixels = rgba.ravel()
                im.filepath_raw = os.path.join(out_dir, f"{g}_az{int(az):03d}_el{int(el):+03d}.png")
                im.file_format = "PNG"
                im.save()
                bpy.data.images.remove(im)
if os.path.exists(tmp):
    os.remove(tmp)
json.dump(dict(asset=base, rows=rows), open(os.path.join(out_dir, "lod_check.json"), "w"), indent=1)
print("LODCHECK_DONE", base)
