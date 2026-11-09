# Shadow normalization for facade colour measurement

A shadowed wall is usually the **same material** as the lit part, only darker. Sampling it directly makes the paint palette too dark. `tools/shadow_norm.py` uses the bright white wall in the photo as the reference and lifts shadowed blocks toward it.

```bash
python tools/shadow_norm.py --image photos/wall.png --out photos/wall_lit.png --block 64
python tools/shadow_norm.py --dir photos/planes --out photos/planes_lit --block 64 --json
```

## Method

1. The 98th luminance percentile is the white-wall reference.
2. The image is split into 64 px blocks; each block's 92nd percentile is its bright wall value.
3. `gain = white / block_bright`, clamped to `1.0 .. --max-gain` (default 1.8).
4. The block gain map is resized smoothly to full resolution and multiplied into RGB.
5. Images with no bright reference (white < 45) are skipped.

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
