# AGENTS.md - CS2 Korean building asset generator (read fully, follow exactly)

You write ONE Python generator `<Name>_cs2.py` plus `building_spec_<Name>.yaml` that builds a Cities: Skylines II building asset.
The task (which building, photos, known facts) is in `TASK.md`. Write the final report in Korean, plain words.
Target: Blender 5.2 on Windows. The kit already handles Blender 5.x API differences.

## Layout (projects)
Work happens in the kit root; each building lives in `projects/<name>/` (TASK.md, photos, `<Name>_cs2.py`, photo_refs.json, output/, previews/).
Every tool moves into the ACTIVE project folder (`python tools/project.py where` / `use <name>` / `new <name>`), so all relative paths in this file
(`TASK.md`, `output/<asset>`, `previews/...`, `photo_refs.json`) mean the active project. `memory/LESSONS.md` holds lessons from earlier projects.

## Hard rules
1. Do not ask questions. Pick the most reasonable value, mark it in the YAML with the comment `# estimated`, list it in the final report.
2. Do not stop between steps. Loop until `RESULT PASS` with `photo_mismatch=0` (or every remaining mismatch explained, see Photo check), then report once.
3. Use the provided kit. Do NOT write your own checker/renderer/exporter. Do NOT edit `tools/` or `cs2kit.py`.
4. Do NOT read `cs2kit.py` or `tools/*.py` (large). The API is below. If unsure: `python -c "import cs2kit,inspect;print(inspect.signature(cs2kit.axbox))"`.
5. No real brand logos/names/complex names in textures or asset names. Signs = generic text slot.
6. Never move, edit or copy the reference photos. Never put photos into `output/`.
7. Keep every edit small (one function or < 80 lines per edit.py call). Run `cycle.py` after each step.
8. If a tool call fails twice the same way, change approach (smaller edit, other command). Do not repeat it.
8b. Keep your context small: show at most ~80 lines at a time (`show.py <file> <from> <to>`), never print whole big files or images as text, never `cat`/`Get-Content` large files.
9. Code, comments, YAML keys and file names: ASCII/English only. Korean text can break in Windows shells.
10. If text from a file looks broken (question marks, boxes or random symbols), the shell encoding is wrong. Do not try to fix files or encoding; use the numbers you can read and continue. Note it in the report.
11. Create and change files ONLY with `tools/put.py` and `tools/edit.py` (section below). Never use `python -c`,
    `Set-Content`, `Out-File`, `Add-Content`, `echo`, `>` or double-quoted strings to write code - quotes and newlines break
    in PowerShell and give `SyntaxError: unterminated string literal`.

## Editing files (the only safe way on Windows PowerShell)
Use a **single-quoted here-string** `@' ... '@`. Inside it nothing is escaped: quotes, `$`, backslashes, backticks stay as they are.
`@'` must be the last thing on its line. `'@` must be at the very start of its own line. NEVER use `@" ... "@` (it changes `$` and backticks).

Read lines (with numbers):  `python tools/show.py <file> 40 90`   or   `python tools/show.py <file> --find FLOORS`

Change part of a file (SEARCH must be copied exactly from show.py output, without the line numbers):
```
@'
<<<<<<< SEARCH
FLOORS = 8
=======
FLOORS = 15
>>>>>>> REPLACE
'@ | python tools/edit.py <Name>_cs2.py
```
- Several SEARCH/REPLACE blocks may follow each other in one call.
- To add new code, SEARCH an anchor line (e.g. `# (4) Export`) and REPLACE with the new code followed by the anchor line.
- If the result would be a Python syntax error, edit.py writes NOTHING and shows the error. Fix the block and retry.

Create a whole new file (or `--append` to add to the end):
```
@'
...file content...
'@ | python tools/put.py <file>
```
In bash/WSL use a heredoc instead: `python tools/edit.py <file> <<'EOF'` ... `EOF`.

