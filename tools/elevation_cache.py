import glob
import hashlib
import os

import numpy as np
from PIL import Image

from proj import ROOT
from render import SKY, render


def _mesh_hash(mesh):
    cached = getattr(mesh, "_elevation_hash", None)
    if cached:
        return cached
    h = hashlib.sha256()
    h.update(mesh.verts.tobytes())
    for face, uv in zip(mesh.faces, mesh.uvs):
        h.update(np.asarray(face, dtype=np.int32).tobytes())
        h.update(np.asarray(uv, dtype=np.float64).tobytes())
    mesh._elevation_hash = h.hexdigest()
    return mesh._elevation_hash


def _texture_hash(tex):
    cached = getattr(tex, "_elevation_hash", None)
    if cached:
        return cached
    h = hashlib.sha256()
    for image in (tex.img, tex.alpha, tex.nrm, tex.emis):
        if image is not None:
            h.update(image.tobytes())
    tex._elevation_hash = h.hexdigest()
    return tex._elevation_hash


def model_crop(meshes, tex, yaw, pitch, size=2200, box=None):
    h = hashlib.sha256()
    for name in ("main", "win", "gls"):
        mesh = meshes.get(name)
        if mesh is not None:
            h.update(_mesh_hash(mesh).encode("ascii"))
    h.update(_texture_hash(tex).encode("ascii"))
    h.update(f"{yaw}:{pitch}:{size}".encode("ascii"))
    if box:
        h.update(",".join(f"{v:.5f}" for v in box).encode("ascii"))
    folder = os.path.join(ROOT, "previews", "elevation_cache")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, h.hexdigest() + ".png")
    if os.path.isfile(path):
        os.utime(path, None)
        return Image.open(path).convert("RGB")
    im = render([(meshes.get("main"), "s"), (meshes.get("win"), "window"), (meshes.get("gls"), "glass")],
                tex, yaw, pitch, (size, size), label=False, box=box)
    a = np.asarray(im, np.float32) / 255.0
    sky = np.abs(a - SKY[None, None, :]).max(-1) > 0.02
    ys, xs = np.nonzero(sky)
    if not len(xs):
        raise ValueError("model render is empty")
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    tmp = path + f".{os.getpid()}.tmp.png"
    im.save(tmp)
    os.replace(tmp, path)
    cached = sorted(glob.glob(os.path.join(folder, "*.png")), key=os.path.getmtime, reverse=True)
    for old in cached[64:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return im
