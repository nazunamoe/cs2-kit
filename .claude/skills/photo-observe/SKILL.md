---
name: photo-observe
description: Read one wall photo with a fixed checklist (floors, windows per bay, paint bands, balcony/louver type), cross-check against measured data, and record it with agent.py observe
---

Use for one wall or one detail crop at a time. Never judge a whole building from one uncropped photo.

1. Pick the photo and the wall. If it is a Naver VR capture, use the wall's `make_refs` entry (`size_m`, `z_m`); otherwise use `photo_refs.json`.
   Run `agent.py photos --page 0 --json` for the contact sheet only to choose the photo.
2. Zoom first. Split the wall into at least 3 columns x 3 rows and Read every cell
   (`tools/sat_grid.py grid <photo> --crop x0,y0,x1,y1 --zoom 3 --step 10 -o previews/obs_<wall>_<cell>.png`).
   Do not answer from the full photo.
3. Fill this checklist, one line each. Write `unknown` instead of guessing. Mark each answer `counted` (you counted it in the crops) or `estimated`:
   - floors visible in this crop / in this wall
   - windows per floor per bay (list the bays left to right)
   - window kind: sliding / fixed / curtain wall; window width x height (m) if a scale is known
   - balcony: expanded / open / none; railing: glass / metal / none
   - louver: none / vertical / horizontal; where (floor range, bay range)
   - paint bands: colour (hex from the crop), floor range, bay range
   - special floors (refuge floor, machine floor) and which floor numbers
   - things that block the view (trees, shadows, signs, other buildings)
4. Cross-check before recording:
   - floors vs `data.xrx` floor count (Naver VR) or the `facade_paint.py floors` numbered picture
   - bay pitch vs the `facade_paint.py windows` MODULE line
   - `TASK.md` louver / railing / balcony / window_type values win over the photo; note the difference
   If a number disagrees, recount the crops once. If it still disagrees, record both values and the reason; do not pick silently.
5. Record: `agent.py observe --photo <photo> --side <side> --note "<checklist as short key=value pairs>"`.
6. Report in Korean: the checklist, the cross-check result, and what is `unknown`.

Do not use observations to edit a `photo_refs.json` that the user wrote. Do not put building-specific values in `memory/LESSONS.md`.
