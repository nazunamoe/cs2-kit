import sys
from PIL import Image
# crop.py img a0 H a_from a_to z_from z_to zoom out
f,a0,H,af,at,zf,zt,zoom,out=sys.argv[1],float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6]),float(sys.argv[7]),float(sys.argv[8]),sys.argv[9]
im=Image.open(f)
b=(int((af-a0)*20),int((H-zt)*20),int((at-a0)*20),int((H-zf)*20))
c=im.crop(b); c=c.resize((int(c.size[0]*zoom),int(c.size[1]*zoom)),Image.LANCZOS); c.save(out); print(c.size)
