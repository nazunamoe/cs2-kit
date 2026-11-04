---
name: fix
description: Apply a scoped CS2 asset fix with final gate and outside-scope comparison
argument-hint: "<requested change>"
---

Requested change: `$ARGUMENTS`.

1. Resolve the active project and read `work/agent_state.json` for the current generator and asset.
2. Run `agent.py fix` with explicit `--project`, `--generator`, `--request`, and a measured `--box` when the changed volume is known.
3. Use native Read/Edit to change only that scope.
4. Run the exact returned `agent.py fix --finish` command. Do not replace it with quick.
5. Inspect the final preview and flagged images, review the compare result, then run `agent.py review`.
6. Report any LOD/photo failure or outside-scope change instead of claiming success.
