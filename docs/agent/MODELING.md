# Detailed modeling and photo review

Load this reference only for a task that needs detailed facade modeling or photo analysis. Project-specific values in old memory are examples, not defaults.

## Evidence and observations

- Priority: current GLB measurements > current photo measurements > researched facts > era defaults > estimates.
- TASK values for `louver`, `railing`, `balcony`, `curtainwall`, and `window_type` override ambiguous photo interpretation.
- Record each facade's observed openings, floor ranges, dimensions, colors, source photo, and confidence. Mark unknown dimensions `estimated`.
- Count floors from a feature floor when possible and verify the numbered image. Do not assume symmetry or equal bay widths.
- Use scan geometry only for dimensions/shape. Never copy scan geometry or textures into the asset.
- Do not research when `complex_name` is empty. Record source URLs and conflicts; never invent missing research values.

## Facade construction

Build mass and stepped cores first. Model every depth offset >= 5 cm: recesses, balcony slabs, eaves, parapets, mullions, reveals, and canopies. Do not flatten different depths into one painted plane.

Windows are lists per wall with position, width, and type; a feature floor may differ. Use a dark reveal, thin frame, and measured mullion/transom ratios rather than equal splits. Keep window mullions in front of glass and split transoms between vertical members to avoid coplanar faces.

- Window: `_Win` + `_Gls`; frames/reveals in main mesh.
- Louver: real main-mesh blades and dark backing, not `_Win`; no normal night-window emission.
- Glass railing: glass in `_Gls`, rails/fixings in main mesh.
- Metal railing: opaque main-mesh bars, no glass.
- Panel/spandrel: opaque main mesh or paint.
- Expanded balcony: windows and slab, no open balcony railing.
- Open balcony: slab, appropriate railing, rear windows/doors.
- Canopy: thin slab plus supports, not a solid mass.

For curtain walls use `K.curtainwall`. TASK values determine module width and spandrel height; otherwise measure them and record the evidence. Use 1.5 m / 0.9 m only as marked estimates. Do not use reflected sky photo textures as window material. Close side-wall ends with `corner_post` where required.

## Paint and materials

Read paint as a few large rectangles plus floor rules, not independent noisy pixels. Identify the same wall by opening sequence, not brightness alone. Compare views from the same camera before judging color.

Use photo-derived colors and repeating material units. Avoid windows, signs, people, vehicles, and logos in extracted textures. Use `--paint` for painted walls and measured joint periods for stone/panel textures. Do not upscale beyond source information without marking the texture `synthesized`.

Do not rely on raw color distance under different illumination. Use same-L comparison for different photos, raw ratios within the same photo, and a same-material control surface. Also compare whole-wall area ratios so brightness normalization cannot hide a wrong paint region.

For `band_scan.py`, exclude windows and `paint_exclude` regions before clustering. Keep observed Lab lightness within one photo; do not flatten different paints to one L. Inspect `_mask.png` and leave `cell_id=-1` unknown. For Naver VR, use exact planar refs from `docs/agent/NAVER_VR.md` rather than warping merged non-coplanar wall groups.

## Review

At mass, windows, and final checkpoints, compare both numbers and images. Inspect only flagged tiles and ambiguous details. Low recall can come from trees, shadows, blur, or perspective; record such evidence instead of endlessly changing geometry.

A coplanar error means moving/attaching geometry or changing paint layers, not changing the measured design. A LOD triangle excess never justifies changing actual floor count, bay count, or window locations.

## Detail targets

Main target 30k-60k tris, warning above 95k; LOD1 < 50%, LOD2 <= 500. Use mesh for window frames, railings, louvers, canopies, columns, doors, coping, and roof equipment where visible. Atlas 4096; eye-level materials 256 px/m, main walls 128, roof/high surfaces 64. Use lower detail in LODs without changing the building's measured structure.
