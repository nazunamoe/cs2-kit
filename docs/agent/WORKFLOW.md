# Portable agent workflow

Use this file when building, resuming, or fixing an asset. CLI-specific files should contain only tool preferences.

## 1. Start

Run from the kit root. Agent commands always require an explicit project; do not rely on `projects/.current`.

```bash
python tools/agent.py doctor --project <project> --json
python tools/agent.py resume --project <project> --json
```

Read `TASK.md`, the selected generator, and only the reference documents needed for that building type. Use the native file-editing tool when available. Never interpolate source code into shell strings. `tools/put.py` and `tools/edit.py` are fallbacks for environments without reliable native editing.

## 2. Photos without repeated image reads

```bash
python tools/agent.py photos --project <project> --page 0 --page-size 30 --json
```

Inspect one contact-sheet page. Select representative, non-duplicate images. Crop only ambiguous walls or details with `tools/sat_grid.py`. Record observations so unchanged photos need not be read again:

```bash
python tools/agent.py observe --project <project> --photo photos/front.jpg --side front --note "36 rows; left 3 bays obscured" --json
```

Create `photo_refs.json` when images can be inspected. If image input is unavailable, do not invent visual observations: use supplied refs or record visual/photo checks as unavailable.

## 3. Build loop

Use one semantic change per iteration. Choose the smallest useful gate:

```bash
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode quick --label mass --json
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode visual --label windows --json
python tools/agent.py cycle --project <project> --generator <name>_cs2.py --mode final --label final --json
```

- `quick`: normal Python, OBJ, geometry/spec checks. Use for syntax and geometry-error retries.
- `visual`: OBJ, preview, and photo checks when refs exist. Use after mass, windows, facade, roof, and material changes.
- `final`: Blender FBX/.blend, preview, photo, tiles, full LOD, and strict gate. Use before reporting and scoped-fix completion.

Follow the JSON `next_action`. Do not parse the entire raw log unless the summary points to it. Detailed reports are in `output/<asset>/_check/gate.json`; raw output is in `work/logs/last_cycle.log`.

Build order: mass -> windows -> facade parts -> roof -> LOD -> textures -> YAML -> final. Correct mass and floor pitch before adding detail.

## 4. Gate meaning

- `PASS`: every requested check passed.
- `FAIL`: a requested check ran and failed.
- `INCOMPLETE`: a required check or visual review did not run.
- `NOT_APPLICABLE`: no `photo_refs.json` exists; this is not a failed photo comparison.
- `NOT_CHECKED`: never treat this as verified.

After a visual/final run, inspect the current preview and only flagged photo/tile images. Then record the review:

```bash
python tools/agent.py review --project <project> --status PASS --note "reviewed final preview and flagged tiles" --json
```

Use `--status FAIL` when the images disagree with the references. Changing the generator resets the review to `NOT_CHECKED`.

A final strict run requires Blender, FBX, executed photo/tile checks when refs exist, LOD, and visual review. Tile scores are advisory; execution failures and explicit photo mismatches are not.

## 5. Resume and retry limits

`work/agent_state.json` stores the generator hash, last gate, next action, mismatch signature/count, and visual review. `STATUS.md` is its short human-readable summary. Read these instead of replaying old conversations.

Do not repeat an unchanged failing command. After three attempts on the same photo mismatch, stop changing that item and record the evidence and reason in `building_spec_<Name>.yaml` under `photo_mismatch_notes`.

## 6. Scoped fix

Begin before editing. Use the current asset from the last gate or pass `--asset`.

```bash
python tools/agent.py fix --project <project> --generator <name>_cs2.py --request "change only entrance railing" --box=x0,x1,y0,y1,z0,z1 --json
```

Edit only the requested scope, then run the exact `next_action` command, equivalent to:

```bash
python tools/agent.py fix --project <project> --generator <name>_cs2.py --finish --json
```

This runs the final gate and `compare.py diff`. A mesh change outside `--box` fails the fix. Review the resulting preview before final PASS.

## 7. Final report

Report changed files, final gate/check statuses, warnings, FBX status, estimated values, remaining photo/tile issues with reasons, and in-game checks. Do not report final PASS when the gate is FAIL or INCOMPLETE.
