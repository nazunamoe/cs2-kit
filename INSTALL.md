# CS2 building kit installation — Claude Code

## Included

- `CLAUDE.md`: Claude-specific adapter; `AGENTS.md`: short shared rules
- `.claude/skills/`: `/build`, `/resume`, `/photo-refs`, `/fix`
- `.claude/settings.json`: Korean, tool permissions, final/fix Stop hook
- `TOOLS_CLAUDE.md`, `docs/agent/`: on-demand references
- `cs2kit.py`, example generators, and `tools/`
- `tools/agent.py`: shared JSON workflow; `tools/cycle.py`: quick/visual/final gate
- `templates/`: TASK, STATUS, photo refs, memory templates

## Setup

1. Extract the kit into a writable folder.
2. Install Python 3.9+ and run `pip install numpy pillow`.
3. Run `python tools/project.py init`.
4. FBX export needs Blender **or** the `bpy` Python module. The module needs no app install:
   its wheels track one Python version (Blender 5.0 → 3.11, 5.1 → 3.13), so use a dedicated venv.

   ```bash
   uv venv .venv-bpy --python 3.11
   uv pip install --python .venv-bpy bpy
   python tools/run_blender.py --find
   ```

   Or point it at an existing install:

   ```bash
   python tools/run_blender.py --set "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
   python tools/run_blender.py --set-py ".venv-bpy\Scripts\python.exe"
   ```

   `run_blender.py` prefers the bpy module (same exporter, headless); set `RUN_BLENDER_ENGINE=exe` to force Blender.
   Without either it still writes OBJ (`--obj`), which covers checks, previews and LOD checks.

5. Create a project and add photos/TASK values:

   ```bash
   python tools/project.py new my-apt
   # or: python tools/project.py new my-apt --template cw
   ```

6. Start Claude Code at the kit root and run `/build`.

The project contains `TASK.md`, `STATUS.md`, `photos/`, and a copied generator. Reference photos stay in `photos/`; output assets go to `output/`; state and observations go to `work/`.

Check the environment at any time:

```bash
python tools/agent.py doctor --project my-apt --json
```

Optional Naver VR capture also needs `pip install playwright` and Chrome running with remote debugging port 9222. See `docs/agent/NAVER_VR.md`; Blender is not used for VR capture or `make_refs`.

## Upgrade

Overwrite kit files with the new distribution, including `.claude/`. Keep `projects/` and `memory/`; they contain user work and are not part of the base distribution. Back them up before major upgrades.

For an old flat layout:

```bash
python tools/project.py migrate old-name
python tools/project.py migrate old-name --apply
```

See `README.md` and `docs/agent/WORKFLOW.md` for daily use.
