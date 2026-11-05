"""Data-driven mixed-use/school example using generic volumes and wall features."""
import json
import os
import sys


def find_kit():
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(path, "cs2kit.py")):
            return path
        path = os.path.dirname(path)
    raise RuntimeError("cs2kit.py not found")


sys.path.insert(0, find_kit())
import cs2kit as K  # noqa: E402

spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generic_spec.json")
with open(spec_path, encoding="utf-8") as f:
    spec = json.load(f)

A = K.Atlas(size=4096, pad=16)
materials = {
    "wall": ((205, 204, 198), 0.0, 0.35),
    "roof": ((105, 108, 110), 0.0, 0.35),
    "frame": ((105, 112, 118), 0.65, 0.55),
    "sign_slot": ((82, 88, 92), 0.0, 0.35),
    "louver_back": ((45, 48, 50), 0.0, 0.3),
    "louver": ((115, 119, 120), 0.6, 0.5),
    "railing": ((115, 120, 123), 0.65, 0.5),
    "glass": ((135, 165, 180), 0.0, 0.8),
    "canopy": ((160, 163, 162), 0.2, 0.45),
    "roof_equipment": ((125, 128, 129), 0.3, 0.4),
}
for name, (color, metal, gloss) in materials.items():
    A.add(name, color=color, ctrl=(0, 0, 0), metal=metal, gloss=gloss, px=128)

main = K.build_volume_spec(A, spec, K.QualityStage.FULL)
lod1 = K.build_volume_spec(A, spec, K.QualityStage.SIMPLIFY_TRIM)
lod2 = K.build_volume_spec(A, spec, K.QualityStage.LOD_CULL)
K.export_asset("CivicGeneric01", 1,
               dict(main=main["mb"], lod1=lod1["mb"], lod2=lod2["mb"],
                    gls=main["gls"], lod1_gls=lod1["gls"], windows=main["windows"]),
               A, K.out_dir_from_argv("output"), metadata=main["metadata"])
