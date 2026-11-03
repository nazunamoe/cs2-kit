# 한 LOD 만 뒷면 숨김(게임과 같게)으로 원근 렌더: 투명 구멍 찾기용. 뒷면이 비치는 곳은 빨강
# blender -b <asset.blend> -P lodcam.py -- out.png LOD2|LOD1|main camx camy camz tx ty tz [lens]
import bpy, sys
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
out, which = a[0], a[1]
cam_p = Vector(tuple(float(v) for v in a[2:5])); tgt = Vector(tuple(float(v) for v in a[5:8]))
lens = float(a[8]) if len(a) > 8 else 50
sc = bpy.context.scene
ms = [o for o in bpy.data.objects if o.type == "MESH" and o.name != "Cube"]
base = min((o.name for o in ms), key=len)
keep = {base, base + "_Win"} if which == "main" else {base + "_" + which, base + "_" + which + "_Win"}
for o in bpy.data.objects:
    if o.type == "MESH":
        o.hide_render = o.name not in keep
# 앞면 = 텍스처, 뒷면 = 빨강 (뒷면이 보이면 그 자리는 게임에서 투명)
for o in ms:
    for m in o.data.materials:
        if m is None or not m.use_nodes:
            continue
        nt = m.node_tree
        out_n = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
        src = out_n.inputs[0].links[0].from_socket if out_n.inputs[0].links else None
        geo = nt.nodes.new("ShaderNodeNewGeometry"); red = nt.nodes.new("ShaderNodeEmission"); red.inputs[0].default_value = (1, 0, 0, 1)
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
        if src: nt.links.new(src, mix.inputs[1])
        nt.links.new(red.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out_n.inputs[0])
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 1314, 1021
cd = bpy.data.cameras.new("c"); cd.lens = lens; cd.clip_end = 5000
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); sc.camera = cam
cam.location = cam_p; cam.rotation_euler = (tgt - cam_p).to_track_quat("-Z", "Y").to_euler()
sc.world = sc.world or bpy.data.worlds.new("w")
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
