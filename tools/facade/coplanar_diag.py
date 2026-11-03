# 진단용: 출력 .blend 의 한 메시에서 같은 평면·같은 방향이 겹치는 면 쌍을 재질·좌표와 함께 출력
# usage: blender -b <asset>.blend -P coplanar_diag.py -- <mesh name substring> [tol]
import bpy, sys
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
sub = a[0]
tol = float(a[1]) if len(a) > 1 else 0.004
ob = [o for o in bpy.data.objects if o.type == "MESH" and sub in o.name][0]
me = ob.data
me.calc_loop_triangles()
groups = {}
for p in me.polygons:
    n = p.normal
    key = (round(n.x, 1), round(n.y, 1), round(n.z, 1))
    d = round(p.center.dot(n), 1)
    groups.setdefault((key, d), []).append(p)
n = 0
def bb(p):
    xs = [me.vertices[v].co for v in p.vertices]
    return (min(v.x for v in xs), max(v.x for v in xs), min(v.y for v in xs), max(v.y for v in xs),
            min(v.z for v in xs), max(v.z for v in xs))


for (key, d), ps in groups.items():
    if len(ps) < 2:
        continue
    for i in range(len(ps)):
        ci, ai = ps[i].center, ps[i].area
        bi = bb(ps[i])
        for j in range(i + 1, len(ps)):
            cj = ps[j].center
            bj = bb(ps[j])
            ox = min(bi[1], bj[1]) - max(bi[0], bj[0])
            oy = min(bi[3], bj[3]) - max(bi[2], bj[2])
            oz = min(bi[5], bj[5]) - max(bi[4], bj[4])
            ov = max(0.0, ox) * max(0.0, oy) * max(0.0, oz)
            if ov > 0.0005:
                mi = me.materials[ps[i].material_index].name if me.materials else "-"
                mj = me.materials[ps[j].material_index].name if me.materials else "-"
                print("PAIR n=%s d=%.2f ov=%.4f A=(%.2f,%.2f,%.2f) %s %.3f bb=(%.2f,%.2f,%.2f,%.2f,%.2f,%.2f) | B=(%.2f,%.2f,%.2f) %s %.3f" % (
                    key, d, ov, ci.x, ci.y, ci.z, mi, ai, bi[0], bi[1], bi[2], bi[3], bi[4], bi[5],
                    cj.x, cj.y, cj.z, mj, ps[j].area))
                n += 1
print("pairs", n)
