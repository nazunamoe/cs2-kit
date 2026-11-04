---
name: resume
description: Resume the active CS2 project from its saved machine state
---

1. Get the project with `python tools/project.py where`.
2. Run `python tools/agent.py resume --project <name> --json` using the explicit folder name.
3. Read `STATUS.md` and only the referenced current generator, gate, or observation files needed for the next action.
4. Execute the returned `next_action`; do not restart the build or replay old photo analysis.
5. If there is no state, run `agent.py doctor`, read `TASK.md`, and start the remaining workflow rather than guessing a generator.
