# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
import yaml

def update_yaml(path, key, value):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    
    keys = key.split(".")
    curr = data
    for k in keys[:-1]:
        curr = curr.setdefault(k, {})
    
    try:
        if "." in value:
            val = float(value)
        else:
            val = int(value)
    except ValueError:
        val = value

    curr[keys[-1]] = val

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return val

def main():
    ap = argparse.ArgumentParser(description="Update building spec YAML values")
    ap.add_argument("--project", required=True)
    ap.add_argument("--spec", required=True, help="building_spec_<Name>.yaml")
    ap.add_argument("--key", required=True, help="YAML key to update (supports dot notation)")
    ap.add_argument("--value", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project_root = os.path.join(os.getcwd(), "projects", args.project)
    spec_path = os.path.join(project_root, args.spec)
    
    if not os.path.isfile(spec_path):
        print(f"Spec file not found: {spec_path}")
        sys.exit(1)

    new_val = update_yaml(spec_path, args.key, args.value)
    
    result = {"status": "UPDATED", "project": args.project, "spec": args.spec, "key": args.key, "value": new_val}
    if args.json:
        print(json.dumps(result))
    else:
        print(f"Updated {args.spec}: {args.key} -> {new_val}")

if __name__ == "__main__":
    main()
