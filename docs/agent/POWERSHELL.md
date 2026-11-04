# PowerShell editing fallback

Prefer native Edit/apply_patch tools. Use this fallback only when they are unavailable or repeatedly fail. Do not use `python -c`, `Set-Content`, `Out-File`, `Add-Content`, `echo`, or shell redirection to write source.

Read a small range:

```powershell
python tools/show.py <file> 40 90
python tools/show.py <file> --find FLOORS
```

Use a single-quoted here-string. `@'` must end its line and `'@` must start at column zero. Nothing inside is interpolated.

```powershell
@'
=== SEARCH
FLOORS = 8
=== REPLACE
FLOORS = 15
'@ | python tools/edit.py <name>_cs2.py
```

`edit.py` writes nothing when the result is invalid Python. Copy SEARCH exactly from `show.py`, without line numbers. Multiple SEARCH/REPLACE pairs may follow in one input.

Create a file:

```powershell
@'
...file content...
'@ | python tools/put.py <file>
```

In bash/WSL, use a quoted heredoc:

```bash
python tools/edit.py <file> <<'EOF'
=== SEARCH
FLOORS = 8
=== REPLACE
FLOORS = 15
EOF
```

Keep code, YAML keys, asset names, and file names ASCII. If shell output is garbled, use readable numbers and English tool output; do not rewrite reference data to repair console encoding.
