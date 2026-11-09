# GLB-driven mass reconstruction

Use this whenever a project has a GLB/GLTF scan. Do not stop at overall width/depth/height and redraw a rectangular mass when the scan contains footprint or height evidence.

## 1. Select the building

```bash
python tools/agent.py glb-mass --project P --json -- photos/scan.glb --list
```

Select only the target building with `--mesh`, `--mesh-index`, and optionally `--box=x0,x1,y0,y1`. Check `--scale` and `--up y|z`; glTF normally uses Y-up. Wrong selection or scale invalidates every derived value.

## 2. Generate the generic mass spec

Create the project with `--template generic`, then run:

```bash
python tools/agent.py glb-mass --project P --json -- photos/scan.glb --mesh-index 3 --out generic_spec.json --force
```

The tool:

- normalizes ground, scale, and building orientation;
- cuts the selected mesh at multiple heights;
- extracts and simplifies outer footprint polygons;
- detects footprint changes and creates stacked or separate mass volumes;
- centers X and puts the lowest front extent at Y=0;
- records `source_hash` + `simplify_params` (tolerance, min area, max points, sample points, simplifier version), mesh selection, transform, and simplification settings;
- writes `previews/glb/shape.png` and `shape_report.json` for review (both repeat the source hash and simplify params).

Only simplified measurements are transferred. Source triangles, textures, window meshes, and facade materials are never copied into the asset.

`--force` replaces the whole output file, including openings and attachments. After facade editing has begun, write to another file and merge only reviewed volume changes instead of overwriting the working spec.

## 3. Control difficult scans

Use confirmed internal height boundaries when automatic slicing is noisy:

```bash
python tools/agent.py glb-mass --project P --json -- photos/scan.glb --mesh Building --levels 6,12 --out generic_spec.json --force
```

- `--front-deg`: correct the street-facing orientation.
- `--simplify 0.35`: footprint tolerance in metres; increase only to remove scan noise.
- `--max-points 16`: limits each generated footprint to 3..64 points.
- `--min-area 4`: removes small rings; lower it only for real small wings or equipment.
- `--levels`: explicit internal Z boundaries above normalized ground, not sample heights.

Inspect the preview and warnings. Inner rings/courtyards, terrain, vegetation, neighboring buildings, and rooftop equipment can require manual correction. A generated spec is mass evidence, not a completed visual review. Confirm hidden walls and roof transitions against photos.

## 4. Build and continue

The generated wall IDs such as `mass_00_00:edge_00` can be used directly by generic `window_band`, `shopfront`, louver, railing, and photo-reference features. Derive openings from photos or other facade evidence; do not invent them from the mass converter.

Run the `next_action` quick command. A completely bare, low-poly generic mass can fail the existing `LOD1_TOO_BIG` ratio because there are no full-detail facade parts to omit from LOD1. This is not permission to report PASS or distort the measured mass; add evidence-based parts and rerun the gate.
