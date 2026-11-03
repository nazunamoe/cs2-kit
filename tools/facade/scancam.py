# Blender: 텍스처 스캔(한 메시)을 생성기 좌표로 옮겨 원근 카메라로 렌더 (참고용)
# usage: blender -b -P scancam.py -- <gltf> <mesh> <yaw> <out_prefix> "cx,cy,cz,tx,ty,tz,lens;..." [keep_all]
import bpy, sys, math
from mathutils import Vector, Matrix
a = sys.argv[sys.argv.index("--") + 1:]
gl, mname, yaw, out, cams = a[0], a[1], float(a[2]), a[3], a[4]
keep_all = len(a) > 5
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=gl)
keep = [o for o in bpy.data.objects if o.type == "MESH" and (mname in o.name or mname in o.data.name)][0]
for o in bpy.data.objects:
    if o.type == "MESH":
        o.data.transform(o.matrix_world); o.matrix_world = Matrix.Identity(4)
R = Matrix.Rotation(math.radians(-yaw), 4, "Z")
vs = [R @ v.co for v in keep.data.vertices]
cx = (min(v.x for v in vs) + max(v.x for v in vs)) / 2
y0 = min(v.y for v in vs); z0 = min(v.z for v in vs)
T = Matrix.Translation((-cx, -y0, -z0 - 2.0)) @ R
for o in list(bpy.data.objects):
    if o.type != "MESH": continue
    if o is keep or keep_all:
        o.data.transform(T)
    else:
        bpy.data.objects.remove(o, do_unlink=True)
print("ZMAX", max((T @ v.co).z for v in keep.data.vertices) if False else max(v.co.z for v in keep.data.vertices))
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = 1314, 1021
cd = bpy.data.cameras.new("c"); cd.clip_end = 5000
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
for i, cs in enumerate(cams.split(";")):
    v = [float(t) for t in cs.split(",")]
    cam.location = Vector(v[0:3]); cd.lens = v[6] if len(v) > 6 else 35
    cam.rotation_euler = (Vector(v[3:6]) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = "%s_%d.png" % (out, i)
    bpy.ops.render.render(write_still=True)