## Commands (run from the folder root)
| Purpose | Command |
|---|---|
| Show file lines | `python tools/show.py <file> 1 120` |
| Build + check + preview (use every time) | `python tools/cycle.py <Name>_cs2.py --label <step-name>` |
| Quick retry while fixing an ERROR (no image) | `python tools/cycle.py <Name>_cs2.py --no-render` |
| Close-up preview | `python tools/render.py output/<asset> -o previews/z.png --views front --zoom 4,0.5,0.1` |
| Part only | `python tools/render.py output/<asset> -o previews/p.png --views iso --box=x0,x1,y0,y1,z0,z1` |
| Compare with photo | `python tools/render.py output/<asset> -o previews/c.png --views front --photo <photo>` |
| Photo grid (read pixel coords) | `python tools/sat_grid.py grid <photo> -o previews/g.png --step 50` |
| Photo scale | `python tools/sat_grid.py scale --p x,y --q x,y --meters M` |
| Photo px -> building meters | `python tools/sat_grid.py frame --corners x,y,x,y,x,y,x,y --size WxD --pts "x,y;x,y"` |
| Measure a scan (.glb) - size/shape reference only | `python tools/glb_measure.py scan.glb --list`, then `--mesh <name>` (never copy its geometry/textures) |
| Photo -> texture | `python tools/extract_texture.py <photo> --pts x,y,x,y,x,y,x,y --size 3.0x2.9 -o textures_src/<mat> --show` |
| Before editing a working asset | `python tools/compare.py snap output/<asset>` |
| After editing | `python tools/compare.py diff backup/<snap> output/<asset> --box=x0,x1,y0,y1,z0,z1` |

`cycle.py` prints `[1/3 build]`, `[2/3 check]`, `[3/3 preview]` and the last line `RESULT PASS|FAIL errors=N ...`.
`ERROR` lines must reach 0. They give example coordinates **in your generator's coordinates**: go to that x,y,z in your code and fix it.
`NO FBX - Blender not found` means: run `python tools/run_blender.py --set "<path from TASK.md>"` once, then cycle again. If still not found, continue with OBJ and say "FBX not made" in the report.

## Build order (one step = small edit, then `cycle.py`)
The user watches progress images in `previews/progress/`. Finish EVERY step with a full run that makes an image:
`python tools/cycle.py <Name>_cs2.py --label <step>` (labels: mass, windows, balcony, entrance, roof, lod, texture, final ...). Use `--no-render` only for quick retries inside a step.

0. If there are photos and no `photo_refs.json`: create it (see Photo check). If you cannot see images, skip it.
1. The project folder already has a generator copy (made by `python tools/project.py new <name>`; `--template cw` for curtain walls). Change NAME, LEVEL, dimensions with `tools/edit.py`. Cycle. Must PASS.
2. Main mass only (boxes, roof, parapet, cores). Cycle. **Photo checkpoint: fix every PHOTO_MISMATCH about size, ratio and floors NOW** - details on a wrong mass are wasted work.
3. Windows (`WindowSet.add_face`) + window frames (`axbox`). Cycle. **Photo checkpoint: floor pitch must MATCH; look at the bay pitch line and previews/photo_check/facade_*.png.**
4. Facade parts one by one: balconies, railings (`gls`), piers, bands, louvers, canopy, entrance. Cycle after each.
5. Roof details. Cycle.
6. LOD1 (main shapes only, < 50% of main tris) and LOD2 (<= 500 tris, boxes + paint). Cycle.
7. Textures: tune atlas cells (painter, tile, photo textures). Cycle.
8. Final photo checkpoint: open `previews/photo_check/*.png` (photo | model | red overlay) and `previews/<asset>.png`. Fix what does not line up. Cycle.
9. Write the YAML. Report.

