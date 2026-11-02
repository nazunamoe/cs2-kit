# -*- coding: utf-8 -*-
"""
show.py - print a file with line numbers (ASCII-safe: non-ASCII becomes \\uXXXX, so it never looks broken).

    python tools/show.py my_building_cs2.py            first 150 lines (use ranges, keep output small)
    python tools/show.py my_building_cs2.py 120 180    lines 120..180
    python tools/show.py my_building_cs2.py --find WindowSet    lines containing the text
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from put import safe_print  # noqa: E402


def main():
    a = sys.argv[1:]
    if not a:
        safe_print(__doc__)
        sys.exit(2)
    path = a[0]
    with open(path, "rb") as f:
        data = f.read()
    for enc in ("utf-8-sig", "cp949", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = text.replace("\r\n", "\n").split("\n")
    if "--find" in a:
        key = a[a.index("--find") + 1]
        for i, l in enumerate(lines, 1):
            if key in l:
                safe_print(f"{i:5d}| {l}")
        return
    s = int(a[1]) if len(a) > 1 else 1
    e = int(a[2]) if len(a) > 2 else min(len(lines), s + 149)
    for i in range(max(1, s), min(len(lines), e) + 1):
        safe_print(f"{i:5d}| {lines[i - 1]}")
    if e < len(lines):
        safe_print(f"... ({len(lines)} lines total; next: python tools/show.py {path} {e + 1} {e + 150})")


if __name__ == "__main__":
    main()
