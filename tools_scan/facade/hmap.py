# 스캔 위에서 본 높이장(셀마다 가장 높은 z) 과 그 면의 기울기 저장
import numpy as np, sys
d = np.load(sys.argv[1]); V, T = d["V"], d["T"]
res = 0.25
x0, x1, y0, y1 = -22, 22, -1, 37
nx, ny = int((x1-x0)/res), int((y1-y0)/res)
H = np.full((ny, nx), -1.0); N = np.zeros((ny, nx, 3))
for t in T:
    P = V[t]
    if P[:,2].max() < 95: continue
    n = np.cross(P[1]-P[0], P[2]-P[0]); L = np.linalg.norm(n)
    if L < 1e-9: continue
    n /= L
    if abs(n[2]) < 0.05: continue
    ix0 = max(0, int((P[:,0].min()-x0)/res)); ix1 = min(nx-1, int((P[:,0].max()-x0)/res)+1)
    iy0 = max(0, int((P[:,1].min()-y0)/res)); iy1 = min(ny-1, int((P[:,1].max()-y0)/res)+1)
    gx, gy = np.meshgrid(x0+(np.arange(ix0, ix1+1)+0.5)*res, y0+(np.arange(iy0, iy1+1)+0.5)*res)
    a, b, c = P[:,:2]
    den = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
    if abs(den) < 1e-12: continue
    l1 = ((b[1]-c[1])*(gx-c[0]) + (c[0]-b[0])*(gy-c[1]))/den
    l2 = ((c[1]-a[1])*(gx-c[0]) + (a[0]-c[0])*(gy-c[1]))/den
    l3 = 1-l1-l2
    m = (l1>=-1e-6)&(l2>=-1e-6)&(l3>=-1e-6)
    z = l1*P[0,2]+l2*P[1,2]+l3*P[2,2]
    sub = H[iy0:iy1+1, ix0:ix1+1]; subn = N[iy0:iy1+1, ix0:ix1+1]
    upd = m & (z > sub)
    sub[upd] = z[upd]; subn[upd] = n
np.savez(sys.argv[2], H=H, N=N, ext=[x0, x1, y0, y1, res])
# 1 m 셀 표 (z-100, 0.1 m 단위 생략 → 정수 dm 대신 소수 1자리)
print("y-x " + " ".join("%5d" % x for x in range(x0, x1, 2)))
for yy in np.arange(y1-1, y0, -1.0):
    iy = int((yy+0.5-y0)/res)
    row = []
    for xx in range(x0, x1, 2):
        ix = int((xx+1-x0)/res); h = H[iy, ix]
        row.append("  .  " if h < 95 else "%5.1f" % h)
    print("%4.0f " % yy + " ".join(row))
