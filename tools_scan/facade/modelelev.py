# orthographic elevation of an exported asset (.blend) in the same frame as elev.py (scan): x centred, front y = 0, ground z = 0
# usage: blender -b asset.blend -P modelelev.py -- view ppm a0 a1 z0 z1 out.png [yoff]
import bpy, sys, math
a = sys.argv[sys.argv.index("--") + 1:]
view, ppm = int(a[0]), float(a[1])
a0, a1, z0, z1, out = float(a[2]), float(a[3]), float(a[4]), float(a[5]), a[6]
yoff = float(a[7]) if len(a) > 7 else 0.0
sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH" and ("LOD" in o.name or o.name == "Cube"):
        bpy.data.objects.remove(o, do_unlink=True)
meshes = [o for o in sc.objects if o.type == "MESH"]
ys = [(o.matrix_world @ __import__("mathutils").Vector(c)).y for o in meshes for c in o.bound_box]
my = min(ys)
win = bpy.data.materials.new("winprev")
win.diffuse_color = (0.08, 0.12, 0.18, 1)
for o in meshes:
    o.location.y -= my - yoff
    if o.name.endswith("_Win"):
        o.data.materials.clear()
        o.data.materials.append(win)
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "FLAT"
sc.display.shading.color_type = "TEXTURE"
sc.view_settings.view_transform = "Standard"
w, h = a1 - a0, z1 - z0
sc.render.resolution_x, sc.render.resolution_y = int(w * ppm), int(h * ppm)
cam = bpy.data.objects.new("cam2", bpy.data.cameras.new("cam2"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(w, h)
cam.data.clip_end = 1000
am, zm, d = (a0 + a1) / 2, (z0 + z1) / 2, 200
ang = math.radians(view)
rx, ry = math.cos(ang), math.sin(ang)
cam.location = (rx * am + math.sin(ang) * d, ry * am - math.cos(ang) * d, zm)
cam.rotation_euler = (math.radians(90), 0, ang)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
