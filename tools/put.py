# -*- coding: utf-8 -*-
"""
put.py - write a whole file from stdin (no quoting problems in PowerShell). Then syntax-check .py files.

PowerShell (single-quoted here-string = no escaping at all; '@ must be at the start of its own line):
    @'
    print("hello")
    '@ | python tools/put.py my_file.py

bash / Git Bash / WSL:
    python tools/put.py my_file.py <<'EOF'
    print("hello")
    EOF

Options: --append   add to the end of the file instead of replacing it
Output: "OK wrote <file> (<n> lines)" or "SYNTAX ERROR line N: ..." with the lines around it (file is still written).
Exit code: 0 ok, 1 syntax error.
"""
import os
import sys


def normalize(text):
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def syntax_report(path, text):
    """Return '' if ok, else a short ASCII report with context lines."""
    if not path.endswith(".py"):
        return ""
    try:
        compile(text, path, "exec")
        return ""
    except SyntaxError as e:
        lines = text.split("\n")
        n = e.lineno or 1
        out = [f"SYNTAX ERROR line {n}: {e.msg}"]
        for i in range(max(1, n - 3), min(len(lines), n + 2) + 1):
            mark = ">>" if i == n else "  "
            out.append(f"{mark}{i:5d}| {lines[i - 1]}")
        return "\n".join(out)


def read_stdin():
    data = sys.stdin.buffer.read()
    for enc in ("utf-8-sig", "utf-16", "cp949", "latin-1"):
        try:
            t = data.decode(enc)
            if enc == "utf-16" and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return t
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def safe_print(s):
    sys.stdout.write(s.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        safe_print(__doc__)
        sys.exit(2)
    path = args[0]
    text = normalize(read_stdin())
    if "--append" in sys.argv and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = normalize(f.read())
        text = old + text
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    rep = syntax_report(path, text)
    n = text.count("\n")
    if rep:
        safe_print(f"WROTE {path} ({n} lines) BUT:\n{rep}\nFix it with tools/edit.py.")
        sys.exit(1)
    safe_print(f"OK wrote {path} ({n} lines)")


if __name__ == "__main__":
    main()