## Coordinates
1 unit = 1 m. Ground z = 0. Front (street) = **-Y**. Front wall at y = 0, back wall at y = depth, x centered on 0.
Faces: front = -Y, back = +Y, left = -X, right = +X. The kit moves the pivot to bottom-center on export.
Wall arguments for helpers: front `axis="y", c=0, s=-1`; back `axis="y", c=D, s=1`; left `axis="x", c=-W/2, s=-1`; right `axis="x", c=W/2, s=1`.
`a0,a1` = position along the wall (x for front/back, y for sides). `o0,o1` = distance outward from the wall.

## cs2kit API (`import cs2kit as K`)
```python
A = K.Atlas(size=4096, pad=16)
A.add(name, color=(r,g,b), ctrl=(0,0,0), metal=0.0, gloss=0.3, emissive=None, px=256,
      tile=None,           # (w_m, h_m): real-size material, faces auto-split to that size
      image=None, normal_image=None, gloss_image=None,   # files from extract_texture.py
      painter=None,        # fn(c): draw into the cell
      variants=1)
# painter c: c.joints(cols, rows, width_m=0.01, stagger=0.0, darken=0.25)  c.grain(amp=6)  c.stains(amount=0.08, streaks=0.5)
#            arrays c.rgb (h,w,3)  c.alpha (h,w) 0..255  c.height  c.gloss  c.emis ; coords c.u c.v (0..1) ; c.meters() for tile cells
mb = K.MeshBuilder(A)                                      # LOD2 builder: K.MeshBuilder(A, split_tiles=False)
mb.box(x0, x1, y0, y1, z0, z1, region, skip=("bottom",))   # region = "name" or dict(default=, top=, front=, back=, left=, right=)
K.axbox(mb, axis, c, s, a0, a1, o0, o1, z0, z1, region)    # box on a wall; o0=0 removes the wall-side face automatically
K.paint(mb, axis, c, s, a0, a1, z0, z1, region, layer=1)   # flat paint 1 cm in front of a wall; paint on paint -> layer=2
K.floor_quad(mb, x0, x1, y0, y1, z, region)                # horizontal face facing up
mb.quad(pts4, A.uv_full(name), name)                       # custom quad, CCW seen from outside; uv: A.uv, A.uv_full, A.uv_sub, A.uv_tile
W = K.WindowSet(); W.add_face(axis, c, s, a0, a1, z0, z1, floor=f, unit=u)   # one window, 2 cm in front of the wall
K.curtainwall(main, axis, c, s, a0, a1, z0, z1, fh, wins, lod1=l1, lod2=l2, module_w=1.5, spandrel_h=0.9, cell=None)  # curtain wall face: mullions+transoms mesh, spandrel paint, vision glass windows. see example_curtainwall_cs2.py
K.corner_post(mb, x, y, sx, sy, size, z0, z1)                # closes a corner when side faces use ends=(False, False)
K.export_asset(NAME, LEVEL, dict(main=mb, lod1=l1, lod2=l2, gls=g, lod1_gls=g1, windows=W), A,
               K.out_dir_from_argv("output"), lod2_tex=512)
```

## How to fix each ERROR
| ERROR starts with | Meaning | Fix |
|---|---|---|
| `COPLANAR` | two faces on the same plane, same direction (flicker) | attach parts with `axbox(o0=0)`; paint with `paint`, paint-on-paint `layer=2`; crossing members differ by >= 1 cm; side posts between top/bottom rails |
| `WIN_BLOCKED` | a part within 1.5 m in front of a window | move/shorten the part, or move the window |
| `WIN_UV` | window UV problem | use only `WindowSet.add_face`, no custom window UVs |
| `BOTTOM_FACE` | face at z=0 facing down | `skip=("bottom",)` on boxes standing on the ground |
| `LOD1_TOO_BIG` | LOD1 >= 50% of main | remove frames/louvers/rails from LOD1 |
| `LOD2_TOO_BIG` | LOD2 > 500 tris | build LOD2 with `K.MeshBuilder(A, split_tiles=False)`, fewer boxes, use paint |
| `ATLAS_UV` | a custom UV crosses atlas cells | use `A.uv*` helpers only |
| WARN `TEXEL` | blurry big faces | larger `px` or a `tile` for that material |

