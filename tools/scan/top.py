# textured orthographic top view of one mesh
# usage: blender -b -P top.py -- <scan.gltf> <meshname|all> <ppm> <out.png> <x0> <x1> <y0> <y1>   (all = 장면 전체)
import bpy, sys, math
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
src, mname, ppm, out = a[0], a[1], float(a[2]), a[3]
x0, x1, y0, y1 = [float(v) for v in a[4:8]]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
if mname == "all":                      # 메시 이름 대신 all: 장면 전체(이웃 건물 포함)
    keep = [q for q in bpy.data.objects if q.type == "MESH"]
else:
    keep = [q for q in bpy.data.objects if q.type == "MESH" and q.data.name == mname][:1]
    for q in list(bpy.data.objects):
        if q.type == "MESH" and q not in keep:
            bpy.data.objects.remove(q, do_unlink=True)
xs, ys, zs = [], [], []
for o in keep:
    me = o.data
    me.transform(o.matrix_world)
    o.matrix_world = Matrix.Identity(4)
    xs += [v.co.x for v in me.vertices]; ys += [v.co.y for v in me.vertices]; zs += [v.co.z for v in me.vertices]
print("BBOX x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f" % (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = int((x1 - x0) * ppm), int((y1 - y0) * ppm)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(x1 - x0, y1 - y0)
cam.data.clip_end = 2000
cam.location = ((x0 + x1) / 2, (y0 + y1) / 2, max(zs) + 100)
cam.rotation_euler = (0, 0, 0)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("WROTE", out)
