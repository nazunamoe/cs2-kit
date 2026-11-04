import json
import os
import sys

payload = json.load(sys.stdin)
if payload.get("stop_hook_active"):
    print("{}")
    raise SystemExit(0)

kit = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
current_path = os.path.join(kit, "projects", ".current")
try:
    with open(current_path, encoding="utf-8") as f:
        project = f.read().strip()
    with open(os.path.join(kit, "projects", project, "work", "agent_state.json"), encoding="utf-8") as f:
        state = json.load(f)
except (OSError, ValueError):
    print("{}")
    raise SystemExit(0)

stage = state.get("current_stage", "")
gate = state.get("last_gate") or {}
final_stage = stage.startswith(("final:", "fix:")) or (stage.startswith("review:") and gate.get("mode") == "final")
if final_stage and gate.get("status") != "PASS":
    next_action = state.get("next_action") or {}
    reason = "Final gate is %s. Next action: %s (%s)" % (
        gate.get("status", "NOT_CHECKED"), next_action.get("command"), next_action.get("reason", "inspect state"))
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
else:
    print("{}")
