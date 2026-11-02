# -*- coding: utf-8 -*-
"""
edit.py - change part of a file with SEARCH/REPLACE blocks read from stdin (no quoting problems).

PowerShell:
    @'
    <<<<<<< SEARCH
    FLOORS = 8
    =======
    FLOORS = 15
    >>>>>>> REPLACE
    '@ | python tools/edit.py my_building_cs2.py

bash / Git Bash / WSL:
    python tools/edit.py my_building_cs2.py <<'EOF'
    <<<<<<< SEARCH
    FLOORS = 8
    =======
    FLOORS = 15
    >>>>>>> REPLACE
    EOF

Rules
- SEARCH text must match the file exactly once (copy it from `python tools/show.py <file> <from> <to>`).
  Trailing spaces and line endings are ignored. Leading indentation must match.
- Several blocks in one call are applied in order. Empty REPLACE deletes. To insert, SEARCH an anchor line and
  put the anchor line plus the new lines in REPLACE.
- For .py files the result is syntax-checked. If it is broken, NOTHING is written and the error is shown.
Exit code: 0 ok, 1 not applied.
"""
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from put import normalize, read_stdin, safe_print, syntax_report  # noqa: E402

BLOCK = re.compile(r"^<{5,9} ?SEARCH[^\n]*\n(.*?)^={5,9}[^\n]*\n(.*?)^>{5,9} ?REPLACE[^\n]*$", re.S | re.M)


def strip_trailing(s):
    return "\n".join(l.rstrip() for l in s.split("\n"))


def find(text, search):
    """Return (start, end) of the unique match, or an error string."""
    n = text.count(search)
    if n == 1:
        i = text.index(search)
        return i, i + len(search)
    if n > 1:
        return f"SEARCH matches {n} places - add more lines around it to make it unique"
    # trailing-space tolerant match on line level
    tl = text.split("\n")
    sl = search.rstrip("\n").split("\n")
    tls = [l.rstrip() for l in tl]
    sls = [l.rstrip() for l in sl]
    hits = [i for i in range(len(tls) - len(sls) + 1) if tls[i:i + len(sls)] == sls]
    if len(hits) == 1:
        a = sum(len(l) + 1 for l in tl[:hits[0]])
        b = a + sum(len(l) + 1 for l in tl[hits[0]:hits[0] + len(sl)])
        return a, b
    if len(hits) > 1:
        return f"SEARCH matches {len(hits)} places - add more lines around it to make it unique"
    # help: closest line of the first search line
    first = next((l for l in sls if l.strip()), "")
    close = difflib.get_close_matches(first, tls, n=3, cutoff=0.5)
    msg = "SEARCH text not found."
    if close:
        lines = [f"  line {tls.index(c) + 1}: {c}" for c in close]
        msg += " Closest lines in the file:\n" + "\n".join(lines) + "\nCopy the exact text with tools/show.py and retry."
    return msg


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        safe_print(__doc__)
        sys.exit(2)
    path = args[0]
    if not os.path.exists(path):
        safe_print(f"NOT APPLIED: file not found: {path} (create it with tools/put.py)")
        sys.exit(1)
    with open(path, encoding="utf-8-sig") as f:
        text = normalize(f.read())
    raw = normalize(read_stdin())
    blocks = BLOCK.findall(raw)
    if not blocks:
        safe_print("NOT APPLIED: no blocks found. Use exactly:\n<<<<<<< SEARCH\nold lines\n=======\nnew lines\n>>>>>>> REPLACE")
        sys.exit(1)
    new = text
    num = re.compile(r"^ ?>?>? *\d+\| ?")

    def unnumber(t):
        """Remove 'NNN| ' prefixes copied from show.py output (only if every non-empty line has one)."""
        ls = t.split("\n")
        body = [l for l in ls if l.strip()]
        if body and all(num.match(l) for l in body):
            return "\n".join(num.sub("", l, count=1) for l in ls)
        return t
    blocks = [(unnumber(a), unnumber(b)) for a, b in blocks]
    for k, (search, replace) in enumerate(blocks, 1):
        if not search.strip():
            safe_print(f"NOT APPLIED: block {k} has an empty SEARCH")
            sys.exit(1)
        r = find(new, search)
        if isinstance(r, str):
            safe_print(f"NOT APPLIED: block {k}: {r}")
            sys.exit(1)
        a, b = r
        rep = replace
        if new[a:b].endswith("\n") and rep and not rep.endswith("\n"):
            rep += "\n"
        new = new[:a] + rep + new[b:]
    rep = syntax_report(path, new)
    if rep:
        safe_print(f"NOT APPLIED (file unchanged) - the result would be broken:\n{rep}")
        sys.exit(1)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    safe_print(f"OK {len(blocks)} block(s) applied to {path} ({new.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
