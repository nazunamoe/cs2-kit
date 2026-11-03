# render the exported asset from the VR photo camera (distance, fov, camera height)
# usage: blender -b asset.blend -P photo_cam.py -- az_deg cam_h dist fov_v resx resy out.png
import bpy, sys, math
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
az, cam_h, dist, fov, rx, ry, ocx, ocy, out = float(a[0]), float(a[1]), float(a[2]), float(a[3]), int(a[4]), int(a[5]), float(a[6]), float(a[7]), a[8]
sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH" and ("LOD" in o.name or o.name == "Cube"):
        bpy.data.objects.remove(o, do_unlink=True)
meshes = [o for o in sc.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
xs = [p.x for p in pts]
ys = [p.y for p in pts]
cx = ocx
cy = ocy
azr = math.radians(az)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.angle_y = math.radians(fov)
cam.data.sensor_fit = "VERTICAL"
cam.location = (cx + dist * math.sin(azr), cy + dist * math.cos(azr), cam_h)
cam.rotation_euler = (math.radians(90), 0.0, math.pi - azr)
sc.render.resolution_x = rx
sc.render.resolution_y = ry
sc.render.resolution_percentage = 100
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.display.shading.show_cavity = True
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
sc.render.film_transparent = False
sc.view_settings.view_transform = "Standard"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("WROTE", out)
