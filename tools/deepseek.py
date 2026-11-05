"""DeepSeek task routing without storing or printing credentials."""
import argparse
import json
import os

POLICIES = {
    "data": dict(thinking=False, reasoning_effort=None,
                 instruction="Edit only the requested data fields; do not redesign the building."),
    "edit": dict(thinking=True, reasoning_effort="low",
                 instruction="Fix one reported error group and run the returned quick/visual command."),
    "geometry": dict(thinking=True, reasoning_effort="high",
                     instruction="Resolve wall/volume evidence before changing mass, floors, bays, or openings."),
    "vision": dict(thinking=True, reasoning_effort="high",
                   instruction="Inspect one wall or detail crop; record source, confidence, and occlusion."),
    "review": dict(thinking=True, reasoning_effort="high",
                  instruction="Review every returned artifact; never mark an unseen image as PASS."),
}


def policy(task):
    result = dict(status="PASS", model="deepseek-flash", task=task, **POLICIES[task])
    result["tool_loop"] = "Preserve reasoning_content and tool_call IDs when using a custom tool-calling client."
    result["privacy"] = "Use explicit wall/detail crops; external image upload is never automatic in this kit."
    if task == "vision":
        result["image_detail"] = "original"
        result["contact_sheet_usage"] = "classification only; use wall/detail crops for measurement"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=sorted(POLICIES), required=True)
    parser.add_argument("--check-credentials", action="store_true")
    args = parser.parse_args()
    result = policy(args.task)
    if args.check_credentials:
        result["credential_present"] = bool(os.environ.get("DEEPSEEK_API_KEY"))
        result["credential_note"] = "Presence only; the key is never read into the result."
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
