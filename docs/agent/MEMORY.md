# Memory scope

Only stable, reusable procedure belongs in auto-loaded `memory/LESSONS.md`.

Each lesson should include scope when it is not universal:

```text
- scope=curtainwall | applies_to=glass_facades | source=<project/tool> | confidence=verified-on-photos
  Observation -> the procedure to follow.
```

Keep the following out of global auto-loaded memory:

- building-specific colors, bay sequences, floor rules, coordinates, or asset names;
- one project's camera alignment and occlusion notes;
- uncertain values that have not been verified.

Store those in the project's `work/observations.json`, research notes, or building YAML. `memory/VALUES.md` is for reusable defaults and clearly sourced reusable measurements. Put building-specific measurements in that project's files.

Prefer deterministic enforcement in `cs2kit` or `tools/check.py` over repeatedly adding prose lessons. Do not copy global memory values into a different building merely because they exist; retrieve by building type and verify against current evidence.
