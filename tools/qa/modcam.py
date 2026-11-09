# 에셋 .blend 를 지정한 카메라(위치·목표·렌즈)로 렌더 (낮은 거리에서 올려다보기, meta 카메라 재현). LOD·Cube 는 지운다.
# usage: blender -b asset.blend -P tools/qa/modcam.py -- out.png camx camy camz tx ty tz [lens=50] [W=1314 H=1021]
# W H 를 주면 meta 캔버스 비율 등 임의 크기, 안 주면 1314x1021
import bpy, sys, math
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
cam_p = Vector(tuple(float(v) for v in a[1:4]))
tgt = Vector(tuple(float(v) for v in a[4:7]))
lens = float(a[7]) if len(a) > 7 else 50
W = int(float(a[8])) if len(a) > 8 else 1314
H = int(float(a[9])) if len(a) > 9 else 1021
sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH" and ("LOD" in o.name or o.name == "Cube"):
        bpy.data.objects.remove(o, do_unlink=True)
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = W, H
cd = bpy.data.cameras.new("c")
cd.lens = lens
cd.clip_end = 3000
cam = bpy.data.objects.new("c", cd)
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = cam_p
d = tgt - cam_p
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
sc.world = sc.world or bpy.data.worlds.new("w")
sc.render.filepath = out
bpy.ops.render.render(write_still=True)