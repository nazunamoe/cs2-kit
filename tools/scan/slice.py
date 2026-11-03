# horizontal sections of one scan mesh (generator frame: rotated by -yaw, x centred, front y=0, ground z=0)
import bpy, bmesh, sys, math
from mathutils import Matrix, Vector
a = sys.argv[sys.argv.index("--") + 1:]
src, mname, yaw = a[0], a[1], float(a[2])
zs = [float(v) for v in a[3].split(",")]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [o for o in bpy.data.objects if o.type == "MESH" and o.data.name == mname][0]
me = o.data; me.transform(o.matrix_world)
me.transform(Matrix.Rotation(math.radians(-yaw), 4, "Z"))
xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zz = [v.co.z for v in me.vertices]
me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2, -min(ys), -min(zz))))
print("BBOX", max(xs) - min(xs), max(ys) - min(ys), max(zz) - min(zz))
for z in zs:
    bm = bmesh.new(); bm.from_mesh(me)
    r = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, z), plane_no=(0, 0, 1))
    pts = [e for e in r["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    segs = [((round(e.verts[0].co.x, 1), round(e.verts[0].co.y, 1)), (round(e.verts[1].co.x, 1), round(e.verts[1].co.y, 1))) for e in pts]
    segs = [s for s in segs if math.dist(s[0], s[1]) > 0.25]
    print("Z %.1f n=%d" % (z, len(segs)))
    for s in sorted(segs):
        print("  %6.1f %6.1f -> %6.1f %6.1f" % (s[0][0], s[0][1], s[1][0], s[1][1]))
    bm.free()
# vertical: max z per 1 m grid cell from vertices of faces facing up
top = {}
for f in me.polygons:
    if f.normal.z > 0.9:
        c = f.center
        for v in f.vertices:
            p = me.vertices[v].co
        k = (round(c.x), round(c.y))
        top[k] = max(top.get(k, 0), c.z)
print("ROOFS")
for f in sorted(me.polygons, key=lambda f: -f.center.z):
    if f.normal.z > 0.9 and f.area > 4:
        vs = [me.vertices[i].co for i in f.vertices]
        print("  z %6.1f area %6.1f x %6.1f..%6.1f y %6.1f..%6.1f" % (f.center.z, f.area, min(v.x for v in vs), max(v.x for v in vs), min(v.y for v in vs), max(v.y for v in vs)))
