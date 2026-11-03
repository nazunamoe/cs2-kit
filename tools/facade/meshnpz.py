# Blender: 스캔 메시들의 꼭짓점을 npz 로 저장 (월드 좌표, z-up)
import bpy, sys, numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
src, out, names = a[0], a[1], a[2].split(",")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
d = {}
for o in bpy.data.objects:
    if o.type == "MESH" and o.data.name in names:
        me = o.data
        V = np.array([tuple(o.matrix_world @ v.co) for v in me.vertices])
        F = np.array([tuple(p.vertices)[:3] for p in me.polygons])
        d["V" + o.data.name] = V; d["F" + o.data.name] = F
np.savez(out, **d); print("saved", list(d))