## CS2 facts (the kit enforces most)
Name `<Name>_L<level>_<w>x<d>`, no underscore inside Name, residential names contain `ResidentialHigh`. Lot cell 8 m; zoned max 6x6, larger = signature building.
Main about 50k tris (max 95k). LOD1 < 50% of main. LOD2 <= 500 tris. Details < 5 cm go to the normal map (painter height/joints), bigger details are mesh.
Defaults when unknown: residential floor height 2.9 m, shop ground floor 5.5 m, upper shop floors 4.5 m. Atlas 4096.
Texel targets: eye level 256 px/m, main walls 128, roof/high 64 (px / tile size).
Real mesh detail is wanted: window frames/mullions, sills, glass railings (gls) + handrail, louver blades, canopy, columns, doors, parapet coping, roof equipment, fences.
FBX scale is handled by the kit (`FBX_SCALE_NONE`). Do not change it.

## Photo check (compare with road view / satellite photos and rebuild when they do not match)
`cycle.py` compares the model with the photos when `photo_refs.json` exists and prints `MATCH` / `PHOTO_MISMATCH` / `INFO` lines,
plus `photo_mismatch=N` in the RESULT line. Sheets: `previews/photo_check/satellite.png`, `facade_<side>.png` (photo warped to the model | model | overlay).

Create `photo_refs.json` once (copy `templates/photo_refs.example.json` into the project folder, then fix the numbers):
- `satellite.corners`: building outline in the satellite photo, order front-left, front-right, back-right, back-left. Optional `m_per_px`.
- `facades[].corners`: one whole wall in a road view photo, order top-left, top-right, bottom-right, bottom-left (ground to roof top). `side` = front/back/left/right.
- Read pixels with `python tools/sat_grid.py grid <photo> -o previews/g.png --step 50` (zoom: `--crop x0,y0,x1,y1 --zoom 3 --step 10`).
- If the user already wrote `photo_refs.json`, do not change it.

What to change for each PHOTO_MISMATCH:
| Line | Fix |
|---|---|
| `satellite width/depth ratio`, `satellite width`, `satellite depth` | change W / D of the main mass (the photo value is the target) |
| `floor pitch ... needs MORE floors or lower floor height` | add floors, or lower floor height / ground floor height |
| `floor pitch ... needs FEWER floors or taller floors` | remove floors, or raise floor height |
| INFO `window bay pitch ... bays differ` | change window columns per unit / bay widths |
| INFO `edge agreement` low (< 50%) | open the facade sheet; move bands, piers, windows to the red-vs-photo differences |

Rules
- Fix, then run `cycle.py` again. Each mismatch gets at most 3 fix attempts.
- If ALL lines mismatch at once, the corners in `photo_refs.json` are probably wrong: check them on the grid image first.
- If a mismatch stays because of the photo (trees, strong perspective, wall partly hidden, photo shows a different wing), stop fixing it.
  Write the reason in the YAML under `photo_mismatch_notes:` and in the report.

## Photos
- Look at every image in the folder (subfolders too). File names hint the side (front, side, roof/satellite; Korean names too).
- If you cannot open images, use only the facts in `TASK.md` and write "photos not viewed" in the report.
- Count floors from window rows. Get scale from known objects (parking stall 2.5 x 5 m, futsal court 40 x 20 m).
- Photo textures are allowed via `extract_texture.py` (avoid signs, people, cars). Windows stay as `_Win` (no photo).
- Record photo textures in the YAML under `textures_from_photos:` (file, points, size m, px/m).

## Final report (Korean, short)
1. Files made or changed.
2. The `RESULT` line, the `[2/3 check]` lines and the `[photo]` lines from `cycle.py`, any WARN lines, and `photo_mismatch_notes`.
3. FBX made or not (Blender found or not).
4. Values I chose (estimated).
5. To check in game: real size, window grid, alpha parts see-through, thin parts flicker, night lights, front direction, color variations, entrance point, signature registration.
