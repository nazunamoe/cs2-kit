# sill shelves (bright bars) in a dark curtain-wall zone: per window (a0,a1) and shelf height above the floor level (median over floors)
# args: img a0img sign ztop dz gf fh k0 k1 afrom ato [thr]
import sys, numpy as np
from PIL import Image
f,a0,sg,ztop,dz,gf,fh,k0,k1,af,at=sys.argv[1],float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6]),float(sys.argv[7]),int(sys.argv[8]),int(sys.argv[9]),float(sys.argv[10]),float(sys.argv[11])
thr=float(sys.argv[12]) if len(sys.argv)>12 else 115
im=np.asarray(Image.open(f).convert("L")).astype(float)
lv=lambda k: gf+(k-2)*fh
Y=lambda zg: int(round((ztop-(zg+dz))*20))
# image columns of the range (in image coords; sign -1: image a runs opposite to gen)
ia,ib=sorted(((af-0)*0+ (sg*af-a0)*20, (sg*at-a0)*20)); ia,ib=int(ia),int(ib)
res={}
for k in range(k0,k1+1):
    y0,y1=Y(lv(k)+2.0),Y(lv(k)-0.1)          # floor band: from +2.0 down to just under the floor
    band=im[y0:y1,ia:ib]
    mask=band>thr
    # per-row bright runs
    for r in range(band.shape[0]):
        pass
    rowcnt=mask.sum(1)
    # shelf rows = rows where the bright run is long (>= 8 px = 0.4 m)
    for r in range(band.shape[0]):
        row=mask[r]; s=None
        for x,v in enumerate(list(row)+[False]):
            if v and s is None: s=x
            if not v and s is not None:
                if x-s>=8: res.setdefault(k,[]).append((s+ia,x+ia,(y0+r)))
                s=None
# merge rows into shelves per floor
out=[]
for k,runs in res.items():
    runs.sort(); groups=[]
    for s,e,y in runs:
        for g in groups:
            if abs(g[0]-s)<=6 and abs(g[1]-e)<=6 and y-g[3]<=4: g[3]=y; g[4].append(y); break
        else: groups.append([s,e,y,y,[y]])
    for g in groups:
        if len(g[4])>=2:                      # >= 0.1 m thick
            ym=np.median(g[4]); out.append((k,g[0],g[1],lv(k)-(ztop-ym/20-dz)*-1+0) )
# convert: shelf height above floor
tab={}
for k,runs in res.items(): pass
rows=[]
for k in range(k0,k1+1):
    runs=res.get(k,[]); runs.sort(); groups=[]
    for s,e,y in runs:
        for g in groups:
            if abs(g[0]-s)<=6 and abs(g[1]-e)<=6 and y-g[3]<=4: g[3]=y; g[4].append(y); break
        else: groups.append([s,e,y,y,[y]])
    for g in groups:
        if len(g[4])>=2:
            ytop=min(g[4]); zs=ztop-ytop/20-dz        # shelf top (gen z)
            rows.append((g[0],g[1],zs-lv(k)))
# cluster by start pixel
rows.sort(); cl=[]
for s,e,h in rows:
    for c in cl:
        if abs(c[0][0]-s)<=8: c.append((s,e,h)); break
    else: cl.append([(s,e,h)])
print("clusters (a0,a1,shelf top above floor, count)")
for c in cl:
    if len(c)<max(3,(k1-k0+1)//3): continue
    s=np.median([t[0] for t in c]); e=np.median([t[1] for t in c]); h=np.median([t[2] for t in c])
    g0,g1=sorted((sg*(a0+s/20),sg*(a0+e/20)))
    print("  a %.2f..%.2f  shelf_top %.2f  n=%d"%(g0,g1,h,len(c)))
