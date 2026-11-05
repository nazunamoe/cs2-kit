# CS2 building agent — portable core

Create one `<Name>_cs2.py` and `building_spec_<Name>.yaml` from the active project's `TASK.md`. Report in Korean. Target Blender 5.2; the kit handles Blender API differences.

## Non-negotiable rules

1. Use the kit. Do not write another checker/renderer/exporter. Do not edit `tools/` or `cs2kit.py` unless the user explicitly requests kit development.
2. Do not ask routine modeling questions. Choose a reasonable value, mark it `# estimated` in YAML, and list it in the report.
3. No real brand, logo, complex name, or sign text in asset names or textures.
4. Never move, edit, or copy reference photos. Never put reference photos in `output/`.
5. Keep one semantic change per iteration. Use native Edit/apply_patch tools when available. Never write source through shell string interpolation. Use `tools/put.py`/`tools/edit.py` only as a fallback; see `docs/agent/POWERSHELL.md` if needed.
6. Read only the references needed for the current building. Do not load `cs2kit.py`, all tools, all photos, or global project history by default. Use `inspect.signature` for an uncertain API.
7. A skipped check is not a pass. Never report final PASS for FAIL or INCOMPLETE.

## Start and resume

Run from the kit root. Agent commands require an explicit project; do not rely on `projects/.current`.

```bash
python tools/agent.py doctor --project <project> --json
python tools/agent.py resume --project <project> --json
```

For a new building, a human or an explicit setup step runs `python tools/project.py new <project> [--template cw|generic]`. Use `generic` for data-driven mixed-use/school/irregular volumes. Read `TASK.md`, the selected generator, and `docs/agent/WORKFLOW.md`.

When GLB/GLTF exists, use it for the mass before hand-drawing geometry. Run `agent.py glb-mass --project P --json -- photos/scan.glb --list`, select only building meshes, then generate `generic_spec.json` with `glb-mass`. Follow `docs/agent/GLB_MASS.md`. Use its simplified footprints, height tiers, source hash, and wall IDs; inspect `previews/glb/shape.png` and warnings. Never copy source triangles or textures. Photo evidence still controls openings and materials.

Global memory is not a source of building-specific facts. Retrieve only relevant, scoped lessons using `docs/agent/MEMORY.md`. Keep current-building observations in project files.

## Gates and next actions

```bash
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode quick --label mass --json
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode visual --label windows --json
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode final --label final --json
```

- `quick`: OBJ + geometry/spec checks, no Blender required.
- `visual`: OBJ + preview + photo checks when refs exist.
- `final`: FBX + full photo/tile/LOD checks + strict gate.

Follow the compact JSON `next_action`; do not dump full logs. `NOT_CHECKED` is unverified, `NOT_APPLICABLE` means no photo refs. After visual/final, inspect every artifact listed in `next_action` and run that exact review command. `PARTIAL` is not PASS; without image input use `NEEDS_HUMAN_REVIEW`.

## Photos

Use `agent.py photos` contact-sheet pages before opening individual images. Record observations with `agent.py observe`; unchanged observed photos need not be read again. Crop only ambiguous regions. If image input is unavailable, say so and use supplied `photo_refs.json`; never invent visual findings.

Build order: mass -> windows -> facade parts -> roof -> LOD -> textures -> YAML -> final. Fix mass ratio and floor pitch before detail. A repeated mismatch gets at most three attempts; then record its evidence and reason under `photo_mismatch_notes`.

For scoped changes use `agent.py fix ... --request ... --box=...`, edit, then the returned `--finish` command. The finish gate includes outside-scope mesh comparison.

## Coordinates and core API

1 unit = 1 m; ground z=0; front/street = -Y; front wall y=0; back y=depth; x centered on 0. Faces: front=-Y, back=+Y, left=-X, right=+X. Wall helpers: front `axis="y",c=0,s=-1`; back `axis="y",c=D,s=1`; left `axis="x",c=-W/2,s=-1`; right `axis="x",c=W/2,s=1`.

```python
import cs2kit as K
A = K.Atlas(size=4096, pad=16)
A.add("wall", color=(180,180,180), ctrl=(0,0,0), px=256, tile=(3.0,2.9))
mb = K.MeshBuilder(A)
mb.box(x0,x1,y0,y1,z0,z1,"wall",skip=("bottom",))
K.axbox(mb,"y",0,-1,a0,a1,0,0.2,z0,z1,"frame")
K.paint(mb,"y",0,-1,a0,a1,z0,z1,"accent",layer=1)
W = K.WindowSet(); W.add_face("y",0,-1,a0,a1,z0,z1,floor=f,unit=u)
l2 = K.MeshBuilder(A, split_tiles=False)
K.export_asset(NAME,LEVEL,dict(main=mb,lod1=l1,lod2=l2,gls=g,lod1_gls=g1,windows=W),A,K.out_dir_from_argv("output"))
```

Use `WindowSet.add_face` for windows. Use atlas UV helpers for custom quads. `axbox(o0=0)` attaches to an existing wall; do not use it for a wall-less roof screen. LOD1 < 50% of main, LOD2 <= 500 tris, main target 30k-60k and hard warning above 95k. Never reduce actual floors or bays merely to reduce triangles.

## On-demand references

- Full workflow, resume, review, fix: `docs/agent/WORKFLOW.md`
- Tool commands and preset API: `TOOLS_CLAUDE.md`
- Detailed facade/photo modeling: `docs/agent/MODELING.md`
- Existing facade lessons: `docs/FACADE_KNOWHOW.md`
- Photo-only evidence and wall refs: `docs/agent/PHOTO_ONLY.md`
- Generic volumes and feature schema: `docs/agent/VOLUMES.md`
- Memory scope: `docs/agent/MEMORY.md`
- PowerShell editing fallback: `docs/agent/POWERSHELL.md`

## Final report

Report files, exact gate/check statuses, warnings, FBX status, estimated values, remaining photo/tile issues and reasons, and in-game checks: real scale, window grid, alpha, flicker, night lights, front direction, colors, entrance, and signature registration.
