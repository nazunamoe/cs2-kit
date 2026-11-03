# textured orthographic elevation of one scan mesh in the generator frame (reference only)
# args: gltf mesh yaw dy view(0/90/180/270 = seen from -Y/+X/+Y/-X) ppm a0 a1 z0 z1 out.png
# a = horizontal image coordinate in metres: view 0 -> x, 90 -> y, 180 -> -x, 270 -> -y (left to right as seen)
import bpy, sys, math
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
src, mname, yaw, dy, view, ppm = a[0], a[1], float(a[2]), float(a[3]), int(a[4]), float(a[5])
a0, a1, z0, z1, out = float(a[6]), float(a[7]), float(a[8]), float(a[9]), a[10]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [o for o in bpy.data.objects if o.type == "MESH" and o.data.name == mname][0]
for q in list(bpy.data.objects):
    if q is not o and q.type == "MESH":
        bpy.data.objects.remove(q, do_unlink=True)
me = o.data; me.transform(o.matrix_world); o.matrix_world = Matrix.Identity(4)
me.transform(Matrix.Rotation(math.radians(-yaw), 4, "Z"))
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zz = [v.co.z for v in me.vertices]
me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -min(ys) - dy, -min(zz))))
import os, bmesh
if os.environ.get("CLIP"):                       # CLIP="x,5,999" keeps only faces whose centre has x in [5, 999]
    ax, lo, hi = os.environ["CLIP"].split(","); ax = "xyz".index(ax); lo = float(lo); hi = float(hi)
    bm = bmesh.new(); bm.from_mesh(me)
    kill = [f for f in bm.faces if not (lo <= f.calc_center_median()[ax] <= hi)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(me); bm.free()
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"; sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
w, h = a1 - a0, z1 - z0
sc.render.resolution_x, sc.render.resolution_y = int(w * ppm), int(h * ppm)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = max(w, h); cam.data.clip_end = 1000
am, zm, d = (a0 + a1) / 2, (z0 + z1) / 2, 200
ang = math.radians(view)
# right vector of the view: view 0 -> +x, 90 -> +y, 180 -> -x, 270 -> -y
rx, ry = math.cos(ang), math.sin(ang)
cam.location = (rx * am + math.sin(ang) * d, ry * am - math.cos(ang) * d, zm)
cam.rotation_euler = (math.radians(90), 0, ang)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
