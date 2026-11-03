# scan mesh rendered from a VR meta camera (perspective, same fov/pos) -> compare with the VR photo
# usage: blender -b -P scan_photo_cam.py -- <scan.gltf> <mesh> <x> <y> <z> <yaw_deg> <fov_v> <resx> <resy> <out.png>   (blender/scan coords; yaw 0 looks +Y)
import bpy, sys, math
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
gl, mname = a[0], a[1]
x, y, z, yaw, fov, rx, ry, out = float(a[2]), float(a[3]), float(a[4]), float(a[5]), float(a[6]), int(a[7]), int(a[8]), a[9]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=gl)
keep = [o for o in bpy.data.objects if o.type == "MESH" and (mname in o.name or mname in o.data.name)][0]
for o in list(bpy.data.objects):
    if o.type == "MESH":
        o.data.transform(o.matrix_world); o.matrix_world = Matrix.Identity(4)
        if o is not keep:
            bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"; sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = rx, ry
cd = bpy.data.cameras.new("c"); cd.clip_end = 5000; cd.sensor_fit = "VERTICAL"; cd.angle_y = math.radians(fov)
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (x, y, z)
cam.rotation_euler = (math.radians(90), 0, math.radians(yaw))
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("WROTE", out)
