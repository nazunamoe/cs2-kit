# textured orthographic elevations (several views in one Blender run)
# usage: blender -b -P elevs.py -- <scan.gltf> <meshname> <ppm> <out_prefix> <views...>
#   view spec: yaw:view:a0:a1:z0:z1   (yaw = rotate mesh deg, view 0=-Y 90=+X 180=+Y 270=-X)
import bpy, sys, math
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
src, mname, ppm, outp = a[0], a[1], float(a[2]), a[3]
specs = a[4:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [q for q in bpy.data.objects if q.type == "MESH" and q.data.name == mname][0]
for q in list(bpy.data.objects):
    if q is not o and q.type == "MESH":
        bpy.data.objects.remove(q, do_unlink=True)
me = o.data
me.transform(o.matrix_world)
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs))))
o.matrix_world = Matrix.Identity(4)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.clip_end = 2000
for spec in specs:
    yaw, view, a0, a1, z0, z1 = spec.split(":")
    yaw = float(yaw); view = float(view)
    a0, a1, z0, z1 = float(a0), float(a1), float(z0), float(z1)
    o.matrix_world = Matrix.Rotation(math.radians(-yaw), 4, "Z")
    w, h = a1 - a0, z1 - z0
    sc.render.resolution_x, sc.render.resolution_y = int(w * ppm), int(h * ppm)
    cam.data.ortho_scale = max(w, h)
    am, zm, d = (a0 + a1) / 2, (z0 + z1) / 2, 300
    ang = math.radians(view)
    rx, ry = math.cos(ang), math.sin(ang)
    cam.location = (rx * am + math.sin(ang) * d, ry * am - math.cos(ang) * d, zm)
    cam.rotation_euler = (math.radians(90), 0, ang)
    sc.render.filepath = "%s_y%03d_v%03d.png" % (outp, int(yaw), int(view))
    bpy.ops.render.render(write_still=True)
    print("WROTE", sc.render.filepath)
