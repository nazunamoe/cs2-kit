# render the exported asset with the exact VR photo camera (view matrix + lens)
# usage: blender -b asset.blend -P plane_cam.py -- view0,view1,...(16) lens_mm rx ry out.png
# the view matrix is three.js column major (scene units = m/100) and already mapped into
# the model frame by the caller, so the camera can simply be inverted into the world.
import bpy
import sys
from mathutils import Matrix

a = sys.argv[sys.argv.index("--") + 1:]
view = [float(x) for x in a[0].split(",")]
lens, rx, ry, out = float(a[1]), int(a[2]), int(a[3]), a[4]

sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH" and ("LOD" in o.name or o.name == "Cube"):
        bpy.data.objects.remove(o, do_unlink=True)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.sensor_fit = "HORIZONTAL"
cam.data.sensor_width = 36.0
cam.data.lens = lens
cam.data.shift_x = 0.0
cam.data.shift_y = 0.0

m = Matrix(((view[0], view[1], view[2], view[3]),
            (view[4], view[5], view[6], view[7]),
            (view[8], view[9], view[10], view[11]),
            (view[12], view[13], view[14], view[15])))
cam.matrix_world = m.inverted()

sc.render.resolution_x = rx
sc.render.resolution_y = ry
sc.render.resolution_percentage = 100
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.display.shading.show_cavity = True
sc.display.shading.background_type = "VIEWPORT"
sc.display.shading.background_color = (1, 1, 1)
sc.render.film_transparent = False
sc.view_settings.view_transform = "Standard"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("WROTE", out)
