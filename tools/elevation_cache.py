import glob
import hashlib
import os
import threading

import numpy as np
from PIL import Image

from proj import ROOT
from render import SKY, render

MEMO_MAX = 24            # decoded views kept in this process (2200^2 RGB = 14.5 MB each at most)
_MEMO = {}
_LOCKS = {}
_GUARD = threading.Lock()


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
    # Single flight per view: walls checked in parallel share a handful of views, so the first caller
    # renders/decodes and the rest reuse the same (read-only) image.
    with _GUARD:
        lock = _LOCKS.setdefault(path, threading.Lock())
    with lock:
        im = _MEMO.get(path)
        if im is None:
            im = _load_or_render(path, folder, meshes, tex, yaw, pitch, size, box)
            with _GUARD:
                while len(_MEMO) >= MEMO_MAX:
                    _MEMO.pop(next(iter(_MEMO)))
                _MEMO[path] = im
    return im


def _load_or_render(path, folder, meshes, tex, yaw, pitch, size, box):
    if os.path.isfile(path):
        os.utime(path, None)
        im = Image.open(path).convert("RGB")
        im.load()
        return im
    im = render([(meshes.get("main"), "s"), (meshes.get("win"), "window"), (meshes.get("gls"), "glass")],
                tex, yaw, pitch, (size, size), label=False, box=box)
    a = np.asarray(im, np.float32) / 255.0
    sky = np.abs(a - SKY[None, None, :]).max(-1) > 0.02
    ys, xs = np.nonzero(sky)
    if not len(xs):
        raise ValueError("model render is empty")
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    tmp = path + f".{os.getpid()}.{threading.get_ident()}.tmp.png"
    im.save(tmp, compress_level=1)
    os.replace(tmp, path)
    cached = sorted(glob.glob(os.path.join(folder, "*.png")), key=os.path.getmtime, reverse=True)
    for old in cached[64:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return im
