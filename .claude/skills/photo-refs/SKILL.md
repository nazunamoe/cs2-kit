---
name: photo-refs
description: Create or validate photo_refs.json using selective visual inspection
---

1. Resolve the active project and run `agent.py photos --page 0 --page-size 16 --json`.
2. Read the contact sheet, then representative road/satellite images. Use `tools/sat_grid.py grid` with crop/zoom only for ambiguous corners.
3. If the user already authored `photo_refs.json`, leave it unchanged and only validate it. Otherwise create it following `templates/photo_refs.example.json`.
4. Record observations with `agent.py observe`.
5. Run the existing generator through `agent.py cycle --mode visual --json`. Inspect the photo sheets, fix reference corners first if warping is wrong, then record the review result.
