"""게임용 사본: 에셋을 Z 축 기준 90° 단위로 돌려 게임의 도로 쪽(정면 = -Y)을 다른 면으로 바꾼다.

생성기와 output/<asset>/ 는 건드리지 않는다. 원본 .blend 의 메시를 그대로 읽어 회전(거울 아님)을
메시 데이터에 적용하고, 원본과 같은 FBX 설정으로 <out>/<asset>/ 에 다시 내보낸다. PNG 맵은 그대로 복사한다
(UV 는 바뀌지 않음). 90/270 은 가로·세로가 바뀌므로 로트를 다시 계산하고(front_yard 6 m 기본값),
에셋·메시·PNG 이름의 로트 부분도 같이 바꾼다(게임은 <메시>_<맵>.png 로 텍스처를 찾는다).

  python tools/game_flip.py projects/P/output/<asset> [...] --out projects/P/output_game --front back
  --front front|back|left|right : 게임에서 도로 쪽이 될 생성기 면 (기본 back)
  --rot 0|90|180|270            : 위에서 본 반시계 회전 각도 (--front 대신; 90 = left 면이 도로 쪽, 270 = right)
  --suffix R                    : 이름 끝에 붙임(<base>R_L1_..). 같은 이름이면 게임이 이전에 가져온 에셋을 그대로 쓴다

검증(같은 Blender 실행 안): 새 FBX 와 원본 FBX 를 다시 읽어 정점이 회전 행렬로 정확히 대응하는지,
삼각형 수·bbox 크기가 맞는지 확인하고 FLIP OK / FLIP FAIL 을 출력한다.
180° 사본은 원본과 이름이 같으므로 게임에는 원본 또는 사본 한쪽만 넣는다.
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLIP_TAG = "game_flip"
FRONT_TO_ROT = {"front": 0, "left": 90, "back": 180, "right": 270}   # generator face that ends up facing the road
NAME_RE = re.compile(r"^(?P<base>.+)_L(?P<level>\d+)_(?P<w>\d+)x(?P<d>\d+)$")


def _blender_exe():
    p = os.path.join(KIT, "tools", "blender_path.txt")
    if os.path.exists(p):
        exe = open(p, encoding="utf-8").read().strip()
        if os.path.isfile(exe):
            return exe
    sys.exit("[game_flip] Blender not found - run `python tools/run_blender.py --find`")


def _opt(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        val = argv[i + 1]
        del argv[i:i + 2]
        return val
    return None


def new_asset_name(asset, rot, size, suffix=""):
    """90/270: footprint swaps -> recompute the lot with cs2kit.asset_name (default front_yard).
    suffix: appended to the base name so the game does not reuse an asset it already imported under the old name."""
    if rot % 180 == 0 and not suffix:
        return asset
    m = NAME_RE.match(asset)
    if not m:
        sys.exit(f"[game_flip] cannot parse asset name {asset}")
    if rot % 180 == 0:
        return f"{m['base']}{suffix}_L{m['level']}_{m['w']}x{m['d']}"
    sys.path.insert(0, KIT)
    import cs2kit as K
    name, _ = K.asset_name(m["base"] + suffix, int(m["level"]), (size[1], size[0]))
    return name


def _outer(argv):
    argv = list(argv)
    out_root = _opt(argv, "--out")
    front = _opt(argv, "--front")
    rot = _opt(argv, "--rot")
    suffix = _opt(argv, "--suffix") or ""
    if not re.fullmatch(r"[A-Za-z0-9]*", suffix):
        sys.exit("[game_flip] --suffix: letters and digits only (no underscore)")
    if out_root is None or not argv:
        sys.exit(__doc__)
    if rot is not None and front is not None:
        sys.exit("[game_flip] give --front or --rot, not both")
    if rot is None:
        front = front or "back"
        if front not in FRONT_TO_ROT:
            sys.exit(f"[game_flip] --front must be one of {', '.join(FRONT_TO_ROT)}")
        rot = FRONT_TO_ROT[front]
    else:
        rot = int(rot) % 360
        if rot % 90:
            sys.exit("[game_flip] --rot must be a multiple of 90")
    road_face = {v: k for k, v in FRONT_TO_ROT.items()}[rot]
    out_root = os.path.abspath(out_root)
    ok_all = True
    for src in (os.path.abspath(a) for a in argv):
        asset = os.path.basename(src.rstrip("\\/"))
        blend = os.path.join(src, asset + ".blend")
        fbx = os.path.join(src, asset + ".fbx")
        if not (os.path.exists(blend) and os.path.exists(fbx)):
            print(f"[game_flip] SKIP {asset}: no {asset}.blend / .fbx (run the final gate first)")
            ok_all = False
            continue
        if os.path.getmtime(blend) + 5 < os.path.getmtime(fbx):
            print(f"[game_flip] SKIP {asset}: .blend older than .fbx (stale save)")
            ok_all = False
            continue
        man = os.path.join(src, "manifest.json")
        data = json.load(open(man, encoding="utf-8")) if os.path.exists(man) else {}
        size = data.get("size") or [0, 0, 0]
        new = new_asset_name(asset, rot, size, suffix)
        dst = os.path.join(out_root, new)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        os.makedirs(dst)
        for png in glob.glob(os.path.join(src, "*.png")):
            b = os.path.basename(png)
            shutil.copy2(png, os.path.join(dst, new + b[len(asset):] if b.startswith(asset) else b))
        if data:
            data["asset"] = new
            if new != asset:
                m = NAME_RE.match(new)
                data["lot"] = [int(m["w"]), int(m["d"])]
            if rot % 180:
                data["size"] = [size[1], size[0], size[2]]
                m = NAME_RE.match(new)
                data["lot"] = [int(m["w"]), int(m["d"])]
            data[FLIP_TAG] = dict(rotate_z_deg=rot, road_face=road_face, source=os.path.relpath(src, KIT),
                                  note=f"game copy: the generator's {road_face} face is the road side (-Y); "
                                       "pivot_shift and generator coordinates no longer apply")
            with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        r = subprocess.run([_blender_exe(), "--background", "--factory-startup", "--python",
                            os.path.abspath(__file__), "--", "--inner", src, dst, str(rot)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("[game_flip]") or ln.startswith("FLIP")]
        print("\n".join(lines) if lines else r.stdout[-1500:] + r.stderr[-1500:])
        ok_all &= any(ln.startswith("FLIP OK") for ln in lines)
    print(f"GAME_FLIP {'PASS' if ok_all else 'FAIL'} (rot {rot}, road side = generator {road_face})")
    sys.exit(0 if ok_all else 1)


def _inner(src, dst, rot):
    import bpy
    import numpy as np
    from mathutils import Matrix
    sys.path.insert(0, KIT)
    import cs2kit as K

    asset = os.path.basename(src.rstrip("\\/"))
    new = os.path.basename(dst.rstrip("\\/"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(src, asset + ".blend"))
    names = {asset + K.SUFFIX[k] for k in K.PARTS}
    fbx_names = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(src, "*.fbx")))
    for ob in list(bpy.data.objects):                     # the .blend holds the whole session: keep this asset only
        if ob.name not in names:
            bpy.data.objects.remove(ob, do_unlink=True)
    R = Matrix.Rotation(math.radians(rot), 4, "Z")        # counter-clockwise from above; rotation, winding unchanged
    done = []
    for n in fbx_names:
        ob = bpy.data.objects.get(n)
        if ob is None or ob.type != "MESH":
            print(f"[game_flip] FLIP FAIL {asset}: object {n} missing in .blend")
            return
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        ob.data.transform(ob.matrix_world)                # bake any object transform, then identity
        ob.matrix_world = Matrix.Identity(4)
        ob.data.transform(R)
        ob.data.update()
        if new != asset:                                  # lot changed: rename mesh, material, texture paths
            ob.name = new + n[len(asset):]
            ob.data.name = ob.name
            for slot in ob.material_slots:
                if slot.material and slot.material.name.startswith(asset):
                    slot.material.name = new + slot.material.name[len(asset):]
        done.append(ob)
    if new != asset:
        for img in bpy.data.images:
            b = os.path.basename(img.filepath)
            if b.startswith(asset):
                img.filepath = os.path.join(dst, new + b[len(asset):])
    for ob in done:                                       # same settings as cs2kit._bl_export
        for o in bpy.data.objects:
            if o.name in bpy.context.view_layer.objects:
                o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.export_scene.fbx(filepath=os.path.join(dst, ob.name + ".fbx"), use_selection=True,
                                 object_types={"MESH"}, apply_unit_scale=True, apply_scale_options=K.FBX_SCALE_OPTION,
                                 axis_forward="-Z", axis_up="Y", bake_space_transform=True, mesh_smooth_type="FACE",
                                 add_leaf_bones=False, bake_anim=False, path_mode="STRIP", embed_textures=False)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(dst, new + ".blend"), copy=True)

    def load(path):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if "fbx_import" in dir(bpy.ops.wm):
            bpy.ops.wm.fbx_import(filepath=path)
        else:
            bpy.ops.import_scene.fbx(filepath=path)
        vs, tris = [], 0
        stem = os.path.splitext(os.path.basename(path))[0]
        for o in (o for o in bpy.context.scene.objects if o.type == "MESH"):
            if o.name.split(".")[0] != stem:             # game looks textures up by this mesh name
                bad.append(f"{stem}: mesh name inside FBX is {o.name}")
            m = o.data
            a = np.empty(len(m.vertices) * 3)
            m.vertices.foreach_get("co", a)
            mw = np.array(o.matrix_world)
            vs.append(a.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
            tris += sum(len(p.vertices) - 2 for p in m.polygons)
        return (np.vstack(vs) if vs else np.zeros((0, 3))), tris

    Rn = np.array(R)[:3, :3]                              # imported frame is Blender's (z up)
    bad = []
    for n in fbx_names:
        nn = new + n[len(asset):]
        va, ta = load(os.path.join(src, n + ".fbx"))
        vb, tb = load(os.path.join(dst, nn + ".fbx"))
        if ta != tb or va.shape != vb.shape:
            bad.append(f"{nn}: tris {ta}/{tb} verts {len(va)}/{len(vb)}")
            continue
        exp = va @ Rn.T
        err = np.abs(exp - vb).max() if len(va) else 0.0
        sa, sb = np.ptp(va, axis=0), np.ptp(vb, axis=0)
        if rot % 180:
            sa = sa[[1, 0, 2]]
        if err > 0.002 or np.abs(sa - sb).max() > 0.002:
            bad.append(f"{nn}: vertex error {err:.4f} m, size {sa.round(2)} vs {sb.round(2)}")
        else:
            print(f"[game_flip] {nn}: tris {tb}, size {sb.round(2).tolist()}, max err {err:.4f} m")
    print((f"FLIP FAIL {asset}: " + "; ".join(bad)) if bad else f"FLIP OK {asset} -> {new} ({len(fbx_names)} FBX)")


if __name__ == "__main__":
    av = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if av and av[0] == "--inner":
        _inner(av[1], av[2], int(av[3]))
    else:
        _outer(av)
