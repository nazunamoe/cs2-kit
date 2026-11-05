---
name: build
description: Build the active CS2 building through the shared quick/visual/final gates
argument-hint: "[optional modeling request]"
---

Read `CLAUDE.md`, the active project `TASK.md`, and `docs/agent/WORKFLOW.md`. Apply the user's additional request: `$ARGUMENTS`.

1. Determine the active project with `python tools/project.py where`, then use its folder name explicitly in every agent command.
2. Run `agent.py doctor` and `agent.py photos` with `--json`. Inspect contact-sheet pages and only necessary representative/cropped photos. Record observations and wall-linked evidence using `docs/agent/PHOTO_ONLY.md`.
3. Create or verify `photo_refs.json` when images are available, linking `wall_id` when metadata exists. Never change user-authored refs. For mixed-use/school/irregular buildings use `--template generic` and `docs/agent/VOLUMES.md`.
4. Follow mass -> windows -> facade -> roof -> LOD -> textures -> YAML. Use quick for error retries and visual at mass/window/facade/material checkpoints.
5. Follow each JSON `next_action`; do not dump full logs or read unchanged photos again.
6. Run final strict, inspect current/flagged images, and record `agent.py review`. Write `building_spec_<Name>.yaml` with estimates and mismatch notes.
7. Report the actual gate states. Do not stop at quick PASS or claim final PASS for FAIL/INCOMPLETE.
