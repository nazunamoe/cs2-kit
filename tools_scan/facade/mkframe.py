# frame json (floor bottoms) for winlist / wmask / colstrips:  python mkframe.py <first_floor_z> <pitch> <n_floors> <out.json>
import json, sys
z0, pitch, n, out = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
json.dump(dict(levels=[round(z0 + pitch * k, 3) for k in range(n)]), open(out, "w"))
print("wrote", out, "levels", n)
