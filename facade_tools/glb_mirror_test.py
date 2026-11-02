import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, gen, GLB, MESHES  # noqa: E402,F401
import json, struct, numpy as np
from PIL import Image, ImageDraw
f = open(GLB, "rb").read()
L = struct.unpack("<I", f[12:16])[0]; J = json.loads(f[20:20+L]); B = f[20+L+8:]
CT = {5126: (np.float32, 4), 5125: (np.uint32, 4), 5123: (np.uint16, 2), 5121: (np.uint8, 1)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
def acc(i):
    a = J["accessors"][i]; bv = J["bufferViews"][a["bufferView"]]
    dt, sz = CT[a["componentType"]]; nc = NC[a["type"]]
    o = bv.get("byteOffset", 0) + a.get("byteOffset", 0); st = bv.get("byteStride", sz*nc)
    out = np.empty((a["count"], nc), dt)
    for k in range(a["count"]): out[k] = np.frombuffer(B, dt, nc, o + k*st)
    return out
def mat(nd):
    if "matrix" in nd: return np.array(nd["matrix"]).reshape(4,4).T
    M = np.eye(4); t = nd.get("translation", [0,0,0]); x,y,z,w = nd.get("rotation", [0,0,0,1]); s = nd.get("scale", [1,1,1])
    R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],[2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],[2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    M[:3,:3] = R*np.array(s); M[:3,3] = t; return M
tris = {}
def walk(ni, P):
    nd = J["nodes"][ni]; M = P @ mat(nd)
    if "mesh" in nd:
        m = J["meshes"][nd["mesh"]]; name = m.get("name", "") + nd.get("name", "")
        for key in MESHES:
            if key in name:
                for pr in m["primitives"]:
                    v = acc(pr["attributes"]["POSITION"]).astype(float)
                    v = (M @ np.c_[v, np.ones(len(v))].T).T[:, :3]
                    idx = acc(pr["indices"]).reshape(-1, 3) if "indices" in pr else np.arange(len(v)).reshape(-1, 3)
                    tris.setdefault(key, []).append(v[idx])
    for c in nd.get("children", []): walk(c, M)
for r in J["scenes"][J.get("scene", 0)]["nodes"]: walk(r, np.eye(4))

def slice_pts(k, dz=100):
    T = np.vstack(tris[k]); h0 = T[..., 1].min(); zc = h0 + dz
    out = []
    for t in T:
        hs = t[:, 1]; pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if (hs[a] - zc) * (hs[b] - zc) < 0:
                u = (zc - hs[a]) / (hs[b] - hs[a]); p = t[a] + u * (t[b] - t[a]); pts.append((p[0], -p[2]))
        if len(pts) == 2:
            a, b = np.array(pts)
            for s in np.linspace(0, 1, max(2, int(np.linalg.norm(b - a) / 0.3))):
                out.append(a + s * (b - a))
    P = np.array(out); return P - P.mean(0)

class cKDTree:
    def __init__(self, P):
        self.P = P
    def query(self, Q):
        d = np.full(len(Q), 1e9)
        for i in range(0, len(self.P), 400):
            D = np.linalg.norm(Q[:, None, :] - self.P[None, i:i + 400, :], axis=2).min(1)
            d = np.minimum(d, D)
        return d, None
A = slice_pts(MESHES[0])[::3]; tA = cKDTree(A)
for k in MESHES[1:]:
    B = slice_pts(k)[::3]
    for mir in (False, True):
        Bm = B * np.array([1, -1]) if mir else B
        best = (1e9, 0)
        for th in np.arange(0, 360, 2.0):
            c, s = np.cos(np.radians(th)), np.sin(np.radians(th))
            R = Bm @ np.array([[c, s], [-s, c]])
            d = tA.query(R)[0].mean() + cKDTree(R).query(A)[0].mean()
            best = min(best, (d, th))
        print(k, "mirror" if mir else "same  ", "best chamfer %.2f m at %.1f deg" % best)
