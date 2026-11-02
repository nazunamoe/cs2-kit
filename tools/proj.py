# -*- coding: utf-8 -*-
"""
proj.py - which project folder do the tools work on?  (import it FIRST in every tool, before argparse)

Layout:   <kit root>/tools, cs2kit.py, memory/, projects/<name>/ (TASK.md, photos, <Name>_cs2.py, output/, previews/ ...)
After `import proj` the tool has done two things:
  1. os.chdir(project folder)  -> every relative path (output/..., previews/..., photo_refs.json) is relative to the PROJECT
  2. argv paths that exist where you stand (e.g. projects/foo/foo_cs2.py typed from the kit root) were turned into absolute paths
     first, so they still work.
The project is decided in this order:
  --project <name|path>   (removed from argv)   >   an argv path inside projects/<name>/   >   env CS2_PROJECT
  >   the current folder inside projects/<name>/   >   projects/.current (written by tools/new_project.py)   >   kit root (old flat layout)
Exports: KIT (kit root), ROOT (project folder, or KIT in the old layout), NAME (project name or "")
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
PROJECTS = os.path.join(KIT, "projects")
_CWD = os.getcwd()


def _inside(path, base):
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path == base or path.startswith(base + os.sep)


def _project_of(path):
    """projects/<name>/... -> absolute project folder, else None"""
    if not _inside(path, PROJECTS):
        return None
    rel = os.path.relpath(os.path.abspath(path), PROJECTS).split(os.sep)
    if not rel or rel[0] in (".", "") or rel[0].startswith("."):
        return None
    return os.path.join(PROJECTS, rel[0])


def _resolve(name):
    if os.path.isdir(os.path.join(PROJECTS, name)):
        return os.path.join(PROJECTS, name)
    if os.path.isdir(name):
        return os.path.abspath(name)
    raise SystemExit(f"[project] no such project: {name}  (projects/ has: {', '.join(list_projects()) or 'nothing yet'})")


def list_projects():
    if not os.path.isdir(PROJECTS):
        return []
    return sorted(d for d in os.listdir(PROJECTS) if not d.startswith(".") and os.path.isdir(os.path.join(PROJECTS, d)))


def current_file():
    return os.path.join(PROJECTS, ".current")


def _decide():
    argv = sys.argv
    for i, a in enumerate(argv):                       # 1 --project
        if a == "--project" and i + 1 < len(argv):
            v = argv[i + 1]
            del argv[i:i + 2]
            return _resolve(v)
        if a.startswith("--project="):
            del argv[i]
            return _resolve(a.split("=", 1)[1])
    for a in argv[1:]:                                  # 2 a path inside projects/<name>/
        if a and not a.startswith("-"):
            p = _project_of(os.path.join(_CWD, a))
            if p:
                return p
    v = os.environ.get("CS2_PROJECT")                   # 3 env
    if v:
        return _resolve(v)
    p = _project_of(_CWD)                               # 4 cwd
    if p:
        return p
    try:                                                # 5 .current
        name = open(current_file(), encoding="utf-8").read().strip()
        if name and os.path.isdir(os.path.join(PROJECTS, name)):
            return os.path.join(PROJECTS, name)
    except OSError:
        pass
    return None


def _activate():
    proj = _decide()
    if not proj:
        return KIT, ""
    if not _inside(_CWD, proj):                         # keep paths that exist here working after the chdir
        for i in range(1, len(sys.argv)):
            a = sys.argv[i]
            if not a or a.startswith("-") or os.path.isabs(a):
                continue
            here = os.path.abspath(os.path.join(_CWD, a))
            if _inside(here, PROJECTS) or (os.path.exists(here) and not os.path.exists(os.path.join(proj, a))):
                sys.argv[i] = here
        os.chdir(proj)
    os.environ["CS2_PROJECT"] = proj                    # child processes use the same project
    return proj, os.path.basename(proj)


ROOT, NAME = _activate()
