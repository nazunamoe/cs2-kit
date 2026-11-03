import bpy, sys, math, json
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
src, mname, yaw, out = a[0], a[1], float(a[2]), a[3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [q for q in bpy.data.objects if q.type == "MESH" and q.data.name == mname][0]
me = o.data; me.transform(o.matrix_world)
xs=[v.co.x for v in me.vertices]; ys=[v.co.y for v in me.vertices]; zs=[v.co.z for v in me.vertices]
raw=[(v.co.x,v.co.y,v.co.z) for v in me.vertices]
cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2; z0=min(zs)
R=Matrix.Rotation(math.radians(-yaw),4,"Z")
res=[]
for (x,y,z) in raw:
    p=R@__import__("mathutils").Vector((x-cx,y-cy,z-z0))
    res.append((x-cx, y-min(ys), z-z0, p.x, p.y))   # model x, model y(from min), z, W x, W y
json.dump(res, open(out,"w"))
print("DONE", len(res))
