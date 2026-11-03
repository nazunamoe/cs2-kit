"""검증 점수 기록과 회귀 경고 (tools/qa/verify.py 가 쓴다).

작업 폴더(= 활성 프로젝트)의 work/chk/scores.json 에 verify 한 번에 한 줄씩 쌓는다.
  record = {time, label, mode(full|fast), asset, tris{main,lod1,lod2}, lod{mode(full|quick), main, lod1, lod2 (최대 구멍 %)},
            shots{"<도구>:<사진>": iou}}   도구 = cmp_cam(verify.json 의 shots) | all(cmp_all.py 16장 전부)

회귀 경고 = 같은 키(같은 도구·같은 사진, LOD 는 같은 모드끼리)의 직전 값보다 나빠진 것만:
  - 사진 실루엣 IoU 가 0.02 넘게 떨어짐
  - LOD 최대 구멍 %가 0.01 %p 넘게 늘어남
  - cmp_all 의 크기 scale(모델을 사진에 맞춘 배율)이 0.02 넘게 변함 (IoU 는 균일한 크기 변화를 흡수하므로 따로 본다;
    단, 같은 사진·같은 탐색 범위끼리 비교)
**이것은 "전보다 나빠졌나"를 보는 회귀 감시다. 실루엣 IoU 는 거의 대칭인 건물에서 반대 면도 비슷하게 나오고
구조(창 위치·면 폭·옥상)는 못 보므로 "사진과 같다"의 증거가 아니다.**
"""
import json
import os
import time

IOU_DROP = 0.02
SCALE_JUMP = 0.02       # cmp_all 은 크기를 0.0125 단위로 맞추므로 2칸 이상(>0.02) 움직이면 경고
LOD_RISE = 0.01


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return []


def check(history, rec):
    """history 의 가장 최근 같은 키 값과 rec 를 비교해 경고 문자열 목록."""
    warns = []
    for key, iou in rec.get("shots", {}).items():
        for prev in reversed(history):
            if key in prev.get("shots", {}):
                d = iou - prev["shots"][key]
                if d < -IOU_DROP:
                    warns.append("REGRESS %s iou %.3f -> %.3f (%+.3f, prev: %s %s)" % (key, prev["shots"][key], iou, d, prev.get("time", "?"), prev.get("label", "")))
                break
    for key, sc in rec.get("scales", {}).items():
        for prev in reversed(history):
            if key in prev.get("scales", {}):
                if abs(sc - prev["scales"][key]) > SCALE_JUMP:
                    warns.append("SCALE_CHANGE %s scale %.3f -> %.3f (model size vs photo changed; prev: %s %s)" % (key, prev["scales"][key], sc, prev.get("time", "?"), prev.get("label", "")))
                break
    lod = rec.get("lod")
    if lod:
        for prev in reversed(history):
            pl = prev.get("lod")
            if pl and pl.get("mode") == lod.get("mode"):
                for g in ("main", "lod1", "lod2"):
                    if g in lod and g in pl and lod[g] - pl[g] > LOD_RISE:
                        warns.append("REGRESS lod(%s) %s hole %.3f%% -> %.3f%% (prev: %s %s)" % (lod["mode"], g, pl[g], lod[g], prev.get("time", "?"), prev.get("label", "")))
                break
    return warns


def append(path, rec):
    """rec 를 path 에 덧붙이고 경고 목록을 돌려준다 (파일이 깨져 있으면 새로 시작)."""
    hist = load(path)
    rec = dict(rec, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    warns = check(hist, rec)
    hist.append(rec)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump(hist[-200:], open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return warns
