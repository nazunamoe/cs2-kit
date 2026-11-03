"""Blender 안에서 실행: 한 번 열어 여러 카메라로 연속 렌더 (tools/qa/cmp_all.py 가 부른다. 직접 쓸 일 없음).

  blender -b asset.blend -P multicam.py -- jobs.json

jobs.json = [{"az": 225, "cx": 0, "cy": 0 (선택: 바라보는 점), "cam_h": 49.1, "dist": 50, "fov": 75, "rx": 3840, "ry": 1874, "out": "<절대경로>.png"}, ...]
tools/facade/model_photo_cam.py 와 같은 카메라·셰이딩(카메라는 원점을 바라봄, 센서 세로 고정)이지만
  - 배경을 투명(RGBA)으로 렌더한다 -> 어두운 면이 배경색과 비슷해 실루엣에서 빠지는 일이 없다.
  - 장면을 한 번만 만들고 카메라만 바꿔 렌더한다 -> 사진 16장도 Blender 시작 1회.
model_photo_cam.py 는 그대로 둔다(cmp_cam.py·cmp.sh 등이 쓴다).
"""
import bpy
import json
import math
import sys

jobs = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
sc = bpy.context.scene
for o in list(bpy.data.objects):
    if o.type == "MESH" and ("LOD" in o.name or o.name == "Cube"):
        bpy.data.objects.remove(o, do_unlink=True)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.sensor_fit = "VERTICAL"
sc.render.resolution_percentage = 100
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.display.shading.show_cavity = True
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"

for j in jobs:
    azr = math.radians(j["az"])
    cam.data.angle_y = math.radians(j["fov"])
    cx, cy = j.get("cx", 0.0), j.get("cy", 0.0)                 # 바라보는 점(에셋 좌표), 기본 원점
    cam.location = (cx + j["dist"] * math.sin(azr), cy + j["dist"] * math.cos(azr), j["cam_h"])
    cam.rotation_euler = (math.radians(90), 0.0, math.pi - azr)
    sc.render.resolution_x = int(j["rx"])
    sc.render.resolution_y = int(j["ry"])
    sc.render.filepath = j["out"]
    bpy.ops.render.render(write_still=True)
    print("WROTE", j["out"])
