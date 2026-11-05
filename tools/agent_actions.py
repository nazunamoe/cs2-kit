FIX_TEXT = {
    "REDUCE_MAIN_DETAIL": "main 이 95000 tris 를 넘음. 층수·bay·창 위치는 유지하고 숨은 면과 보조 디테일만 줄임",
    "REDUCE_LOD_DETAIL": "LOD1/LOD2 에서 작은 부품을 제거. 프리셋 모드면 해당 LOD 호출에 quality_stage=3 전달",
    "FIX_CUSTOM_UV": "ATLAS_UV 만 해당. custom quad UV 를 A.uv_full/A.uv_tile 등 atlas helper 로 교체",
    "FIX_WINDOW_UV": "WindowSet.add_face 로 창을 다시 만들고 custom window UV 를 제거. 창 겹침 여부도 확인",
    "REMOVE_DEGENERATE_FACES": "퇴화 면의 좌표를 확인하고 중복 호출 또는 같은 위치의 정점을 제거",
}


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
