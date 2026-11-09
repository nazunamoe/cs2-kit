# Portable agent workflow

Use this file when building, resuming, or fixing an asset. CLI-specific files should contain only tool preferences.

## 1. Start

Run from the kit root. Agent commands always require an explicit project; do not rely on `projects/.current`.

```bash
python tools/agent.py doctor --project <project> --json
python tools/agent.py resume --project <project> --json
```

Read `TASK.md`, the selected generator, and only references needed for that building type. Use native editing tools when available. Never interpolate source into shell strings. `tools/put.py` and `tools/edit.py` are fallbacks.

If GLB/GLTF exists, reconstruct the mass before drawing it manually. `doctor` lists scans and returns a `glb-mass --list` action for a new project. Select building meshes, generate simplified multi-height footprints into `generic_spec.json`, and inspect `previews/glb/shape.png` plus its report. See `docs/agent/GLB_MASS.md`. Source geometry and textures remain references only.

## 2. Photos without repeated image reads

```bash
python tools/agent.py photos --project <project> --page 0 --page-size 16 --json
```

Inspect one contact-sheet page. Select representative, non-duplicate images and crop only ambiguous regions with `tools/sat_grid.py`. Record observations so unchanged photos need not be read again:

```bash
python tools/agent.py observe --project <project> --photo photos/front.jpg --side front --note "36 rows; left 3 bays obscured" --json
```

Create `photo_refs.json` when images can be inspected. An existing but empty refs file is a failed configuration, not a skipped check. If image input is unavailable, do not invent observations: use supplied refs or report that visual review is unavailable.

## 3. Build loop

Use one semantic change per iteration and the smallest useful gate. Add `--brief` for a minimal model-facing result.

```bash
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode quick --label mass --brief --json
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode visual --label windows --brief --json
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode final --label final --brief --json
```

- `quick`: normal Python, OBJ, geometry/spec checks. Use for syntax and geometry-error retries.
- `visual`: OBJ, preview, and photo checks when refs exist.
- `final`: Blender FBX/.blend, preview, shared photo/tile analysis, full LOD, and strict gate.

Add `--jsonl work/gates.jsonl` to append one record per run (time, mode, label, status, checks, hashes, gate path). The history survives state resets and makes failure patterns greppable:

```bash
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode final --label final --jsonl work/gates.jsonl --json
jq -c 'select(.status!="PASS")' <project>/work/gates.jsonl
```

Follow the JSON `next_action`. Do not parse full logs unless the summary points to them. Detailed reports are in `output/<asset>/_check/gate.json`; raw output is in `work/logs/last_cycle.log`.

Build order: mass -> windows -> facade parts -> roof -> LOD -> textures -> YAML -> final. Correct mass and floor pitch before detail.

## 4. Gate meaning and visual evidence

- `PASS`: every requested check and required review passed.
- `FAIL`: a requested check ran and failed.
- `INCOMPLETE`: a required check or visual review did not run.
- `NEEDS_HUMAN_REVIEW`: automated retries stopped or visual input is unavailable.
- `NOT_APPLICABLE`: no `photo_refs.json` exists.
- `NOT_CHECKED`: never treat this as verified.
- `PARTIAL`: some required review artifacts were not inspected.

After visual/final, run the exact review command returned in `next_action`. It includes `--artifact` for the current preview and required photo/tile images. Inspect those images before executing it. Example shape:

```bash
python tools/agent.py review --project <project> --status PASS --note "reviewed current images" --artifact previews/<asset>.png --artifact previews/photo_check/facade_front.png --json
```

Use `--status FAIL` when images disagree. If image input is unavailable, use `--status NEEDS_HUMAN_REVIEW`; do not claim PASS. Changing the generator or rendering a new preview resets the review. Review records artifact paths and hashes.

A final strict run requires Blender, FBX, executed photo/tile checks when refs exist, LOD, and visual review. Tile scores are advisory; execution failures and explicit photo mismatches are not.

## 5. Resume and retry limits

`work/agent_state.json` stores generator/preview hashes, last gate, next action, stable mismatch IDs/count, and review artifacts. `STATUS.md` is its short human summary. Read these instead of replaying old conversations.

Do not repeat an unchanged failing command. After three attempts with the same wall+metric mismatch, the agent returns `NEEDS_HUMAN_REVIEW` instead of another visual loop. Record evidence and reasons in `building_spec_<Name>.yaml` under `photo_mismatch_notes`.

## 6. Scoped fix

Begin before editing. Use the current asset from the last gate or pass `--asset`.

```bash
python tools/agent.py fix --project <project> --generator <name>_cs2.py --request "change only entrance railing" --box=x0,x1,y0,y1,z0,z1 --json
```

Edit only the requested scope, then run the exact returned `--finish` command. This runs final and `compare.py diff`. A mesh change outside `--box` fails the fix. If the current build fails or produces another asset, compare is `NOT_CHECKED`; stale output is never used as a successful diff. Inspect the returned artifacts and record review before final PASS.

## 7. Final report

Report changed files, final gate/check statuses, warnings, FBX status, estimated values, remaining photo/tile issues with reasons, and in-game checks. Never report final PASS for FAIL, INCOMPLETE, PARTIAL, or NEEDS_HUMAN_REVIEW.
