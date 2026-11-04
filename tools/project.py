# -*- coding: utf-8 -*-
"""
project.py - manage projects and the memory folder (run from the kit root)

  python tools/project.py init                          create memory/ (from templates/memory, never overwrites) and projects/
  python tools/project.py new <name> [--template cw]    projects/<name>/ with TASK.md + generator copy, becomes the active project
                                                        (--template cw = curtain wall example; default = slab apartment example)
  python tools/project.py use <name>                    make <name> the active project (projects/.current)
  python tools/project.py list                          projects, * = active
  python tools/project.py where                         active project folder
  python tools/project.py migrate <name> [--apply] [--facade-tools]
                                                        move the old FLAT layout (TASK.md, photos, <x>_cs2.py, output/, previews/ ...) of the
                                                        kit root into projects/<name>/. Without --apply it only lists what would move.
<name>: letters, digits, - and _ (a folder name, not the asset name; no real complex names - SPEC ch.8)
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
PROJECTS = os.path.join(KIT, "projects")
MEMORY = os.path.join(KIT, "memory")
TEMPLATES = os.path.join(KIT, "templates")
CUR = os.path.join(PROJECTS, ".current")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def p(*a):
    print(*a)


def init():
    os.makedirs(PROJECTS, exist_ok=True)
    os.makedirs(MEMORY, exist_ok=True)
    src = os.path.join(TEMPLATES, "memory")
    for f in sorted(os.listdir(src)):
        dst = os.path.join(MEMORY, f)
        if os.path.exists(dst):
            p(f"[init] memory/{f} exists - kept")
        else:
            shutil.copyfile(os.path.join(src, f), dst)
            p(f"[init] memory/{f} created")
    if not os.path.exists(os.path.join(PROJECTS, "README.md")):
        with open(os.path.join(PROJECTS, "README.md"), "w", encoding="utf-8") as f:
            f.write("# projects/\nOne folder per building (TASK.md, photos, generator, output/, previews/). Make one with `python tools/project.py new <name>`.\n")


def valid(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name or ""):
        raise SystemExit("[project] name: letters, digits, - and _ only, e.g. apt-slab-01")


def use(name):
    if not os.path.isdir(os.path.join(PROJECTS, name)):
        raise SystemExit(f"[project] no such project: {name}")
    os.makedirs(PROJECTS, exist_ok=True)
    with open(CUR, "w", encoding="utf-8") as f:
        f.write(name)
    p(f"[project] active: {name}  ({os.path.join('projects', name)})")


def new(name, template):
    valid(name)
    init()
    d = os.path.join(PROJECTS, name)
    if os.path.exists(d):
        raise SystemExit(f"[project] projects/{name} already exists")
    os.makedirs(os.path.join(d, "photos"))
    shutil.copyfile(os.path.join(TEMPLATES, "TASK.md"), os.path.join(d, "TASK.md"))
    shutil.copyfile(os.path.join(TEMPLATES, "STATUS.md"), os.path.join(d, "STATUS.md"))
    ex = "example_curtainwall_cs2.py" if template == "cw" else "example_building_cs2.py"
    gen = name.replace("-", "_") + "_cs2.py"
    shutil.copyfile(os.path.join(KIT, ex), os.path.join(d, gen))
    use(name)
    p(f"[project] made projects/{name}/ : TASK.md (fill in), photos/ (put photos here), {gen} (copy of {ex})")
    p(f"          build: python tools/cycle.py {gen} --label mass     (paths are relative to the active project)")


def lst():
    cur = open(CUR, encoding="utf-8").read().strip() if os.path.exists(CUR) else ""
    names = sorted(d for d in os.listdir(PROJECTS) if not d.startswith(".") and os.path.isdir(os.path.join(PROJECTS, d))) if os.path.isdir(PROJECTS) else []
    for n in names:
        p(("* " if n == cur else "  ") + n)
    if not names:
        p("(no projects yet - python tools/project.py new <name>)")


def migrate(name, apply, facade):
    valid(name)
    names = {"TASK.md", "STATUS.md", "photo_refs.json", "shape_notes.md", "research_notes.md", "SPEC.md"}
    dirs = {"output", "previews", "backup", "textures_src", "refs", "photos"}
    if facade:
        dirs.add("facade_tools")
    keep_files = {"cs2kit.py", "example_building_cs2.py", "example_curtainwall_cs2.py"}
    move = []
    for f in sorted(os.listdir(KIT)):
        path = os.path.join(KIT, f)
        if f in ("projects", "memory", "templates", "tools", ".claude", "__pycache__", "facade_tools") and not (f == "facade_tools" and facade):
            continue
        if os.path.isdir(path):
            if f in dirs:
                move.append(f)
        else:
            low = f.lower()
            if f in keep_files:
                continue
            if f in names or (f.endswith("_cs2.py")) or re.fullmatch(r"building_spec.*\.ya?ml", f) or low.endswith((".glb", ".jpg", ".jpeg", ".png", ".webp")):
                move.append(f)
    if not move:
        p("[migrate] nothing to move (the kit root has no old project files)")
        return
    p(f"[migrate] -> projects/{name}/ :")
    for f in move:
        p("   " + f)
    if not apply:
        p("(dry run - add --apply to move them)")
        return
    d = os.path.join(PROJECTS, name)
    os.makedirs(d, exist_ok=True)
    for f in move:
        dst = os.path.join(d, f)
        if os.path.exists(dst):
            p(f"   SKIP {f}: already in projects/{name}")
            continue
        shutil.move(os.path.join(KIT, f), dst)
    init()
    use(name)
    p("[migrate] done. If you did not move facade_tools/, it stays in the kit root (it is specific to one project).")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    c = a[0]
    if c == "init":
        init()
    elif c == "new" and len(a) >= 2:
        tpl = a[a.index("--template") + 1] if "--template" in a else ""
        new(a[1], tpl)
    elif c == "use" and len(a) >= 2:
        use(a[1])
    elif c == "list":
        lst()
    elif c == "where":
        cur = open(CUR, encoding="utf-8").read().strip() if os.path.exists(CUR) else ""
        p(os.path.join(PROJECTS, cur) if cur else "(no active project - old flat layout: " + KIT + ")")
    elif c == "migrate" and len(a) >= 2:
        migrate(a[1], "--apply" in a, "--facade-tools" in a)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
