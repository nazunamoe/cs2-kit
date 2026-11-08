# -*- coding: utf-8 -*-
"""Portable agent entry point. Run from the kit root with an explicit --project."""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import subprocess
import sys

EXPLICIT_PROJECT = any(a == "--project" or a.startswith("--project=") for a in sys.argv[1:])
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proj import ROOT, KIT, NAME  # noqa: E402

PY = sys.executable
STATE = os.path.join(ROOT, "work", "agent_state.json")
OBSERVATIONS = os.path.join(ROOT, "work", "observations.json")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {} if default is None else default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def require_project():
    if not NAME or not EXPLICIT_PROJECT:
        raise SystemExit("agent.py requires --project <name>; ambient projects/.current is not accepted")


def command(mode, generator, extra=""):
    return f"python tools/agent.py cycle --project {NAME} --generator {generator} --mode {mode} --json{extra}"


@contextlib.contextmanager
def project_lock():
    path = os.path.join(ROOT, "work", "agent.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(f"another agent run is active in {NAME}: {path}")
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def review_command(gate):
    artifacts = []
    preview = (gate.get("artifacts") or {}).get("preview")
    if preview:
        artifacts.append(preview)
    if (gate.get("photo") or {}).get("checked"):
        folder = os.path.join(ROOT, "previews", "photo_check")
        if os.path.isdir(folder):
            artifacts += [os.path.join("previews", "photo_check", f) for f in sorted(os.listdir(folder)) if f.endswith(".png")]
    for line in (gate.get("tiles") or {}).get("detail", []):
        parts = line.split()
        if len(parts) > 1:
            artifacts.append(os.path.join("previews", "tiles", parts[1] + "_map.png"))
    artifacts = list(dict.fromkeys(path.replace(os.sep, "/") for path in artifacts))
    cmd = f"python tools/agent.py review --project {NAME} --status PASS --note \"reviewed current artifacts\""
    return cmd + "".join(f" --artifact \"{path}\"" for path in artifacts)


def next_for(status, generator, mode="quick"):
    if status == "PASS":
        return {"command": None, "reason": "all requested checks passed"}
    if status == "INCOMPLETE":
        return {"command": command("final", generator), "reason": "run the missing final checks; FBX and LOD need Blender or the bpy module"}
    if status == "FAIL":
        return {"command": command(mode, generator), "reason": f"fix the reported errors, then rerun the {mode} check"}
    return {"command": f"python tools/agent.py doctor --project {NAME} --json", "reason": "inspect the project state"}


def update_status(state):
    gate = state.get("last_gate") or {}
    next_action = state.get("next_action") or {}
    lines = [
        "# STATUS.md - agent handoff",
        "",
        "## Current stage",
        state.get("current_stage", "not started"),
        "",
        "## Generator",
        state.get("generator", "not selected"),
        "",
        "## Last verification",
        gate.get("status", "NOT_CHECKED"),
        "",
        "## Next action",
        next_action.get("command") or next_action.get("reason", "inspect TASK.md"),
        "",
        "## Notes",
        "Machine state: work/agent_state.json. Photo observations: work/observations.json.",
        "Estimated values remain in building_spec_*.yaml with # estimated.",
        "",
    ]
    with open(os.path.join(ROOT, "STATUS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_state(state):
    state["project"] = NAME
    state["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    write_json(STATE, state)
    update_status(state)


def emit(data, as_json, code=0):
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(f"AGENT {data.get('status', 'OK')} project={NAME}")
        if data.get("next_action"):
            print("NEXT " + json.dumps(data["next_action"], ensure_ascii=False))
        for key in ("state", "gate", "contact_sheet", "observations", "log"):
            if data.get(key):
                print(f"{key.upper()} {data[key]}")
    raise SystemExit(code)


def normalized_cycle(args):
    require_project()
    generator = os.path.abspath(args.generator)
    if not os.path.isfile(generator):
        raise SystemExit(f"generator not found: {args.generator}")
    with project_lock():
        cmd = [PY, os.path.join(KIT, "tools", "cycle.py"), generator, "--mode", args.mode, "--json"]
        if args.label:
            cmd += ["--label", args.label]
        code, log = run(cmd)
        os.makedirs(os.path.join(ROOT, "work", "logs"), exist_ok=True)
        log_path = os.path.join(ROOT, "work", "logs", "last_cycle.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(log)
        gate = None
        gate_path = None
        for line in log.splitlines():
            if line.startswith("[json] "):
                gate_path = line[7:].strip()
                gate = read_json(os.path.join(ROOT, gate_path), None)
        state = read_json(STATE)
        gen_hash = digest(generator)
        if state.get("generator_hash") != gen_hash:
            state["visual_review"] = "NOT_CHECKED"
        if gate is None:
            gate = {
                "status": "FAIL", "project": NAME, "generator": os.path.basename(generator), "mode": args.mode,
                "checks": {"build": "FAIL"}, "errors": [{"msg": "cycle failed before gate.json; see the raw log"}],
                "next_action": next_for("FAIL", os.path.basename(generator)),
            }
        preview_rel = (gate.get("artifacts") or {}).get("preview")
        preview_path = os.path.join(ROOT, preview_rel) if preview_rel else None
        preview_hash = digest(preview_path) if preview_path and os.path.isfile(preview_path) else None
        if args.mode != "quick" and state.get("reviewed_preview_hash") != preview_hash:
            state["visual_review"] = "NOT_CHECKED"
        status = gate.get("status", "FAIL")
        mismatch_keys = sorted(line.split(":", 1)[0] for line in (gate.get("photo") or {}).get("lines", [])
                               if line.startswith("PHOTO_MISMATCH"))
        signature = "\n".join(mismatch_keys)
        previous_signature = (state.get("mismatch_attempts") or {}).get("signature")
        attempts = state.get("mismatch_attempts") or {}
        if signature:
            attempts = {"signature": signature, "count": (attempts.get("count", 0) + 1) if signature == previous_signature else 1}
        else:
            attempts = {}
        human_pending = bool(signature and attempts.get("count", 0) >= 3 and status == "FAIL")
        visual_pending = status == "PASS" and args.mode != "quick" and state.get("visual_review") != "PASS"
        if human_pending:
            status = "NEEDS_HUMAN_REVIEW"
            gate["status"] = status
            gate.setdefault("checks", {})["photo_review"] = "NEEDS_HUMAN_REVIEW"
        elif visual_pending:
            status = "INCOMPLETE"
            gate["status"] = status
            gate.setdefault("checks", {})["visual_review"] = "NOT_CHECKED"
            gate.setdefault("gate", {}).setdefault("incomplete", []).append("visual_review=NOT_CHECKED")
        if (human_pending or visual_pending) and gate_path:
            write_json(os.path.join(ROOT, gate_path), gate)
        next_action = next_for(status, os.path.basename(generator), args.mode)
        if human_pending:
            next_action = {"command": None, "reason": "same photo mismatch reached 3 attempts; inspect the photo_refs and comparison sheets manually"}
        elif visual_pending:
            next_action = {"command": review_command(gate),
                           "reason": "inspect the listed current artifacts, then record the review"}
        state.update({
            "current_stage": f"{args.mode}:{status}", "generator": os.path.relpath(generator, ROOT),
            "generator_hash": gen_hash, "current_preview_hash": preview_hash,
            "last_gate": gate, "mismatch_attempts": attempts, "next_action": next_action,
        })
        save_state(state)
        result = {
            "status": status, "project": NAME, "asset": gate.get("asset"), "checks": gate.get("checks", {}),
            "errors": gate.get("errors", []), "warnings": (gate.get("check") or {}).get("warnings", []),
            "photo_mismatch": (gate.get("photo") or {}).get("mismatch"),
            "action_tags": (gate.get("agent") or {}).get("action_tags", []), "next_action": state["next_action"],
            "gate": gate_path, "state": os.path.relpath(STATE, ROOT), "log": os.path.relpath(log_path, ROOT),
        }
        if args.brief:
            result = {"status": status, "project": NAME, "mode": args.mode, "next_action": state["next_action"]}
            if status != "PASS":
                result.update(checks=gate.get("checks", {}), gate=gate_path,
                              photo_mismatch=(gate.get("photo") or {}).get("mismatch"))
                errors = gate.get("errors", [])
                if errors:
                    first = errors[0]
                    result["error"] = {"key": first.get("key"), "message": first.get("msg"),
                                       "example": (first.get("examples") or [None])[0]}
        emit(result, args.json, 0 if status == "PASS" else 1 if status == "FAIL" else 2)


def deepseek_policy(args):
    require_project()
    cmd = [PY, os.path.join(KIT, "tools", "deepseek.py"), "--task", args.task]
    if args.check_credentials:
        cmd.append("--check-credentials")
    code, log = run(cmd)
    result = json.loads(log.strip().splitlines()[-1])
    result["next_action"] = {"command": None, "reason": "apply this policy to the current task"}
    emit(result, args.json, code)


def vision(args):
    require_project()
    cmd = [PY, os.path.join(KIT, "tools", "vision_prepare.py"), args.photo]
    for name, value in (("--box", args.box), ("--wall-id", args.wall_id), ("--out", args.out)):
        if value:
            cmd += [name, value]
    if args.max_side != 1300:
        cmd += ["--max-side", str(args.max_side)]
    for region in args.redact:
        cmd += ["--redact", region]
    code, log = run(cmd)
    result = json.loads(log.strip().splitlines()[-1])
    result["next_action"] = {"command": None, "reason": "inspect the derived crop before any explicit external upload"}
    emit(result, args.json, code)


def glb_mass(args):
    require_project()
    glb_args = args.glb_args[1:] if args.glb_args[:1] == ["--"] else args.glb_args
    if not any(value.lower().endswith((".glb", ".gltf")) for value in glb_args):
        photos_dir = os.path.join(ROOT, "photos")
        found = []
        for base, _, names in os.walk(photos_dir):
            found.extend(os.path.join(base, name) for name in sorted(names) if name.lower().endswith((".glb", ".gltf")))
        if len(found) != 1:
            raise SystemExit("pass one GLB path after --, or keep exactly one GLB/GLTF in photos/")
        glb_args = [found[0]] + glb_args
    code, log = run([PY, os.path.join(KIT, "tools", "glb_shape.py")] + glb_args)
    try:
        result = json.loads(log.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {"status": "FAIL", "errors": [log.strip() or "GLB mass reconstruction failed"]}
    result.setdefault("next_action", {"command": None, "reason": "inspect the reconstructed mass before facade work"})
    emit(result, args.json, code)


def require_final(args):
    require_project()
    state = read_json(STATE, None)
    if not state:
        emit({"status": "NOT_CHECKED", "next_action": {"command": f"python tools/agent.py doctor --project {NAME} --json",
                                                       "reason": "no saved final gate"}}, args.json, 2)
    gate = state.get("last_gate") or {}
    complete = (gate.get("mode") == "final" and gate.get("status") == "PASS"
                and state.get("visual_review") == "PASS"
                and (gate.get("checks") or {}).get("fbx") == "PASS")
    status = "PASS" if complete else "FAIL" if gate.get("status") == "FAIL" else "INCOMPLETE"
    emit({"status": status, "mode": gate.get("mode"), "visual_review": state.get("visual_review"),
          "checks": gate.get("checks", {}),
          "next_action": None if complete else state.get("next_action")}, args.json,
         0 if complete else 1 if status == "FAIL" else 2)


def doctor(args):
    require_project()
    import importlib.util
    from run_blender import find_blender, find_bpy
    bpy = find_bpy(verbose=False)
    blender = None if bpy else find_blender(verbose=False)
    generators = sorted(f for f in os.listdir(ROOT) if f.endswith("_cs2.py"))
    scans = []
    for base, _, names in os.walk(os.path.join(ROOT, "photos")):
        scans.extend(os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, "/")
                     for f in sorted(names) if f.lower().endswith((".glb", ".gltf")))
    state = read_json(STATE)
    next_action = state.get("next_action") or {"command": None, "reason": "select a generator explicitly"}
    if scans and not state:
        next_action = {"command": f"python tools/agent.py glb-mass --project {NAME} --json -- {scans[0]} --list",
                       "reason": "GLB found: select building meshes and reconstruct simplified mass volumes before hand-drawing the mass"}
    result = {
        "status": "OK", "project": NAME, "project_root": ROOT,
        "generators": generators, "glb_files": scans,
        "dependencies": {n: importlib.util.find_spec(n) is not None for n in ("numpy", "PIL")},
        "blender": blender, "bpy": bpy, "fbx_engine": "bpy" if bpy else ("blender" if blender else None),
        "photo_refs": os.path.isfile(os.path.join(ROOT, "photo_refs.json")),
        "state": os.path.relpath(STATE, ROOT) if state else None,
        "current_stage": state.get("current_stage"), "visual_review": state.get("visual_review", "NOT_CHECKED"),
        "next_action": next_action,
    }
    emit(result, args.json)


def resume(args):
    require_project()
    state = read_json(STATE, None)
    if not state:
        emit({"status": "NOT_CHECKED", "next_action": {"command": f"python tools/agent.py doctor --project {NAME} --json",
                                                       "reason": "no saved state"}}, args.json)
    emit({"status": (state.get("last_gate") or {}).get("status", "NOT_CHECKED"),
          "current_stage": state.get("current_stage"), "generator": state.get("generator"),
          "visual_review": state.get("visual_review", "NOT_CHECKED"),
          "mismatch_attempts": state.get("mismatch_attempts", {}), "next_action": state.get("next_action"),
          "state": os.path.relpath(STATE, ROOT)}, args.json)


def photos(args):
    require_project()
    if args.page < 0 or not 1 <= args.page_size <= 100:
        raise SystemExit("photos requires --page >= 0 and 1 <= --page-size <= 100")
    from PIL import Image, ImageDraw
    source = os.path.join(ROOT, "photos")
    files = []
    for base, _, names in os.walk(source):
        for name in sorted(names):
            if os.path.splitext(name)[1].lower() in (".jpg", ".jpeg", ".png", ".webp"):
                files.append(os.path.join(base, name))
    manifest = os.path.join(ROOT, "work", "photo_manifest.json")
    previous = {r["file"]: r for r in read_json(manifest).get("photos", [])}
    records = []
    seen = {}
    for path in files:
        rel = os.path.relpath(path, ROOT)
        stat = os.stat(path)
        old = previous.get(rel, {})
        unchanged = old.get("mtime_ns") == stat.st_mtime_ns and old.get("bytes") == stat.st_size
        if unchanged:
            h = old["sha256"]
            size = old.get("size")
        else:
            h = digest(path)
        if not unchanged or not size:
            with Image.open(path) as im:
                size = im.size
        records.append({"file": rel, "sha256": h, "size": size, "mtime_ns": stat.st_mtime_ns,
                        "bytes": stat.st_size, "duplicate_of": seen.get(h)})
        seen.setdefault(h, rel)
    observations = read_json(OBSERVATIONS)
    for rec in records:
        rec["observed"] = rec["sha256"] in observations
    write_json(manifest, {"photos": records})
    start = args.page * args.page_size
    selected = records[start:start + args.page_size]
    thumbs = []
    for rec in selected:
        with Image.open(os.path.join(ROOT, rec["file"])) as im:
            im = im.convert("RGB")
            im.thumbnail((320, 220))
            tile = Image.new("RGB", (340, 260), "white")
            tile.paste(im, ((340 - im.width) // 2, 22))
            ImageDraw.Draw(tile).text((5, 5), rec["file"][:48], fill="black")
            thumbs.append(tile)
    if thumbs:
        cols = min(3, len(thumbs))
        sheet = Image.new("RGB", (cols * 340, ((len(thumbs) + cols - 1) // cols) * 260), "white")
        for i, tile in enumerate(thumbs):
            sheet.paste(tile, ((i % cols) * 340, (i // cols) * 260))
        out = os.path.join(ROOT, "previews", "agent_photos")
        os.makedirs(out, exist_ok=True)
        sheet_path = os.path.join(out, f"contact_sheet_{args.page:03d}.jpg")
        sheet.save(sheet_path, quality=88)
    else:
        sheet_path = None
    unobserved = [r["file"] for r in records if not r["observed"] and not r["duplicate_of"]]
    unobserved_page = [r["file"] for r in selected if not r["observed"] and not r["duplicate_of"]]
    emit({"status": "OK", "contact_sheet": os.path.relpath(sheet_path, ROOT) if sheet_path else None,
          "page": args.page, "pages": (len(records) + args.page_size - 1) // args.page_size,
          "unobserved_count": len(unobserved), "unobserved": unobserved_page, "manifest": os.path.relpath(manifest, ROOT),
          "next_action": {"command": None, "reason": "inspect one contact-sheet page, then crop only ambiguous regions"}}, args.json)


def evidence(args):
    require_project()
    evidence_args = args.evidence_args[1:] if args.evidence_args[:1] == ["--"] else args.evidence_args
    if not evidence_args:
        raise SystemExit("use agent.py evidence --project P -- <photo|feature|validate options>")
    code, log = run([PY, os.path.join(KIT, "tools", "evidence.py")] + evidence_args)
    try:
        result = json.loads(log.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {"status": "FAIL", "errors": [log.strip() or "evidence tool failed"]}
    result.setdefault("next_action", {"command": None, "reason": "record observations by wall and confidence"})
    emit(result, args.json, code)


def observe(args):
    require_project()
    path = os.path.abspath(args.photo)
    if not os.path.isfile(path):
        raise SystemExit(f"photo not found: {args.photo}")
    records = read_json(OBSERVATIONS)
    records[digest(path)] = {"file": os.path.relpath(path, ROOT), "side": args.side, "note": args.note,
                             "observed_at": datetime.datetime.now().isoformat(timespec="seconds")}
    write_json(OBSERVATIONS, records)
    emit({"status": "OK", "observations": os.path.relpath(OBSERVATIONS, ROOT),
          "next_action": {"command": None, "reason": "unchanged observed photos do not need to be read again"}}, args.json)


def review(args):
    require_project()
    state = read_json(STATE)
    gate = state.get("last_gate")
    if not gate:
        raise SystemExit("run a visual or final cycle before review")
    artifacts = []
    for path in args.artifact:
        absolute = os.path.abspath(path)
        if not os.path.isfile(absolute):
            raise SystemExit(f"review artifact not found: {path}")
        artifacts.append(os.path.relpath(absolute, ROOT).replace(os.sep, "/"))
    review_status = args.status
    if args.status == "PASS":
        expected_preview = ((gate.get("artifacts") or {}).get("preview") or "").replace(os.sep, "/")
        missing = []
        if not expected_preview or expected_preview not in artifacts:
            missing.append("current preview")
        if (gate.get("photo") or {}).get("checked") and not any(p.startswith("previews/photo_check/") for p in artifacts):
            missing.append("photo sheet")
        if (gate.get("tiles") or {}).get("checked") and not any(p.startswith("previews/tiles/") for p in artifacts):
            missing.append("tile map")
        if missing:
            review_status = "PARTIAL"
    state["visual_review"] = review_status
    state["visual_review_note"] = args.note
    state["visual_review_artifacts"] = [{"file": p, "sha256": digest(os.path.join(ROOT, p))} for p in artifacts]
    if review_status == "PASS":
        state["reviewed_preview_hash"] = state.get("current_preview_hash")
    gate.setdefault("checks", {})["visual_review"] = review_status
    other_failure = any(value == "FAIL" for key, value in gate.get("checks", {}).items() if key != "visual_review")
    other_missing = gate.get("mode") == "final" and any(value in ("NOT_CHECKED", "NOT_CREATED")
                        for key, value in gate.get("checks", {}).items() if key != "visual_review")
    gate["status"] = ("FAIL" if args.status == "FAIL" or other_failure else "INCOMPLETE"
                      if other_missing or review_status != "PASS" else "PASS")
    incomplete = gate.setdefault("gate", {}).setdefault("incomplete", [])
    incomplete = [item for item in incomplete if not item.startswith("visual_review=")]
    if review_status != "PASS":
        incomplete.append(f"visual_review={review_status}")
    gate["gate"]["incomplete"] = incomplete
    state["last_gate"] = gate
    state["current_stage"] = f"review:{gate['status']}"
    if review_status == "PARTIAL":
        state["next_action"] = {"command": review_command(gate), "reason": "review all required current artifacts"}
    elif review_status == "NEEDS_HUMAN_REVIEW":
        state["next_action"] = {"command": None, "reason": "visual input unavailable; a human must inspect the current artifacts"}
    else:
        state["next_action"] = next_for(gate["status"], gate.get("generator", ""), gate.get("mode", "quick"))
    save_state(state)
    gate_path = os.path.join(ROOT, "output", gate.get("asset", ""), "_check", "gate.json")
    if gate.get("asset") and os.path.isfile(gate_path):
        write_json(gate_path, gate)
    emit({"status": gate["status"], "visual_review": review_status, "checks": gate.get("checks", {}),
          "next_action": state["next_action"]}, args.json,
         0 if gate["status"] == "PASS" else 1 if gate["status"] == "FAIL" else 2)


def fix(args):
    require_project()
    generator = os.path.abspath(args.generator)
    if not os.path.isfile(generator):
        raise SystemExit(f"generator not found: {args.generator}")
    with project_lock():
        state = read_json(STATE)
        if not args.finish:
            asset = args.asset or (state.get("last_gate") or {}).get("asset")
            if not asset:
                raise SystemExit("fix begin needs --asset when no previous gate exists")
            code, log = run([PY, os.path.join(KIT, "tools", "compare.py"), "snap", os.path.join(ROOT, "output", asset)])
            if code != 0:
                raise SystemExit(log.strip())
            snap_line = next((l for l in log.splitlines() if l.startswith("[snap] ")), "")
            snapshot = snap_line[7:].strip()
            if not snapshot:
                raise SystemExit("compare.py did not return a snapshot")
            state["fix"] = {"request": args.request, "snapshot": snapshot, "asset": asset, "box": args.box,
                            "generator": os.path.relpath(generator, ROOT), "before_hash": digest(generator)}
            state["current_stage"] = "fix:edit_pending"
            finish_cmd = f"python tools/agent.py fix --project {NAME} --generator {os.path.basename(generator)} --finish --json"
            state["next_action"] = {"command": finish_cmd, "reason": "edit only the requested scope, then run the command"}
            save_state(state)
            emit({"status": "EDIT_PENDING", "snapshot": snapshot, "next_action": state["next_action"]}, args.json)
        fix_state = state.get("fix")
        if not fix_state:
            raise SystemExit("no pending fix; run fix without --finish first")
        code, log = run([PY, os.path.join(KIT, "tools", "cycle.py"), generator, "--mode", "final", "--json", "--label", "fix"])
        gate = None
        for line in log.splitlines():
            if line.startswith("[json] "):
                gate = read_json(os.path.join(ROOT, line[7:].strip()), None)
        can_compare = bool(gate and (gate.get("checks") or {}).get("build") == "PASS"
                           and gate.get("asset") == fix_state["asset"])
        if can_compare:
            diff_cmd = [PY, os.path.join(KIT, "tools", "compare.py"), "diff", fix_state["snapshot"],
                        os.path.join(ROOT, "output", fix_state["asset"])]
            if fix_state.get("box"):
                diff_cmd.append("--box=" + fix_state["box"])
            diff_code, diff_log = run(diff_cmd)
            compare_status = "FAIL" if diff_code else "PASS"
        else:
            diff_code, diff_log = 0, "NOT_CHECKED: current build did not produce the expected asset"
            compare_status = "NOT_CHECKED"
        status = "FAIL" if code == 1 or diff_code or not gate or (gate.get("checks") or {}).get("build") == "FAIL" else "INCOMPLETE" if code == 2 else "PASS"
        gen_hash = digest(generator)
        preview_rel = (gate.get("artifacts") or {}).get("preview") if gate else None
        preview_path = os.path.join(ROOT, preview_rel) if preview_rel else None
        preview_hash = digest(preview_path) if preview_path and os.path.isfile(preview_path) else None
        if state.get("generator_hash") != gen_hash or state.get("reviewed_preview_hash") != preview_hash:
            state["visual_review"] = "NOT_CHECKED"
        visual_pending = status == "PASS" and state.get("visual_review") != "PASS"
        if visual_pending:
            status = "INCOMPLETE"
            if gate:
                gate["status"] = status
                gate.setdefault("checks", {})["visual_review"] = "NOT_CHECKED"
        state["current_stage"] = f"fix:{status}"
        state["generator"] = os.path.relpath(generator, ROOT)
        state["generator_hash"] = gen_hash
        state["current_preview_hash"] = preview_hash
        state["last_gate"] = gate or state.get("last_gate")
        state["next_action"] = next_for(status, os.path.basename(generator), "final")
        if visual_pending:
            state["next_action"] = {"command": review_command(gate),
                                    "reason": "inspect the listed fix artifacts and compare result, then record the review"}
        state.pop("fix", None)
        save_state(state)
        emit({"status": status, "checks": (gate or {}).get("checks", {}),
              "compare": {"status": compare_status, "output": diff_log.splitlines()[-30:]},
              "cycle_output": log.splitlines()[-30:], "next_action": state["next_action"]}, args.json,
             0 if status == "PASS" else 1 if status == "FAIL" else 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, epilog="All commands require --project <name>. Add --json for one machine-readable result.")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("doctor", "resume", "require-final"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
        p.set_defaults(fn=globals()[name.replace("-", "_")])
    p = sub.add_parser("deepseek-policy")
    p.add_argument("--json", action="store_true")
    p.add_argument("--task", choices=("data", "edit", "geometry", "vision", "review"), required=True)
    p.add_argument("--check-credentials", action="store_true")
    p.set_defaults(fn=deepseek_policy)
    p = sub.add_parser("vision")
    p.add_argument("--json", action="store_true")
    p.add_argument("--photo", required=True)
    p.add_argument("--box", default="")
    p.add_argument("--redact", action="append", default=[])
    p.add_argument("--wall-id", default="")
    p.add_argument("--max-side", type=int, default=1300)
    p.add_argument("--out", default="")
    p.set_defaults(fn=vision)
    p = sub.add_parser("glb-mass")
    p.add_argument("--json", action="store_true")
    p.add_argument("glb_args", nargs=argparse.REMAINDER)
    p.set_defaults(fn=glb_mass)
    p = sub.add_parser("photos")
    p.add_argument("--json", action="store_true")
    p.add_argument("--page", type=int, default=0)
    p.add_argument("--page-size", type=int, default=16)
    p.set_defaults(fn=photos)
    p = sub.add_parser("evidence")
    p.add_argument("--json", action="store_true")
    p.add_argument("evidence_args", nargs=argparse.REMAINDER)
    p.set_defaults(fn=evidence)
    p = sub.add_parser("observe")
    p.add_argument("--json", action="store_true")
    p.add_argument("--photo", required=True)
    p.add_argument("--side", default="")
    p.add_argument("--note", required=True)
    p.set_defaults(fn=observe)
    p = sub.add_parser("review")
    p.add_argument("--json", action="store_true")
    p.add_argument("--status", choices=("PASS", "FAIL", "NEEDS_HUMAN_REVIEW"), required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--artifact", action="append", default=[])
    p.set_defaults(fn=review)
    p = sub.add_parser("cycle")
    p.add_argument("--json", action="store_true")
    p.add_argument("--brief", action="store_true")
    p.add_argument("--generator", required=True)
    p.add_argument("--mode", choices=("quick", "visual", "final"), default="quick")
    p.add_argument("--label", default="")
    p.set_defaults(fn=normalized_cycle)
    p = sub.add_parser("fix")
    p.add_argument("--json", action="store_true")
    p.add_argument("--generator", required=True)
    p.add_argument("--request", default="")
    p.add_argument("--asset", default="")
    p.add_argument("--box", default="")
    p.add_argument("--finish", action="store_true")
    p.set_defaults(fn=fix)
    args = ap.parse_args()
    if args.cmd == "fix" and not args.finish and not args.request:
        ap.error("fix requires --request")
    args.fn(args)


if __name__ == "__main__":
    main()
