# CS2 building kit installation — DeepSeek via Codex

## Included

- `AGENTS.md`: short DeepSeek working rules and reasoning routing
- `TOOLS.md`, `docs/agent/`: on-demand tool and modeling references
- `cs2kit.py` and example generators
- `tools/agent.py`: portable JSON workflow
- `tools/cycle.py`: quick/visual/final gate
- `tools/`: checking, preview, photo/material/scan measurement, Blender integration
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
   # curtain wall: python tools/project.py new my-apt --template cw
   # mixed-use/school/irregular: python tools/project.py new my-building --template generic
   ```

<<<<<<< HEAD
7. Configure `deepseek-flash` using `docs/agent/DEEPSEEK.md`, then start Codex at the kit root. Never store the API key in project files. The first machine check is:

   ```bash
   python tools/agent.py doctor --project my-apt --json
   ```
=======
6. Start Claude Code at the kit root and run `/build`.
>>>>>>> eb37db5 (Export FBX without a Blender install (bpy module))

The project contains `TASK.md`, `STATUS.md`, `photos/`, and a copied generator. Reference photos stay in `photos/`; output assets go to `output/`; state and observations go to `work/`.

Optional Naver VR capture also needs `pip install playwright` and Chrome running with remote debugging port 9222. See `docs/agent/NAVER_VR.md`; Blender is not used for VR capture or `make_refs`.

IFC conversion needs BlenderBIM/Bonsai, IfcConvert or FreeCAD; `tools/ifc_to_glb.py --check` reports what is available. See `docs/agent/IFC_TO_GLB.md`.

Optional video frame extraction needs ffmpeg on PATH or `pip install imageio-ffmpeg`. See `docs/agent/VIDEO_FRAMES.md`.

## Upgrade

Overwrite kit files with the new distribution. Keep `projects/` and `memory/`; they contain user work and are not part of the base distribution. Back them up before major upgrades.

For an old flat layout, preview migration and then apply it:

```bash
python tools/project.py migrate old-name
python tools/project.py migrate old-name --apply
```

See `README.md` and `docs/agent/WORKFLOW.md` for daily use.
