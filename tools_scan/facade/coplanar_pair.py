# 진단용: 같은 평면·같은 방향으로 실제 겹치는 면 쌍을 정확히 찾아 꼭짓점까지 출력 (Blender 배경 실행)
# usage: blender -b <asset>.blend -P coplanar_pair.py -- <object name> [tol]
import bpy, sys
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
name = a[0]
TOL = float(a[1]) if len(a) > 1 else 0.012
ob = bpy.data.objects[name]
me = ob.data
polys = []
for p in me.polygons:
    if p.area < 1e-4:
        continue
    n = p.normal.normalized()
    polys.append((p, n, p.center.dot(n), [me.vertices[v].co.copy() for v in p.vertices]))
polys.sort(key=lambda t: t[2])


def overlap_area(A, B, n):
    """두 폴리곤(같은 평면)의 교차 면적: A 를 B 의 반평면들로 잘라 넓이"""
    u = Vector((1, 0, 0))
    if abs(n.x) > 0.9:
        u = Vector((0, 1, 0))
    u = (u - n * u.dot(n)).normalized()
    v = n.cross(u)
    poly = [(p.dot(u), p.dot(v)) for p in A]
    clip = [(p.dot(u), p.dot(v)) for p in B]
    # clip 방향(CCW) 확인
    sgn = sum(clip[i][0] * clip[(i + 1) % len(clip)][1] - clip[(i + 1) % len(clip)][0] * clip[i][1] for i in range(len(clip)))
    if sgn < 0:
        clip = clip[::-1]

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    out = poly
    for i in range(len(clip)):
        if not out:
            break
        p0, p1 = clip[i], clip[(i + 1) % len(clip)]
        inp, out2 = out, []
        for j in range(len(inp)):
            cur, nxt = inp[j], inp[(j + 1) % len(inp)]
            if cross(p0, p1, nxt) >= 0:
                if cross(p0, p1, cur) < 0:
                    # 교점
                    d0 = cross(p0, p1, cur)
                    d1 = cross(p0, p1, nxt)
                    t = d0 / (d0 - d1)
                    out2.append((cur[0] + (nxt[0] - cur[0]) * t, cur[1] + (nxt[1] - cur[1]) * t))
                out2.append(nxt)
            elif cross(p0, p1, cur) >= 0:
                d0 = cross(p0, p1, cur)
                d1 = cross(p0, p1, nxt)
                t = d0 / (d0 - d1)
                out2.append((cur[0] + (nxt[0] - cur[0]) * t, cur[1] + (nxt[1] - cur[1]) * t))
        out = out2
    if len(out) < 3:
        return 0.0
    s = sum(out[i][0] * out[(i + 1) % len(out)][1] - out[(i + 1) % len(out)][0] * out[i][1] for i in range(len(out)))
    return abs(s) / 2


found = 0
for i in range(len(polys)):
    pi, ni, di, vi = polys[i]
    for j in range(i + 1, len(polys)):
        pj, nj, dj, vj = polys[j]
        if dj - di > TOL:
            break
        if ni.dot(nj) < 0.9995 or abs(dj - di) > TOL:
            continue
        ov = overlap_area(vi, vj, ni)
        if ov > 0.0002:
            found += 1
            if found <= 8:
                print("PAIR ov=%.4f n=(%.2f,%.2f,%.2f) d=%.3f" % (ov, ni.x, ni.y, ni.z, di))
                for tag, pp, vv in (("A", pi, vi), ("B", pj, vj)):
                    print("   %s c=(%.2f,%.2f,%.2f) verts=%s" % (tag, pp.center.x, pp.center.y, pp.center.z,
                          " ".join("(%.2f,%.2f,%.2f)" % (q.x, q.y, q.z) for q in vv)))
print("total", found)
