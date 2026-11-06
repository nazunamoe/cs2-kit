# -*- coding: utf-8 -*-
"""Reusable facade style data shared by project generators.

A style is a small YAML file (palette + window + paint layers + night policy).
Geometry, mass, and wall roles stay in the project generator; the style only
supplies repeatable finish decisions.

  from templates.facade_style import load_style, list_styles
  style = load_style("templates/styles/apartment_2020_lightstone.yaml")
  style.color("wall")
  style.window.width_m
  style.layer("spandrel_height_m")
"""
import glob
import os
from types import SimpleNamespace

try:
    import yaml
except ImportError:  # Blender's bundled Python has no PyYAML
    yaml = None


REQUIRED = ("id", "palette", "window", "layers")


def _scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~", ""):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _value(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        if not body:
            return []
        return [_scalar(part) for part in body.split(",")]
    return _scalar(text)


def _mini_yaml(text):
    """Parse the small mapping/list subset used by templates/styles/*.yaml.

    This is the fallback for Blender, whose Python does not ship PyYAML.
    It handles nested mappings, inline lists and skips `>` block scalars.
    """
    data = {}
    stack = [(-1, data)]
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if value in (">", "|", ">-", "|-"):
            parent[key] = ""
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip(" "))) <= indent:
                    break
                i += 1
            continue
        if value == "":
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _value(value)
    return data


def load_style(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    data = (yaml.safe_load(text) if yaml is not None else _mini_yaml(text)) or {}
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        raise ValueError(f"{path}: style missing {', '.join(missing)}")
    return Style(data, path)



class Style:
    def __init__(self, data, path=""):
        self.data = data or {}
        self.path = path
        self.id = self.data.get("id", "")
        self.label = self.data.get("label", self.id)
        self.era = self.data.get("era", "")
        self.type = self.data.get("type", "")
        self.tags = list(self.data.get("tags", []))
        self.palette = {k: tuple(v) for k, v in (self.data.get("palette") or {}).items()}
        self.window = SimpleNamespace(**(self.data.get("window") or {}))
        self.layers = SimpleNamespace(**(self.data.get("layers") or {}))
        self.night = SimpleNamespace(**(self.data.get("night") or {}))
        self.zones = self.data.get("zones") or {}
        self.notes = self.data.get("notes", "")

    def color(self, name, default=(200, 200, 200)):
        value = self.palette.get(name, default)
        return tuple(int(v) for v in value)

    def layer(self, name, default=0.0):
        return getattr(self.layers, name, default)

    def win(self, name, default=0.0):
        return getattr(self.window, name, default)

    def night_value(self, name, default=None):
        return getattr(self.night, name, default)

    def to_dict(self):
        return dict(self.data)


def list_styles(directory):
    rows = []
    for path in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
        try:
            style = load_style(path)
        except Exception as exc:
            rows.append(dict(id=os.path.basename(path), status="ERROR", error=str(exc), path=path))
            continue
        rows.append(dict(id=style.id, label=style.label, era=style.era, type=style.type,
                         tags=style.tags, status="OK", path=path))
    return rows


def select_style(styles, era="", building_type=""):
    """Choose the closest style by exact era/type, then tag matches."""
    candidates = [s for s in styles if s.get("status") == "OK"]
    if not candidates:
        return None
    if era:
        exact = [s for s in candidates if str(s.get("era", "")).startswith(str(era)[:4])]
        if exact:
            candidates = exact
    if building_type:
        typed = [s for s in candidates if building_type in (s.get("type", "") + " " + " ".join(s.get("tags", [])))]
        if typed:
            candidates = typed
    return candidates[0]
