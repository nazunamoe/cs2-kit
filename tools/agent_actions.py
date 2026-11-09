FIX_TEXT = {
    "REDUCE_MAIN_DETAIL": "main 이 95000 tris 를 넘음. 층수·bay·창 위치는 유지하고 숨은 면과 보조 디테일만 줄임",
    "REDUCE_LOD_DETAIL": "LOD1/LOD2 에서 작은 부품을 제거. 프리셋 모드면 해당 LOD 호출에 quality_stage=3 전달",
    "FIX_CUSTOM_UV": "ATLAS_UV 만 해당. custom quad UV 를 A.uv_full/A.uv_tile 등 atlas helper 로 교체",
    "FIX_WINDOW_UV": "WindowSet.add_face 로 창을 다시 만들고 custom window UV 를 제거. 창 겹침 여부도 확인",
    "REMOVE_DEGENERATE_FACES": "퇴화 면의 좌표를 확인하고 중복 호출 또는 같은 위치의 정점을 제거",
}

CATEGORY_TEXT = {
    "build": "빌드: 생성기 실행 로그의 첫 traceback/오류를 고친 뒤 quick 부터 다시 실행",
    "geometry": "기하: check.py ERROR key 와 예시 좌표를 확인. 층수·bay·창 위치는 줄이지 않음",
    "texture": "텍스처/UV: ATLAS_UV·WIN_UV·texel 밀도 순서로 확인하고 atlas helper 로 교체",
    "lod": "LOD: lod_check 의 HOLE 줄과 LOD1/LOD2 tris 를 확인. main 구조를 줄여 맞추지 않음",
    "photo_match": "사진: previews/photo_check 와 plane_compare 시트를 같은 카메라로 비교하고 근거를 남김",
    "gate": "게이트: final/require-final 의 미완료 항목을 먼저 채움",
}


def classify_gate(gate):
    """Map a gate result to a small set of builder categories and a compact brief.

    This is a deterministic mapping of check keys and error keys, not a text classifier.
    Unknown error keys fall back to geometry so a failure is never dropped silently.
    """
    checks = gate.get("checks") or {}
    errors = gate.get("errors") or []
    cats = []

    def add(cat):
        if cat not in cats:
            cats.append(cat)

    for key, value in checks.items():
        if value != "FAIL":
            continue
        if key in ("build", "fbx"):
            add("build")
        elif key in ("lod", "lod1", "lod2"):
            add("lod")
        elif key == "photo":
            add("photo_match")
        elif key in ("tiles", "texture"):
            add("texture")
    for err in errors:
        key = str(err.get("key") or "")
        if not key:
            add("build" if checks.get("build") == "FAIL" else "geometry")
        elif key in ("tex", "atlas", "win_uv", "texel") or key.startswith("tex"):
            add("texture")
        elif key.startswith(("lod1", "lod2")):
            add("lod")
        elif key.startswith(("win_", "coplanar", "degenerate", "tris", "size", "pivot")):
            add("geometry")
        elif key in ("build", "fbx"):
            add("build")
        else:
            add("geometry")
    if (gate.get("photo") or {}).get("mismatch"):
        add("photo_match")
    if (gate.get("lod") or {}).get("status") == "FAIL":
        add("lod")
    if gate.get("status") in ("INCOMPLETE", "NEEDS_HUMAN_REVIEW"):
        add("gate")
    if not cats and gate.get("status") not in ("PASS", None):
        add("gate")

    lines = ["# Builder brief", "",
             "gate: %s %s" % (gate.get("mode", "?"), gate.get("status", "?")),
             "failed checks: " + (", ".join(k for k, v in checks.items() if v == "FAIL") or "none"),
             "categories: " + (", ".join(cats) or "none"), ""]
    for cat in cats:
        lines.append("- " + CATEGORY_TEXT[cat])
    if errors:
        lines += ["", "first errors:"]
        for err in errors[:3]:
            msg = err.get("msg") or err.get("key") or "error"
            ex = (err.get("examples") or [None])[0]
            lines.append("- [%s] %s%s" % (err.get("key", "?"), msg, (" e.g. %s" % ex) if ex is not None else ""))
    if not errors and gate.get("status") not in ("PASS",):
        lines += ["", "no structured errors: read the gate JSON and the last cycle log first."]
    return {"categories": cats, "brief": "\n".join(lines)}



def agent_summary(r):
    i = r["info"]
    err_keys = {e["key"] for e in r["errors"]}
    warn_keys = {w["key"] for w in r["warnings"]}
    tags = []
    if "tris" in warn_keys:
        tags.append("REDUCE_MAIN_DETAIL")
    if "lod1" in err_keys or "lod2" in err_keys:
        tags.append("REDUCE_LOD_DETAIL")
    if "atlas" in err_keys:
        tags.append("FIX_CUSTOM_UV")
    if "win_uv" in err_keys:
        tags.append("FIX_WINDOW_UV")
    if "degenerate" in warn_keys:
        tags.append("REMOVE_DEGENERATE_FACES")
    fix = "; ".join(FIX_TEXT[t] for t in tags) if tags else "no fix needed"
    lod_name = {"main": "LOD0", "lod1": "LOD1", "lod2": "LOD2"}
    verts = {lod_name[k]: v for k, v in i.get("verts", {}).items() if k in lod_name}
    return dict(status="FAIL" if r["errors"] else "PASS", verts=verts,
                action_tags=tags, exact_fix_instruction=fix)
