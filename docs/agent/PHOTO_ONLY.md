# Photo-only evidence workflow

Use this when no GLB exists. A single frontal photo cannot establish depth or hidden geometry. Record estimates instead of presenting them as measurements.

## Photo selection

Prefer a full frontal image per wall, oblique images at corners, detail photos for entrances/roof edges, and an optional roof/satellite image. A short walk-around video can provide better continuity than isolated photos, but video/photogrammetry is not required by this kit.

For each photo, record what it can actually support: floors, bays, color, depth, or roof. Mark occlusion and confidence. Use one representative image for a measurement and another angle as a holdout review when available.

## Evidence ledger

Record the photo and wall first:

```bash
python tools/agent.py evidence --project P --json -- photo \
  --photo photos/front.jpg --photo-id front_main --wall main:front \
  --view frontal --use floors,bays,color --confidence high \
  --occluded "left 2 bays behind trees" --note "full wall"
```

Add normalized observations:

```bash
python tools/agent.py evidence --project P --json -- feature \
  --wall main:front --kind window --u 0.12,0.19 --v 0.20,0.78 \
  --floor 7 --photo-id front_main --confidence high --note "measured edges"
```

Validate with:

```bash
python tools/agent.py evidence --project P --json -- validate
```

Data is stored in `work/photo_evidence.json`. Every feature has a wall, source photo, U/V range, confidence, and optional floor/estimated marker. Low-confidence values must be marked estimated.

## Wall-linked photo refs

`photo_refs.json` facade entries support:

- `wall_id`: link to `manifest.metadata.walls` from the generic volume builder.
- `size_m`: measured width/height of the wall inside the four corners.
- `box`: generator-coordinate render box `[x0,x1,y0,y1,z0,z1]`.
- `yaw_deg`: optional explicit camera yaw; normally derived from wall `normal_deg`.
- `confidence`: low-confidence evidence is not allowed to trigger automatic floor changes.
- `occluded`: document hidden regions.

A missing linked wall is an error unless explicit `size_m` and `box` fully describe the reference. Pivot shift is applied by the checker. Wall-specific render boxes prevent a recessed or angled wall from being compared against the whole building extent.

## Measurement order

1. Establish wall identity and usable photo coverage.
2. Measure mass and floor structure before detail.
3. Use robust floor lines from clean vertical sections; ground/feature/crown floors may differ.
4. Record actual window edges, not an assumed equal grid.
5. Obtain depth only from oblique/roof evidence or mark it estimated.
6. Compare colors only after geometry, using same-material controls and trusted tiles.
7. Review a different angle when possible.

Weak photo/model patterns and low-confidence references produce informational findings, not automatic floor-count instructions. After three identical mismatch attempts, stop for human review.
