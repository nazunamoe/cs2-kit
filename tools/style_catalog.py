# -*- coding: utf-8 -*-
"""List and validate reusable facade styles.

  python tools/style_catalog.py --json
  python tools/style_catalog.py --validate
  python tools/style_catalog.py --style apartment_2020_lightstone

Styles live in templates/styles/*.yaml and are consumed by
templates/facade_style.py.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from proj import KIT  # noqa: E402
sys.path.insert(0, KIT)
from templates.facade_style import list_styles, load_style  # noqa: E402

STYLE_DIR = os.path.join(KIT, "templates", "styles")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--style", default="")
    a = ap.parse_args()
    rows = list_styles(STYLE_DIR)
    errors = [r for r in rows if r.get("status") != "OK"]
    if a.style:
        match = next((r for r in rows if r.get("id") == a.style), None)
        if not match or match.get("status") != "OK":
            print(json.dumps(dict(status="FAIL", error=f"style not found: {a.style}",
                                  styles=[r.get("id") for r in rows]), ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(load_style(match["path"]).to_dict(), ensure_ascii=False, indent=1))
        return
    if a.json:
        print(json.dumps(dict(status="PASS" if not errors else "FAIL", styles=rows,
                              errors=[dict(id=r.get("id"), error=r.get("error")) for r in errors]),
                         ensure_ascii=False))
    else:
        for r in rows:
            if r.get("status") == "OK":
                print(f"{r['id']:32s} {r['era']:8s} {r['type']:18s} {', '.join(r.get('tags', []))}")
            else:
                print(f"{r.get('id', '?'):32s} ERROR {r.get('error')}")
    if a.validate and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
