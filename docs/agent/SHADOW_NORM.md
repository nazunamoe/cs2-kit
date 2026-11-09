# Shadow normalization for facade colour measurement

A shadowed wall is usually the **same material** as the lit part, only darker. Sampling it directly makes the paint palette too dark. `tools/shadow_norm.py` uses the bright white wall in the photo as the reference and lifts shadowed blocks toward it.

```bash
python tools/shadow_norm.py --image photos/wall.png --out photos/wall_lit.png --block 64
python tools/shadow_norm.py --dir photos/planes --out photos/planes_lit --block 64 --json
```

## Normalizing a whole photo_refs file

`--refs` normalizes every image a `photo_refs.json` points at and writes a **new refs json**
with the updated file paths. Paint tools then run on the normalized refs, so the colour
sampling and the wall texture both use the corrected images.

```bash
python tools/shadow_norm.py --project my-building \
  --refs photo_refs.json --out-refs photo_refs_lit.json
```

- the same image referenced by several entries is normalized once
- the new refs file keeps every other field (`corners`, `size_m`, `paint_exclude`, ...) and
  records the settings under `_shadow_norm`
- `photo_refs_lit.json` is the file to hand to `band_scan.py` / `facade_read.py` when the
  measurement is about colour; keep the original refs for geometry
- the normalized images are written next to the originals (`<name>_lit.png`), the source
  photos are never modified

## Method

1. The 98th luminance percentile is the white-wall reference. With `--patch-median` the
   reference is the **median of five patches** (four corners and the centre), which is less
   pulled down by a large shadowed area or a bright sky than a single whole-image value.
2. The image is split into 64 px blocks; each block's 92nd percentile is its bright wall value.
3. `gain = white / block_bright`, clamped to `1.0 .. --max-gain` (default 1.8).
4. The block gain map is resized smoothly to full resolution and multiplied into RGB.
5. Images with no bright reference (white < 45) are skipped.

```bash
python tools/shadow_norm.py --image photos/wall.png --out photos/wall_lit.png --patch-median
python tools/shadow_norm.py --refs photo_refs.json --out-refs photo_refs_lit.json \
  --patch-median --patch-frac 0.18 --json
```

`--patch-frac` is the patch size as a fraction of the shorter side (default 0.18). The
stats (`white_patches`, `white_mode`) show whether the patch median or the global value
was used. Patch median helps when one large dark region dominates the frame; if every
patch lands on a window or the sky, check the values before trusting them.

Only luminance is normalized. Colour temperature (warm/cool cast) is preserved.

## Example: 101 tower planes

| Plane | Before | After |
|---|---|---|
| p16 white wall | `#98a1a3 #c3cbcd #d9ddde` | `#acbec9 #d5dcdb #f9fcfd` |
| p20 shadowed wall | `#2b2d38 #565c74 #717998` | `#404258 #838dac #a5b6e8` |

The p20 wall read almost black before and mid blue-grey after, matching the lit side of the same wall.

## Limits

- Deep shadow beyond `--max-gain` is only partly recovered.
- This is an albedo estimate, not a measured material sample.
- Do not use the normalized image as a display photo; use it for colour sampling and wall textures.
- Exclude windows, signs, trees and the ground from paint sampling separately (`band_scan` masks or `paint_exclude`).
