# -*- coding: utf-8 -*-
"""One state document for a project: work/state.yaml.

`work/agent_state.json` stays the machine state the agent writes; this module mirrors the
parts that humans and later runs need (current stage, gate, per-stage artifact hashes) into
one YAML file. Stages are keyed by the cycle label (or mode), so `quick`, `windows`,
`final`, `fix:...` runs accumulate instead of overwriting each other.

    python tools/state.py --project P --init
    python tools/state.py --project P --json

The YAML is a projection: agent.py updates it after every cycle/fix, and a crash only
leaves the previous projection. Nothing reads it as the source of truth for a gate.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from proj import ROOT, KIT, NAME  # noqa: E402,F401  (consumes --project and chdirs)

try:
    import yaml
except Exception:  # noqa: BLE001 - fall back to JSON with the same fields
    yaml = None

STATE_VERSION = 1
STATE_NAME = os.path.join("work", "state.yaml")


def digest(path):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rel(path):
    if not path:
        return None
    try:
        return os.path.relpath(path, ROOT).replace(os.sep, "/")
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")


def load(root=None):
    root = root or ROOT
    path = os.path.join(root, STATE_NAME)
    if not os.path.isfile(path):
        return {"version": STATE_VERSION, "project": NAME, "stages": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) if yaml else json.load(f)
        return data if isinstance(data, dict) else {"version": STATE_VERSION, "stages": {}}
    except (OSError, ValueError):
        return {"version": STATE_VERSION, "project": NAME, "stages": {}}


def save(data, root=None):
    root = root or ROOT
    path = os.path.join(root, STATE_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if yaml:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        else:
            json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def artifact(root, path, key=None):
    if not path:
        return None
    full = path if os.path.isabs(path) else os.path.join(root, path)
    return {"path": rel(full), "exists": os.path.isfile(full), "sha256": digest(full), "key": key}


def sync(state, gate=None, stage=None, root=None):
    """Project agent_state.json (+ the last gate) into work/state.yaml.

    `state` is the agent state dict; `stage` is the cycle label or mode. Missing artifacts
    are recorded as exists=false instead of failing the update.
    """
    root = root or ROOT
    data = load(root)
    data["version"] = STATE_VERSION
    data["project"] = state.get("project") or NAME
    data["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    data["current_stage"] = state.get("current_stage")
    data["generator"] = state.get("generator")
    data["generator_hash"] = state.get("generator_hash")
    data["visual_review"] = state.get("visual_review")
    data["reviewed_preview_hash"] = state.get("reviewed_preview_hash")
    data.setdefault("stages", {})

    if gate:
        mode = gate.get("mode")
        label = stage or mode or "cycle"
        preview = (gate.get("artifacts") or {}).get("preview")
        fbx = (gate.get("artifacts") or {}).get("fbx")
        data["stages"][label] = {
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "status": gate.get("status"),
            "label": gate.get("label"),
            "gate": rel(os.path.join(root, "output", gate.get("asset", ""), "_check", "gate.json")),
            "checks": gate.get("checks") or {},
            "generator_hash": state.get("generator_hash"),
            "preview": artifact(root, preview),
            "fbx": artifact(root, fbx),
        }
        data["last_gate"] = {"mode": mode, "status": gate.get("status"),
                             "path": data["stages"][label]["gate"]}
    save(data, root)
    return data


def summary(data=None):
    data = data or load()
    stages = data.get("stages") or {}
    return {"status": "OK", "path": STATE_NAME, "current_stage": data.get("current_stage"),
            "last_gate": data.get("last_gate"),
            "stages": {k: {"mode": v.get("mode"), "status": v.get("status"),
                           "generator_hash": (v.get("generator_hash") or "")[:12],
                           "preview": (v.get("preview") or {}).get("sha256")}
                       for k, v in stages.items()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--init", action="store_true", help="write an empty state file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.init:
        data = load()
        data.setdefault("stages", {})
        save(data)
    data = load()
    out = summary(data)
    print(json.dumps(out, ensure_ascii=False) if a.json else _human(out))
    return 0


def _human(out):
    lines = ["[state] %s  current %s" % (out["path"], out.get("current_stage") or "-")]
    for name, st in (out.get("stages") or {}).items():
        lines.append("  %-14s %-8s %s  %s" % (name, st.get("status") or "-",
                                               st.get("mode") or "-", (st.get("preview") or "-")[:12]))
    if out.get("last_gate"):
        lines.append("  last gate: %s %s" % (out["last_gate"].get("mode"), out["last_gate"].get("status")))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
