# Blender side of tools/qa/probe.py: cast rays through photo pixels into an asset .blend.
# usage: blender -b asset.blend -P tools/qa/probe_bl.py -- request.json
# request.json: pos, target (asset coords), lens, W, H, pixels [[x, y], ...], cells (atlas cells from manifest.json), pivot [px, py]
# Prints one "PROBE {json}" line per pixel.
import json
import math
import sys

import bpy
from mathutils import Vector

req = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
W, H = int(req["W"]), int(req["H"])
px0, py0 = req.get("pivot", [0.0, 0.0])
cells = req.get("cells", {})
ATLAS = 4096.0

sc = bpy.context.scene
for o in list(bpy.data.objects):                       # LOD meshes and the default cube must not take the hit
    if o.type == "MESH" and ("LOD" in o.name or o.name == "Cube"):
        bpy.data.objects.remove(o, do_unlink=True)
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.resolution_percentage = 100
cd = bpy.data.cameras.new("probe_cam")
cd.lens = float(req["lens"])
cd.sensor_fit = "AUTO"
cd.clip_end = 3000
cam = bpy.data.objects.new("probe_cam", cd)
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = Vector(req["pos"])
cam.rotation_euler = (Vector(req["target"]) - Vector(req["pos"])).to_track_quat("-Z", "Y").to_euler()
bpy.context.view_layer.update()

# rays come from the camera's own view frame, so a probe pixel is the same pixel as in the cmp_cam / modcam render
vf = cd.view_frame(scene=sc)
xs, ys = [v.x for v in vf], [v.y for v in vf]
x0, x1, y0, y1, zf = min(xs), max(xs), min(ys), max(ys), vf[0].z
R = cam.matrix_world.to_3x3()
origin = cam.matrix_world.translation.copy()
dg = bpy.context.evaluated_depsgraph_get()


def region_at(u, v):
    X, Y = u * ATLAS, (1.0 - v) * ATLAS
    for name, c in cells.items():
        x, y, w, h = c["rect"]
        if x <= X < x + w and y <= Y < y + h:
            return name
    return "?"


for (x, y) in req["pixels"]:
    u, v = x / W, 1.0 - y / H
    d = (R @ Vector((x0 + u * (x1 - x0), y0 + v * (y1 - y0), zf))).normalized()
    ok, loc, n, idx, ob, _m = sc.ray_cast(dg, origin, d)
    if not ok:
        print("PROBE " + json.dumps({"px": [x, y], "hit": False}))
        continue
    me = ob.data
    p = me.polygons[idx]
    uvl = me.uv_layers.active.data if me.uv_layers.active else None
    reg = "?"
    if uvl is not None:
        uu = sum(uvl[i].uv[0] for i in p.loop_indices) / p.loop_total
        vv = sum(uvl[i].uv[1] for i in p.loop_indices) / p.loop_total
        reg = region_at(uu, vv)
    nw = (ob.matrix_world.to_3x3() @ n).normalized()
    print("PROBE " + json.dumps({
        "px": [round(x, 1), round(y, 1)], "hit": True,
        "object": ob.name, "kind": "window" if ob.name.endswith("_Win") else "main",
        "region": reg, "normal": [round(c, 2) for c in nw],
        "asset_xyz": [round(c, 2) for c in loc],
        "generator_xyz": [round(loc[0] - px0, 2), round(loc[1] - py0, 2), round(loc[2], 2)],
        "distance": round((loc - origin).length, 2), "face_area": round(p.area, 3)}))
