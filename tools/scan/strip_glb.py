# remove KHR_texture_basisu textures from a GLB so Blender can import the geometry (reference only)
import json, struct, sys

src, dst = sys.argv[1], sys.argv[2]
b = open(src, "rb").read()
magic, ver, total = struct.unpack("<III", b[:12])
jlen, jtype = struct.unpack("<II", b[12:20])
js = json.loads(b[20:20 + jlen])
rest = b[20 + jlen:]
for k in ("extensionsUsed", "extensionsRequired"):
    if k in js:
        js[k] = [e for e in js[k] if e != "KHR_texture_basisu"]
        if not js[k]:
            del js[k]
for m in js.get("materials", []):
    pbr = m.get("pbrMetallicRoughness", {})
    pbr.pop("baseColorTexture", None)
    pbr.pop("metallicRoughnessTexture", None)
    for t in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        m.pop(t, None)
    m.get("extensions", {}).clear()
js.pop("textures", None); js.pop("images", None); js.pop("samplers", None)
out = json.dumps(js).encode()
out += b" " * ((4 - len(out) % 4) % 4)
total = 12 + 8 + len(out) + len(rest)
open(dst, "wb").write(struct.pack("<III", magic, ver, total) + struct.pack("<II", len(out), 0x4E4F534A) + out + rest)
print("ok", len(js.get("meshes", [])))
