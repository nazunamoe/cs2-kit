# (tools/facade/scancam.py 는 생성기 좌표로 옮겨 여러 카메라, 이것은 스캔 좌표 그대로 + W H + 메시 선택)
# 스캔(gltf)을 meta 카메라(mesh 좌표 그대로)로 렌더. 사진 판정 + 스캔|모델 비교용.
# usage: blender -b -P scancam_raw.py -- <gltf> out.png camx camy camz tx ty tz lens W H [meshname]
# cam/타깃 좌표 = 스캔 메시 좌표계 (towers.npz V<fid> 와 같은, z-up).
import bpy, sys
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
gl, out = a[0], a[1]
cam_p = Vector(tuple(float(v) for v in a[2:5]))
tgt = Vector(tuple(float(v) for v in a[5:8]))
lens = float(a[8])
W, H = int(float(a[9])), int(float(a[10]))
keep = a[11] if len(a) > 11 else ""
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=gl)
if keep:
    for o in list(bpy.data.objects):
        if o.type == "MESH" and keep not in o.name and keep not in (o.data.name or ""):
            bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = W, H
cd = bpy.data.cameras.new("c"); cd.lens = lens; cd.clip_end = 5000
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = cam_p
cam.rotation_euler = (Vector(tgt) - cam_p).to_track_quat("-Z", "Y").to_euler()
sc.world = sc.world or bpy.data.worlds.new("w")
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
xs = [(o.matrix_world @ Vector(c)).x for o in sc.objects if o.type == "MESH" for c in o.bound_box]
print("BOUNDS x %.2f..%.2f" % (min(xs), max(xs)))