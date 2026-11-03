# 스캔 메시를 생성기 좌표로 옮겨 z>98 삼각형을 npz 로 저장
import bpy, sys, math, numpy as np
from mathutils import Matrix
a = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a[0])
keep = [o for o in bpy.data.objects if o.type == "MESH" and a[1] in o.name][0]
keep.data.transform(keep.matrix_world)
R = Matrix.Rotation(math.radians(-float(a[2])), 4, "Z"); keep.data.transform(R)
V = np.array([v.co[:] for v in keep.data.vertices])
V -= [(V[:,0].min()+V[:,0].max())/2, V[:,1].min(), V[:,2].min()+2.0]
keep.data.calc_loop_triangles()
T = np.array([t.vertices[:] for t in keep.data.loop_triangles])
np.savez(a[3], V=V, T=T)
print("SAVED", V.shape, T.shape, V.min(0), V.max(0))
