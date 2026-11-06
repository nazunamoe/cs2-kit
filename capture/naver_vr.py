"""네이버 부동산 VR 단지 뷰 -> 동별 8방향 입면 캡쳐.

준비: Chrome 을 디버그 포트로 열고 단지 VR 투어 페이지(fin.land.naver.com/complexes/<번호>/tour)를 띄워 둔다.
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir=D:\\chrome_vr

사용:
  python capture/naver_vr.py list                      # 동 목록
  python capture/naver_vr.py run                       # 모든 동, 8방향
  python capture/naver_vr.py run --dongs 101,103 --angles 8 --width 0.4 --overlap 0.3

동작(동마다):
  1) 전체 보기에서 카메라를 그 동 라벨로 옮기고 라벨을 클릭 -> 포커스 모드(그 동만, 수평 카메라)
  2) 건물 폭(평면 외곽선 투영)이 화면 폭의 --width 가 되도록 거리 조정 (뷰어 허용 범위 안에서)
  3) 이동 가능 범위(위·아래로 화면 높이의 --extra 만큼 넓힘) 맨 위 -> 화면 높이의 (1-overlap) 씩 아래로,
     끝에 닿으면 멈춤. 매 위치 캡쳐
  4) 방위각을 45도씩 돌려(모델이 오른쪽으로 도는 방향) 3) 반복, 처음 각도로 오면 X 로 닫기
캡쳐 전에 DOM 오버레이(헤더·버튼·매물 라벨)와 파란 매물 층 강조 메시를 숨기고, 캔버스 전체를 찍는다.

출력(기본 capture/out/<단지번호>/): <동>_side<번호>.png (찍은 순서, 1부터), <동>_meta.json (각 사진의 각도·카메라 높이)
"""
import argparse, json, math, os, re, sys, time, urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

CDP = "http://127.0.0.1:9222"
ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 페이지 JS
JS_CC = r"""
() => new Promise(res => window.applyCamera((cc, mgr, center) => { window.__cc = cc; window.__mgr = mgr; res(true); }))
"""
JS_STATE = r"""
() => { const cc = window.__cc, mgr = window.__mgr;
  return {target: cc.getTarget().toArray(), dist: cc.distance, az: cc.azimuthAngle, polar: cc.polarAngle,
          minDist: cc.minDistance, maxDist: cc.maxDistance, fov: cc.camera.fov, aspect: cc.camera.aspect,
          focused: !!mgr.focused, rest: !!cc._hasRested,
          boundary: cc._boundary ? [cc._boundary.min.toArray(), cc._boundary.max.toArray()] : null}; }
"""
JS_PROJ = r"""
(pts) => { const cam = window.__cc.camera; cam.updateMatrixWorld(); const V = cam.position.constructor;
  return pts.map(p => { const v = new V(p[0], p[1], p[2]).project(cam); return [(v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight, v.z]; }); }
"""
# three.js Scene 잡기: Object3D.prototype.updateMatrixWorld 를 잠깐 가로챈다
JS_GRAB_SCENE = r"""
() => new Promise(res => { const cc = window.__cc;
  if (window.__scenesV === 2 && window.__scenes && window.__scenes.length) return res(window.__scenes.length);
  let target = null, P = Object.getPrototypeOf(cc.camera);
  while (P && P !== Object.prototype) { if (Object.prototype.hasOwnProperty.call(P, 'updateMatrixWorld')) target = P; P = Object.getPrototypeOf(P); }
  const orig = target.updateMatrixWorld, S = new Set();
  target.updateMatrixWorld = function (f) { if (this.isScene) S.add(this); return orig.call(this, f); };
  // 그려지는 물체마다 불리는 onBeforeRender 도 가로챈다 -> 행렬 자동 갱신을 끈 장면(라벨 전용 장면 등)도 잡힌다
  const ob = target.onBeforeRender;
  target.onBeforeRender = function (r, s) { if (s && s.isScene) S.add(s); if (r) window.__renderer = r; return ob.apply(this, arguments); };
  cc.rotate(0.0002, 0, true); setTimeout(() => cc.rotate(-0.0002, 0, true), 250);
  setTimeout(() => { target.updateMatrixWorld = orig; target.onBeforeRender = ob;
    window.__scenes = [...S]; window.__scenesV = 2;
    let best = null, bv = -1;
    window.__scenes.forEach(sc => { let v = 0; sc.traverse(o => { const g = o.geometry; if (g && g.attributes && g.attributes.position) v += g.attributes.position.count; });
      if (v > bv) { bv = v; best = sc; } });
    window.__scene = best; res(window.__scenes.length); }, 1200); })
"""
# 매물 층 강조(파랑 #0a7df3, 보라 #c759d4 등 반투명 0.3 판) 숨기기 - 색과 상관없이 반투명 메시 전부
JS_HIDE_HL = r"""
() => { let n = 0; if (!window.__scene) return -1;
  (window.__scenes && window.__scenes.length ? window.__scenes : [window.__scene]).forEach(sc => sc.traverse(o => { const m = Array.isArray(o.material) ? o.material[0] : o.material;
    if (o.isMesh && m && m.color && m.transparent && m.opacity < 0.9) { if (o.visible) n++; o.visible = false; } }));
  return n; }
"""
CSS_HIDE = "body *{visibility:hidden !important} canvas{visibility:visible !important}"

# ---------------------------------------------------------------- 도우미
def log(*a):
    print(*a, flush=True)


def connect(p):
    br = p.chromium.connect_over_cdp(CDP)
    pages = [x for c in br.contexts for x in c.pages if "land.naver.com" in x.url and "/tour" in x.url]
    if not pages:
        sys.exit("VR 투어 페이지(fin.land.naver.com/complexes/<번호>/tour)를 찾지 못함")
    pg = pages[0]
    for _ in range(90):  # 로딩 화면 대기
        if not pg.evaluate("() => !!document.querySelector('[class*=TourLoading]')"):
            break
        time.sleep(1)
    pg.evaluate(JS_CC)
    return br, pg


def wait_tour(pg, timeout=120):
    """VR 뷰어가 준비될 때까지(applyCamera 있음 + 로딩 화면 사라짐) 기다린다."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        ok = pg.evaluate("() => typeof window.applyCamera === 'function' && !!document.querySelector('#xrx-viewer canvas')"
                         " && !document.querySelector('[class*=TourLoading]')")
        if ok:
            time.sleep(3.0)
            pg.evaluate(JS_CC)
            return True
        time.sleep(1)
    return False


def open_tour(pg, url):
    """페이지를 url 로 옮기고 data.xrx 주소를 잡아 둔다."""
    found = []
    h = lambda r: found.append(r.url) if "data.xrx" in r.url else None
    pg.on("response", h)
    pg.goto(url, wait_until="domcontentloaded", timeout=90000)
    ok = wait_tour(pg)
    pg.remove_listener("response", h)
    return ok, (found[0] if found else None)


def load_xrx(pg, url=None):
    url = url or pg.evaluate("() => performance.getEntriesByType('resource').map(e => e.name).find(n => n.includes('data.xrx'))")
    if not url:
        sys.exit("data.xrx 를 찾지 못함 - 페이지를 새로고침한 뒤 다시 실행")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fin.land.naver.com/"})
    return json.loads(urllib.request.urlopen(req).read())


def poi_points(q):
    """평면 외곽선 점(장면 단위 = 데이터/100) - 바닥/옥상 높이 두 벌."""
    pts = []
    def flat(o):
        if isinstance(o, list) and o and isinstance(o[0], (int, float)):
            pts.append(o)
        elif isinstance(o, list):
            for x in o:
                flat(x)
    flat(q.get("footprint") or q.get("obb"))
    els = [s["elevation"] for s in q.get("slices", [])] or [pts[0][1]]
    lo, hi = min(els), max(els)
    out = []
    for x, _, z in pts:
        out.append([x / 100, lo / 100, z / 100])
        out.append([x / 100, hi / 100, z / 100])
    return out, lo / 100, hi / 100


def kick(pg):
    """다시 그리게 만든다(카메라를 아주 조금 움직였다 되돌림)."""
    pg.evaluate("() => window.__cc.truck(0, 1e-6, false)")
    time.sleep(0.12)
    pg.evaluate("() => window.__cc.truck(0, -1e-6, false)")


def shot(pg, box):
    b = pg.screenshot(clip=box, scale="device", animations="disabled")
    from io import BytesIO
    return Image.open(BytesIO(b)).convert("RGB")


def stable_shot(pg, box, wait=0.8, tries=8):
    """화면이 멈출 때까지(텍스처 로딩 포함) 기다렸다 찍는다."""
    time.sleep(wait)
    prev = None
    for _ in range(tries):
        im = shot(pg, box)
        a = np.asarray(im.resize((im.width // 8, im.height // 8)), dtype=np.int16)
        if prev is not None and np.abs(a - prev).mean() < 0.4:
            return im
        prev = a
        time.sleep(0.6)
    return im


def canvas_box(pg):
    return pg.evaluate("""() => { const r = document.querySelector('#xrx-viewer canvas').getBoundingClientRect();
        return {x: Math.max(0, r.x), y: Math.max(0, r.y), width: Math.min(r.width, innerWidth), height: Math.min(r.height, innerHeight)}; }""")


def set_quality(pg, want="고화질"):
    """화질 버튼 -> '화질 선택' 라디오 창에서 want 선택. 버튼이 없으면 그냥 넘어간다."""
    btn = pg.locator("button[data-nlogs-area='default.quality']")
    if not btn.count():
        return "no quality button"
    txt = btn.first.inner_text().strip()
    if txt == want:
        return txt
    btn.first.click()
    time.sleep(1.0)
    try:
        pg.locator("[id^=portal] label", has_text=want).first.click(timeout=3000)
    except Exception as ex:
        log("[quality] WARN", str(ex).splitlines()[0])
    time.sleep(1.0)
    close_modal(pg)
    time.sleep(3.0)  # 새 화질 텍스처 로딩
    return btn.first.inner_text().strip()


def close_modal(pg):
    """열린 모달(dimmed layer)이 있으면 닫는다."""
    for _ in range(3):
        if not pg.evaluate("() => !!document.querySelector('[data-testid=dimmed-layer]')"):
            return
        btn = pg.get_by_role("button", name="모달 닫기")
        if btn.count():
            btn.first.click(timeout=3000)
        else:
            pg.keyboard.press("Escape")
        time.sleep(0.8)


def header_dong(pg):
    return pg.evaluate("() => { const e = document.querySelector('[class*=TourViewerHeader] [class*=detai]'); return e ? e.innerText.trim() : ''; }")


def focus_dong(pg, q):
    """전체 보기에서 라벨을 클릭해 포커스 모드로. 성공하면 True."""
    close_modal(pg)
    pos = [v / 100 for v in q["position"]]
    pg.evaluate("(p) => window.__cc.moveTo(p[0], p[1], p[2], false)", pos)
    time.sleep(1.5)
    for dy in (30, 15, 45, 60, 5):
        x, y, _ = pg.evaluate(JS_PROJ, [pos])[0]
        pg.mouse.click(x, y - dy)
        for _ in range(12):
            time.sleep(0.5)
            st = pg.evaluate(JS_STATE)
            if st["focused"] and header_dong(pg).startswith(q["name"]):
                pg.mouse.move(3, pg.evaluate("innerHeight") - 3)  # 마우스를 건물 밖(왼쪽 아래 구석)으로
                time.sleep(2.0)  # 포커스 애니메이션
                return True
        if pg.evaluate(JS_STATE)["focused"]:  # 다른 동이 열렸다
            close_focus(pg)
    return False


def close_focus(pg):
    loc = pg.locator("button:has(span:text('닫기'))")
    if loc.count():
        loc.first.click()
    else:
        pg.locator("[class*=TourViewerHeader] button").last.click()
    for _ in range(20):
        time.sleep(0.4)
        if not pg.evaluate(JS_STATE)["focused"]:
            break
    time.sleep(2.0)


def fit_width(pg, pts, frac):
    """건물 폭 / 화면 폭 = frac 이 되도록 거리 조정(허용 범위로 자름). 실제 비율 반환."""
    vw = pg.evaluate("innerWidth")
    for _ in range(4):
        sc = pg.evaluate(JS_PROJ, pts)
        xs = [s[0] for s in sc]
        w = (max(xs) - min(xs)) / vw
        st = pg.evaluate(JS_STATE)
        if abs(w - frac) < 0.01:
            return w, st["dist"]
        d = min(max(st["dist"] * w / frac, st["minDist"]), st["maxDist"])
        if abs(d - st["dist"]) < 1e-4:
            return w, st["dist"]
        pg.evaluate("(d) => window.__cc.dollyTo(d, false)", d)
        time.sleep(0.6)
    return w, pg.evaluate(JS_STATE)["dist"]


def wait_rest(pg, timeout=8.0):
    """카메라(타깃·거리·각도)가 멈출 때까지 기다린다 (포커스 애니메이션 중에 재면 거리가 틀림)."""
    prev, t0 = None, time.time()
    while time.time() - t0 < timeout:
        st = pg.evaluate(JS_STATE)
        cur = st["target"] + [st["dist"], st["az"], st["polar"]]
        if prev and max(abs(a - b) for a, b in zip(cur, prev)) < 1e-5:
            return st
        prev = cur
        time.sleep(0.4)
    return pg.evaluate(JS_STATE)


JS_CAM = r"""
() => { const c = window.__cc.camera; c.updateMatrixWorld(); c.updateProjectionMatrix(); const d = new c.position.constructor(); c.getWorldDirection(d);
  return {pos: c.position.toArray(), dir: d.toArray(), fov: c.fov, aspect: c.aspect,
          view: Array.from(c.matrixWorldInverse.elements), proj: Array.from(c.projectionMatrix.elements),   // 열 우선 4x4 (three.js)
          vw: innerWidth, vh: innerHeight}; }
"""


# ---------------------------------------------------------------- 평면·벽 기하 (브라우저 없이 계산)
def _rings(o):
    """중첩 리스트에서 [x,y,z] 점들의 고리(ring)를 모은다."""
    out = []
    def is_pt(v):
        return isinstance(v, list) and len(v) >= 3 and all(isinstance(t, (int, float)) for t in v[:3])
    def rec(x):
        if isinstance(x, list) and x and all(is_pt(v) for v in x):
            out.append(x)
        elif isinstance(x, list):
            for v in x:
                rec(v)
    rec(o)
    return out


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def footprint_xz(q):
    """동의 평면 외곽선 [(x, z)] (m, 시계/반시계 무관). footprint 가 없으면 obb 의 볼록 껍질."""
    for key in ("footprint", "obb"):
        rs = _rings(q.get(key))
        if not rs:
            continue
        ring = max(rs, key=len) if key == "footprint" else sum(rs, [])
        xz = [(float(p[0]), float(p[2])) for p in ring]
        if key == "obb":
            xz = _hull(xz)
        if len(xz) > 1 and xz[0] == xz[-1]:
            xz = xz[:-1]
        if len(xz) >= 3:
            return xz
    return []


def walls_of(xz, min_len=4.0, group_deg=20.0, depth_gap=3.0):
    """외곽선 -> 면(벽) 목록. 발코니 단차처럼 같은 방향이고 깊이 차가 depth_gap(m) 이내인 변은 한 면으로 합친다.
    면의 위치는 가장 바깥 변 기준 평면, 폭은 합친 변들의 전체 범위. 방위각은 카메라 방위각(0 = +Z 쪽에서 봄)."""
    n = len(xz)
    area2 = sum(xz[i][0] * xz[(i + 1) % n][1] - xz[(i + 1) % n][0] * xz[i][1] for i in range(n))
    sgn = 1.0 if area2 > 0 else -1.0
    edges = []
    for i in range(n):
        (x0, z0), (x1, z1) = xz[i], xz[(i + 1) % n]
        L = math.hypot(x1 - x0, z1 - z0)
        if L < 0.3:
            continue
        nx, nz = sgn * (z1 - z0) / L, -sgn * (x1 - x0) / L       # 바깥쪽 법선 (x,z)
        edges.append({"i": i, "a": (x0, z0), "b": (x1, z1), "L": L, "n": (nx, nz)})
    # 1) 방향끼리 묶기 (긴 변부터)
    cosg = math.cos(math.radians(group_deg))
    dirs = []
    for e in sorted(edges, key=lambda e: -e["L"]):
        for g in dirs:
            if e["n"][0] * g["n"][0] + e["n"][1] * g["n"][1] >= cosg:
                g["e"].append(e)
                break
        else:
            dirs.append({"n": e["n"], "e": [e]})
    out = []
    for g in dirs:
        sx = sum(e["n"][0] * e["L"] for e in g["e"])
        sz = sum(e["n"][1] * e["L"] for e in g["e"])
        hl = math.hypot(sx, sz) or 1.0
        nx, nz = sx / hl, sz / hl
        tx, tz = -nz, nx
        off = lambda p: p[0] * nx + p[1] * nz
        # 2) 깊이(법선 방향 위치)로 나누기: 단차(<= depth_gap)는 합치고, 날개(ㄱ자 등)는 나눈다
        es = sorted(g["e"], key=lambda e: -(off(e["a"]) + off(e["b"])) / 2)
        subs, cur, last = [], [], None
        for e in es:
            o = (off(e["a"]) + off(e["b"])) / 2
            if cur and last - o > depth_gap:
                subs.append(cur)
                cur = []
            cur.append(e)
            last = o
        if cur:
            subs.append(cur)
        for sub in subs:
            pts = [e["a"] for e in sub] + [e["b"] for e in sub]
            ts = [p[0] * tx + p[1] * tz for p in pts]
            o_out = max(off(p) for p in pts)
            span = max(ts) - min(ts)
            if span < min_len or sum(e["L"] for e in sub) < min_len:   # 단차의 짧은 옆변만 모인 가짜 면은 버림
                continue
            P = lambda t: [round(t * tx + o_out * nx, 4), round(t * tz + o_out * nz, 4)]
            out.append({"p0": P(min(ts)), "p1": P(max(ts)), "length_m": round(span, 3),
                        "normal": [round(nx, 5), round(nz, 5)], "azimuth_deg": round(math.degrees(math.atan2(nx, nz)), 3),
                        "parts": sorted(e["i"] for e in sub),
                        "depth_m": round(o_out - min(off(p) for p in pts), 2)})
    out.sort(key=lambda w: w["azimuth_deg"])
    for k, w in enumerate(out):
        w["i"] = k
    return out


def reference_walls_of(xz, grouped=None, min_len=1.0, angle_tol=2.0, offset_tol=0.05):
    """Exact planar runs for homography refs; unlike walls_of, never bridges depth or angle changes."""
    n = len(xz)
    area2 = sum(xz[i][0] * xz[(i + 1) % n][1] - xz[(i + 1) % n][0] * xz[i][1] for i in range(n))
    sgn = 1.0 if area2 > 0 else -1.0
    edges = []
    for i in range(n):
        a, b = xz[i], xz[(i + 1) % n]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 0.05:
            continue
        nx, nz = sgn * (b[1] - a[1]) / length, -sgn * (b[0] - a[0]) / length
        edges.append({"i": i, "a": a, "b": b, "L": length, "n": (nx, nz),
                      "off": ((a[0] + b[0]) / 2 * nx + (a[1] + b[1]) / 2 * nz)})
    runs = []
    cos_tol = math.cos(math.radians(angle_tol))
    for edge in edges:
        if runs:
            base = runs[-1]["base"]
            if edge["n"][0] * base["n"][0] + edge["n"][1] * base["n"][1] >= cos_tol \
                    and abs(edge["off"] - base["off"]) <= offset_tol:
                runs[-1]["edges"].append(edge)
                continue
        runs.append({"base": edge, "edges": [edge]})
    if len(runs) > 1:
        first, last = runs[0]["base"], runs[-1]["base"]
        if first["n"][0] * last["n"][0] + first["n"][1] * last["n"][1] >= cos_tol \
                and abs(first["off"] - last["off"]) <= offset_tol:
            runs[0]["edges"] = runs[-1]["edges"] + runs[0]["edges"]
            runs.pop()
    out = []
    for run in runs:
        base = run["base"]
        nx, nz = base["n"]
        tx, tz = -nz, nx
        points = [p for e in run["edges"] for p in (e["a"], e["b"])]
        ts = [p[0] * tx + p[1] * tz for p in points]
        span = max(ts) - min(ts)
        if span < min_len:
            continue
        off = base["off"]
        parts = [e["i"] for e in run["edges"]]
        group_i = None
        if grouped:
            candidates = [g for g in grouped if set(parts) & set(g.get("parts", []))]
            if candidates:
                group_i = max(candidates, key=lambda g: len(set(parts) & set(g.get("parts", []))))["i"]
        project = lambda t: [round(t * tx + off * nx, 4), round(t * tz + off * nz, 4)]
        out.append({"p0": project(min(ts)), "p1": project(max(ts)), "length_m": round(span, 3),
                    "normal": [round(nx, 6), round(nz, 6)],
                    "azimuth_deg": round(math.degrees(math.atan2(nx, nz)), 3),
                    "parts": parts, "group_i": group_i, "depth_m": 0.0,
                    "plane_error_m": round(max(abs(p[0] * nx + p[1] * nz - off) for p in points), 4)})
    out.sort(key=lambda w: (w["azimuth_deg"], w["p0"]))
    for i, wall in enumerate(out):
        wall["i"] = i
    return out


def apply_mat(M, p):
    """three.js 열 우선 4x4 행렬 M(16개) x 점 p(3) -> (x,y,z,w)"""
    x, y, z = p
    return tuple(M[0 + r] * x + M[4 + r] * y + M[8 + r] * z + M[12 + r] for r in range(4))


def project_px(shot, p_m, box, dpr, img):
    """월드 점(m) -> 저장된 사진의 픽셀 [x, y, depth]. 카메라 뒤면 None."""
    c = shot["cam"]
    v = apply_mat(c["view"], [t / 100 for t in p_m])           # 장면 단위 = m/100
    clip = [sum(c["proj"][r + 4 * k] * (v[k] if k < 3 else 1.0) for k in range(4)) for r in range(4)]
    if clip[3] <= 1e-9:
        return None
    nx, ny = clip[0] / clip[3], clip[1] / clip[3]
    cx, cy = (nx + 1) / 2 * c["vw"], (1 - ny) / 2 * c["vh"]       # CSS 픽셀 (JS_PROJ 와 같은 식)
    sx = img[0] / (box["width"] * dpr)
    sy = img[1] / (box["height"] * dpr)
    return [(cx - box["x"]) * dpr * sx, (cy - box["y"]) * dpr * sy, clip[3]]
JS_SET_BOUNDARY = r"""
(b) => { const cc = window.__cc, B = cc._boundary;
  const box = new B.constructor(new B.min.constructor(...b[0]), new B.max.constructor(...b[1]));
  cc.setBoundary(box); }
"""


def hold_az(pg, az, tries=4):
    """방위각이 az 가 아니면 다시 맞춘다(이동·범위 변경 뒤 뷰어가 되돌리는 경우 대비). 최종 실제 방위각(rad)을 돌려준다."""
    cur = pg.evaluate(JS_STATE)["az"]
    for _ in range(tries):
        if abs((cur - az + math.pi) % (2 * math.pi) - math.pi) < 0.01:
            break
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az)
        time.sleep(0.25)
        cur = pg.evaluate(JS_STATE)["az"]
    return cur


def sweep(pg, box, out, name, n0, overlap, extra, shots, az_hold=None, center=False):
    """이동 범위 맨 위 -> 아래로 화면 높이의 (1-overlap) 씩, 더 안 내려가면 멈춤.
    뷰어 이동 범위를 위·아래로 화면 높이의 extra 만큼 넓혀서 찍고, 끝나면 원래 범위로 되돌린다.
    <동>_side<번호>.png 로 저장하고 다음 번호를 돌려준다."""
    st = pg.evaluate(JS_STATE)
    tx, ty, tz = st["target"]
    vis_h = 2 * st["dist"] * math.tan(math.radians(st["fov"]) / 2)  # 타깃 거리에서 화면 높이(장면 단위)
    scr_h = vis_h * (box["height"] / pg.evaluate("innerHeight"))  # 캡쳐 영역 높이(장면 단위)
    bnd = st["boundary"]
    if bnd:
        ext = scr_h * extra
        lo, hi = list(bnd[0]), list(bnd[1])
        lo[1] -= ext
        hi[1] += ext
        pg.evaluate(JS_SET_BOUNDARY, [lo, hi])
        ytop, ybot = hi[1], lo[1]
    else:
        ytop, ybot = ty, ty
    if center:
        mid = (ytop + ybot) / 2.0
        ytop = ybot = mid
    step = scr_h * (1 - overlap)
    n, y, last = n0, ytop, None
    try:
        while True:
            pg.evaluate("(p) => window.__cc.moveTo(p[0], p[1], p[2], false)", [tx, max(y, ybot), tz])
            if az_hold is not None:
                hold_az(pg, az_hold)
            pg.evaluate(JS_HIDE_HL)
            kick(pg)
            if az_hold is not None:
                real_az = hold_az(pg, az_hold)
                if abs((real_az - az_hold + math.pi) % (2 * math.pi) - math.pi) >= 0.01:
                    log(f"[{name}] WARN 방위각을 유지 못 함 (want {math.degrees(az_hold):.1f}, got {math.degrees(real_az):.1f}) - 이 사진은 방향이 다를 수 있음")
                    kick(pg)
            real = pg.evaluate(JS_STATE)["target"][1]
            if last is not None and abs(real - last) < 1e-5:  # 더 안 내려감
                break
            f = out / f"{name}_side{n}.png"
            im = stable_shot(pg, box)
            im.save(f)
            # 카메라 기록(장면 단위 = m/100): 나중에 벽 꼭짓점을 사진에 투영해 photo_refs 를 만들 때 쓴다
            # view/proj = 카메라 행렬, img = 저장된 사진 픽셀 크기 -> make_refs 가 브라우저 없이 투영
            shots.append({"file": f.name, "target_y": round(real, 6), "img": list(im.size), "cam": pg.evaluate(JS_CAM),
                          "az_deg_actual": round(math.degrees(pg.evaluate(JS_STATE)["az"]), 2)})
            n += 1
            last = real
            y -= step
    finally:
        if bnd:
            pg.evaluate(JS_SET_BOUNDARY, bnd)
            pg.evaluate("(p) => window.__cc.moveTo(p[0], p[1], p[2], false)", [tx, ty, tz])
    return n


# ---------------------------------------------------------------- 실행
def cmd_list(args):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg = connect(p)
        d = load_xrx(pg)
        log(d["id"], d["name"])
        for q in d["poi"]:
            fl = q.get("floor", {})
            els = [s["elevation"] for s in q.get("slices", [])]
            log(f"  {q['name']}  floors {fl.get('minFloor')}~{fl.get('maxFloor')}  height {max(els) - min(els):.1f} m" if els else f"  {q['name']}")


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("_") or "x"


JS_LABELS = r"""
(hide) => {
  // 글자/아이콘 숨기기
  //  DOM: 건물 캔버스와 그 조상을 뺀 모든 요소(섀도 DOM 포함)를 인라인 !important 로 숨김 (페이지 스타일보다 우선)
  //  3D : 잡은 모든 장면에서 스프라이트·CSS2D/3D·점 아이콘, 글자 텍스처, 투명한 작은 판(라벨 판), 이름에 label/text/poi/marker 가 든 물체
  const main = document.querySelector('#xrx-viewer canvas');
  const scenes = (window.__scenes && window.__scenes.length) ? window.__scenes : (window.__scene ? [window.__scene] : []);
  if (hide) {
    const L = window.__lbl = {objs: [], els: []};
    const walk = root => root.querySelectorAll('*').forEach(el => {
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el === main || (main && el.contains(main))) return;
      L.els.push([el, el.style.getPropertyValue('visibility'), el.style.getPropertyPriority('visibility')]);
      el.style.setProperty('visibility', 'hidden', 'important'); });
    walk(document.body);
    const info = [];
    // 네이버 VR: 건물·지형 = 'Root' 아래 텍스처 메시. 동 라벨(초록/흰 판, "101동", "총 36층", 배지) = Root 바깥의 텍스처 없는 단색 메시
    const under = (o, r) => { for (let p = o; p; p = p.parent) if (p === r) return true; return false; };
    scenes.forEach((sc, si) => { let n = 0, verts = 0, objs = 0;
      const root = sc.getObjectByName('Root');
      sc.traverse(o => { objs++;
        const g = o.geometry, pc = g && g.attributes && g.attributes.position ? g.attributes.position.count : 0; verts += pc;
        if (o === sc || !o.visible) return;
        const m = Array.isArray(o.material) ? o.material[0] : o.material, map = m && m.map;
        const textTex = !!(map && (map.isCanvasTexture || (typeof HTMLCanvasElement !== 'undefined' && map.image instanceof HTMLCanvasElement)));
        const labelQuad = !!(o.isMesh && map && pc > 0 && pc <= 8 && (m.transparent || m.depthTest === false));
        const named = /label|text|poi|marker|badge/i.test(o.name || '');
        const outsideNomap = !!(o.isMesh && !map && (root ? !under(o, root) : (o.layers && o.layers.mask === 2)));
        if (o.isSprite || o.isCSS2DObject || o.isCSS3DObject || o.isPoints || textTex || labelQuad || named || outsideNomap) { o.visible = false; L.objs.push(o); n++; } });
      info.push({scene: si, main: sc === window.__scene, root: !!root, objects: objs, verts: verts, hidden: n}); });
    return {dom_hidden: L.els.length, scenes: info};
  }
  const L = window.__lbl || {objs: [], els: []};
  L.objs.forEach(o => { o.visible = true; });
  L.els.forEach(([el, v, p]) => { if (v) el.style.setProperty('visibility', v, p); else el.style.removeProperty('visibility'); });
  window.__lbl = null; return {restored_dom: L.els.length, restored_objects: L.objs.length};
}
"""
JS_DUMP = r"""
() => { const scenes = (window.__scenes && window.__scenes.length) ? window.__scenes : (window.__scene ? [window.__scene] : []);
  const groups = {};
  scenes.forEach((sc, si) => sc.traverse(o => { if (o === sc) return;
    const g = o.geometry, m = Array.isArray(o.material) ? o.material[0] : o.material;
    const pc = g && g.attributes && g.attributes.position ? g.attributes.position.count : 0;
    const img = m && m.map && m.map.image;
    const key = ['s' + si, o.type, (o.name || '-').slice(0, 24), g ? g.type : '-', m ? m.type : '-',
      img ? (img.constructor.name + ' ' + (img.width || '?') + 'x' + (img.height || '?')) : 'nomap',
      pc <= 8 ? 'v<=8' : pc <= 200 ? 'v<=200' : pc <= 5000 ? 'v<=5k' : 'v>5k',
      m ? ('tr' + (m.transparent ? 1 : 0) + ' dt' + (m.depthTest ? 1 : 0) + ' op' + (m.opacity != null ? m.opacity.toFixed(2) : '?')) : '-',
      'ro' + o.renderOrder, 'L' + (o.layers ? o.layers.mask : '?'), o.visible ? 'vis' : 'hid',
      o.parent ? (o.parent.type + ':' + (o.parent.name || '-').slice(0, 16)) : '-'].join(' | ');
    groups[key] = (groups[key] || 0) + 1; }));
  return {camera_layers: window.__cc.camera.layers.mask, renderer: !!window.__renderer,
          groups: Object.entries(groups).sort((a, b) => b[1] - a[1]).slice(0, 40).map(([k, c]) => c + 'x  ' + k)}; }
"""
JS_WHAT_AT = r"""
(pts) => pts.map(([x, y]) => { const el = document.elementFromPoint(x, y);
  if (!el) return 'nothing';
  return el.tagName + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').slice(0, 2).join('.') : '')
         + ' "' + (el.innerText || '').trim().slice(0, 20).replace(/\n/g, ' ') + '"'; })
"""
CSS_REMOVE = "() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })"


def overview(pg, out, n=4, d=None):
    """단지 전체 보기 n 방향(360/n 도씩) -> danji_<k>.png.
    숨기는 것: 화면 위 글자(DOM: 동 라벨·매물 수·시설 라벨·버튼), 3D 안의 글자/아이콘(스프라이트), 매물 층 강조 메시.
    끝나면 처음 방위각으로 되돌리고 숨긴 것을 다시 보이게 한다(동 촬영에 영향 없게)."""
    box = canvas_box(pg)
    st0 = wait_rest(pg)
    if d and d.get("poi"):                      # 진단: 동 라벨 자리에 무엇이 있나 (DOM 이면 태그 이름, 캔버스면 CANVAS)
        q = d["poi"][0]
        x, y, _ = pg.evaluate(JS_PROJ, [[v / 100 for v in q["position"]]])[0]
        what = pg.evaluate(JS_WHAT_AT, [[x, y - dy] for dy in (10, 30, 50)])
        log(f"[overview] {q['name']} label spot: {what}")
    pg.add_style_tag(content=CSS_HIDE)
    nl = pg.evaluate(JS_LABELS, True)
    pg.evaluate(JS_HIDE_HL)
    log(f"[overview] hidden labels {nl}")
    dpr = pg.evaluate("devicePixelRatio")
    shots = []
    dump = pg.evaluate(JS_DUMP)
    (out / "scene_dump.txt").write_text("\n".join([f"camera layers {dump['camera_layers']}  renderer {dump['renderer']}"] + dump["groups"]), encoding="utf-8")
    if isinstance(nl, dict) and not sum(s["hidden"] for s in nl.get("scenes", [])):
        log("[overview] 3D 라벨을 못 찾음 - 장면 요약 (이 줄들을 보내 주세요, scene_dump.txt 에도 저장):")
        log(f"  camera layers {dump['camera_layers']}  renderer {dump['renderer']}")
        for g in dump["groups"]:
            log("  " + g)
    try:
        for k in range(1, n + 1):
            pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", st0["az"] - (k - 1) * 2 * math.pi / n)
            wait_rest(pg)
            kick(pg)
            im = stable_shot(pg, box, wait=1.5)
            im.save(out / f"danji_{k}.png")
            shots.append({"file": f"danji_{k}.png", "img": list(im.size), "cam": pg.evaluate(JS_CAM)})
    finally:
        pg.evaluate(CSS_REMOVE)
        pg.evaluate(JS_LABELS, False)
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", st0["az"])
        wait_rest(pg)
    log(f"[overview] {n} shots ({360 / n:.0f} deg) -> {out / 'danji_1.png'} .. danji_{n}.png")
    if d and d.get("poi"):
        tag_overview(out, {"canvas_css": box, "dpr": dpr, "shots": shots}, d)


def dong_tag(name):
    """'101동' -> '101' (그림에 쓰는 표시는 ASCII 만: 기본 글꼴이 한글을 못 그림)"""
    t = re.sub(r"[^0-9A-Za-z-]", "", str(name))
    return t or str(name)


def tag_overview(out, meta, d):
    """단지 사진마다 동 위치를 카메라로 투영 -> danji_meta.json + danji_<k>_tagged.png (원본은 그대로, 사본에 외곽선·동 번호)."""
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=30)
    except TypeError:
        font = ImageFont.load_default()
    box, dpr = meta["canvas_css"], meta["dpr"]
    dongs = []
    for q in d["poi"]:
        xz = footprint_xz(q)
        els = [s["elevation"] for s in q.get("slices", [])]
        lo, hi = (min(els), max(els)) if els else (q["position"][1], q["position"][1])
        if not xz:
            xz = [(q["position"][0], q["position"][2])]
        dongs.append({"name": q["name"], "tag": dong_tag(q["name"]), "floors": q.get("floor", {}).get("maxFloor"),
                      "footprint_m": [list(p) for p in xz], "ground_m": lo, "roof_m": hi})
    palette = [(255, 60, 60), (255, 170, 0), (60, 200, 255), (120, 255, 90), (255, 90, 220), (255, 255, 80)]
    for s in meta["shots"]:
        im = Image.open(out / s["file"]).convert("RGB")
        dr = ImageDraw.Draw(im)
        W_, H_ = s["img"]
        s["dongs"] = {}
        for k, g in enumerate(dongs):
            col = palette[k % len(palette)]
            top = [project_px(s, [x, g["roof_m"], z], box, dpr, s["img"]) for x, z in g["footprint_m"]]
            if any(p is None for p in top):
                continue
            cx = sum(p[0] for p in top) / len(top)
            cy = sum(p[1] for p in top) / len(top)
            base = [project_px(s, [x, g["ground_m"], z], box, dpr, s["img"]) for x, z in g["footprint_m"]]
            inside = 0 <= cx < W_ and 0 <= cy < H_
            s["dongs"][g["name"]] = {"roof_center_px": [round(cx, 1), round(cy, 1)], "in_view": inside,
                                     "roof_px": [[round(p[0], 1), round(p[1], 1)] for p in top]}
            if len(top) > 1:
                dr.line([tuple(p[:2]) for p in top] + [tuple(top[0][:2])], fill=col, width=3)
                if all(base):
                    for a, b in zip(top, base):
                        dr.line([tuple(a[:2]), tuple(b[:2])], fill=col, width=1)
            if inside:
                dr.text((cx, cy - 40), g["tag"], fill=col, font=font, anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
        im.save(out / s["file"].replace(".png", "_tagged.png"))
    (out / "danji_meta.json").write_text(json.dumps({"canvas_css": box, "dpr": dpr, "dongs": dongs, "shots": meta["shots"]},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[overview] dong tags -> danji_<k>_tagged.png, danji_meta.json ({len(dongs)} dongs)")


def cmd_overview(args):
    """단지 전체 사진만 찍는다 (동 촬영 없음)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg = connect(p)
        d = load_xrx(pg)
        out = Path(args.out or ROOT / "out" / str(d["id"]))
        out.mkdir(parents=True, exist_ok=True)
        close_modal(pg)
        if pg.evaluate(JS_STATE)["focused"]:
            close_focus(pg)
        if args.quality:
            log("[quality]", set_quality(pg, args.quality))
        log(f"[overview] scenes {pg.evaluate(JS_GRAB_SCENE)}")
        overview(pg, out, args.angles, d)


def capture_config(args):
    keys = ("fit_wall", "wall_frac", "min_wall", "wall_group_deg", "wall_depth_gap", "width",
            "overlap", "extra", "angles", "quality")
    return {key: getattr(args, key) for key in keys}


def completed_capture(path, config):
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        return bool(meta.get("complete") and meta.get("capture_config") == config)
    except (OSError, ValueError):
        return False


def run_complex(pg, d, out, args, url=None):
    """한 단지: 고화질 -> 동마다 포커스·8방향 캡쳐. 단지 데이터도 저장."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.xrx.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (out / "complex.json").write_text(json.dumps({"id": d["id"], "name": d.get("name"), "url": url or pg.url,
                                                  "dongs": [q["name"] for q in d["poi"]]}, ensure_ascii=False, indent=1), encoding="utf-8")
    want = [s.strip() for s in args.dongs.split(",")] if args.dongs else [q["name"] for q in d["poi"]]
    pois = [q for q in d["poi"] if q["name"] in want]
    log(f"[complex] {d['id']} dongs {[q['name'] for q in pois]} -> {out}")
    if pg.evaluate(JS_STATE)["focused"]:
        close_focus(pg)
    if args.quality:
        log("[quality]", set_quality(pg, args.quality))
    pg.evaluate(JS_GRAB_SCENE)
    if getattr(args, "overview", False) or os.environ.get("OVERVIEW") == "1":   # 기본은 끔. 켜면 동 촬영 전에 단지 전체를 찍고 각도를 되돌린다
        try:
            overview(pg, out, args.overview_angles, d)
        except Exception as ex:
            log(f"[overview] ERROR {type(ex).__name__}: {str(ex).splitlines()[0][:200]}")
            pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
    done, failed = [], []
    config = capture_config(args)
    for q in pois:
        meta_path = out / f"{safe_name(q['name'])}_meta.json"
        if not args.overwrite and completed_capture(meta_path, config):
            log(f"[{q['name']}] SKIP unchanged completed capture")
            done.append(q["name"])
            continue
        if meta_path.exists():
            try:
                previous = json.loads(meta_path.read_text(encoding="utf-8"))
                previous["complete"] = False
                meta_path.write_text(json.dumps(previous, ensure_ascii=False, indent=1), encoding="utf-8")
            except (OSError, ValueError):
                pass
        try:
            if capture_dong(pg, d, q, out, args):
                done.append(q["name"])
            else:
                failed.append(q["name"])
        except Exception as ex:
            log(f"[{q['name']}] ERROR {type(ex).__name__}: {str(ex).splitlines()[0][:200]}")
            failed.append(q["name"])
            try:
                pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
                close_modal(pg)
                if pg.evaluate(JS_STATE)["focused"]:
                    close_focus(pg)
            except Exception:
                pass
    log(f"[done] {d['id']} ok {done} fail {failed}")
    return done, failed


def capture_dong(pg, d, q, out, args):
    name = safe_name(q["name"])
    if not focus_dong(pg, q):
        log(f"[{name}] FAIL 라벨 클릭으로 포커스 못 함 - 건너뜀")
        return False
    wait_rest(pg)
    pts, ylo, yhi = poi_points(q)
    w, dist = fit_width(pg, pts, args.width)
    st = wait_rest(pg)
    log(f"[{name}] focus ok  width {w:.2f} (target {args.width})  dist {dist * 100:.1f} m"
        + (f"  boundary y {st['boundary'][0][1] * 100:.1f}~{st['boundary'][1][1] * 100:.1f}" if st["boundary"] else ""))
    pg.add_style_tag(content=CSS_HIDE)
    log(f"[{name}] hidden labels {pg.evaluate(JS_LABELS, True)}")
    box = canvas_box(pg)
    vh = pg.evaluate("innerHeight")
    dpr = pg.evaluate("devicePixelRatio")
    az0 = st["az"]
    meta = {"complex": d["id"], "dong": name, "floors": q.get("floor", {}).get("maxFloor"),
            "height_m": round((yhi - ylo) * 100, 2), "dist_m": round(dist * 100, 2), "fov_v_deg": st["fov"],
            "width_frac": round(w, 3), "canvas_css": box, "dpr": dpr,
            # 타깃(건물 중심) 거리 평면에서의 축척. 앞 벽은 더 가까워 이보다 조금 크다
            "px_per_m_at_target": round(vh * dpr / (2 * dist * 100 * math.tan(math.radians(st["fov"]) / 2)), 3),
            "capture_config": capture_config(args), "complete": False, "shots": []}
    # 평면·벽 정보(m). make_refs 가 이것과 사진마다의 카메라 행렬로 벽 꼭짓점을 사진 픽셀로 투영한다
    xz = footprint_xz(q)
    walls = walls_of(xz, args.min_wall, args.wall_group_deg, args.wall_depth_gap) if xz else []
    if args.fit_wall and walls:
        log(f"[{name}] faces {len(walls)}: " + ", ".join(f"{w['i']}:{w['length_m']:.0f}m(parts {len(w['parts'])})" for w in walls))
    meta.update({"footprint_m": [list(p) for p in xz], "ground_m": round(ylo * 100, 3), "roof_m": round(yhi * 100, 3),
                 "walls": walls, "fit_wall": bool(args.fit_wall)})
    n = 1
    try:
        if args.fit_wall:
            if not walls:
                log(f"[{name}] WARN 외곽선(footprint)이 없어 --fit-wall 불가 - 8방향으로 대체")
        if args.fit_wall and walls:
            # 1) 가장 긴 면을 정면으로 보는 방위각을 찾는다 (후보를 돌려 실제 카메라 방향으로 확인)
            main = max(walls, key=lambda w: w["length_m"])
            nx, nz = main["normal"]
            def face_cos():
                cam = pg.evaluate(JS_CAM)
                dx, dz = cam["dir"][0], cam["dir"][2]
                return -(dx * nx + dz * nz) / (math.hypot(dx, dz) or 1.0)   # 카메라가 그 면을 정면으로 보면 1
            want = math.atan2(nx, nz)
            best = None
            for cand in (want, want + math.pi, -want, math.pi - want):
                pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", cand)
                time.sleep(0.3)
                c = face_cos()
                if best is None or c > best[0]:
                    best = (c, cand)
                if c > 0.98:
                    break
            pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", best[1])
            time.sleep(0.3)
            if best[0] <= 0.98:
                log(f"[{name}] WARN 가장 긴 면 정면을 못 맞춤 (cos {best[0]:.2f})")
            az_base = pg.evaluate(JS_STATE)["az"]
            nang = args.angles or 4
            log(f"[{name}] fit-wall: 면 {main['i']} ({main['length_m']:.0f} m) 정면 기준 (cos {best[0]:.2f}), {nang}방향 {360 / nang:.0f}도씩")
            # 2) 거기서 360/nang 도씩 돌며 찍는다 (거리 = --width 기준, 8방향 모드와 같음)
            for k in range(nang):
                pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az_base - k * 2 * math.pi / nang)
                time.sleep(0.4)
                real_az = pg.evaluate(JS_STATE)["az"]
                cam = pg.evaluate(JS_CAM)
                dx, dz = cam["dir"][0], cam["dir"][2]
                hl = math.hypot(dx, dz) or 1.0
                facing = max(walls, key=lambda w: -(dx * w["normal"][0] + dz * w["normal"][1]) / hl)
                fc = -(dx * facing["normal"][0] + dz * facing["normal"][1]) / hl
                if args.wall_frac:                       # 지정했을 때만 그 면에 맞춰 가까이 (사진 수 늘어남)
                    bpts = [[facing["p0"][0] / 100, ylo, facing["p0"][1] / 100], [facing["p1"][0] / 100, ylo, facing["p1"][1] / 100],
                            [facing["p0"][0] / 100, yhi, facing["p0"][1] / 100], [facing["p1"][0] / 100, yhi, facing["p1"][1] / 100]]
                    fit_width(pg, bpts, args.wall_frac)
                    wait_rest(pg)
                shots = []
                n1 = sweep(pg, box, out, name, n, args.overlap, args.extra, shots, az_hold=real_az,
                           center=args.center)
                for s in shots:
                    s["angle_deg"] = round(k * 360 / nang)
                    if fc > 0.9:
                        s["wall"] = facing["i"]
                meta["shots"] += shots
                log(f"[{name}] {round(k * 360 / nang):3d} deg  면 {facing['i']} ({facing['length_m']:.0f} m, cos {fc:.2f})  side{n}~side{n1 - 1}")
                n = n1
        else:
            nang = args.angles or 8
            for k in range(nang):
                ang = round(k * 360 / nang)
                pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0 - math.radians(ang))
                time.sleep(0.4)
                real_az = pg.evaluate(JS_STATE)["az"]
                if k and abs((real_az - az0) + math.radians(ang)) > 0.02:
                    log(f"[{name}] WARN 방위각이 안 돌아감 (want {-ang}, got {math.degrees(real_az - az0):.1f})")
                shots = []
                n1 = sweep(pg, box, out, name, n, args.overlap, args.extra, shots, az_hold=real_az,
                           center=args.center)
                for s in shots:
                    s["angle_deg"] = ang
                meta["shots"] += shots
                log(f"[{name}] {ang:3d} deg  side{n}~side{n1 - 1}")
                n = n1
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0)  # 처음 각도로
        time.sleep(0.5)
        meta["complete"] = True
    finally:
        pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
        pg.evaluate(JS_LABELS, False)
        (out / f"{name}_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    close_focus(pg)
    return True


def cmd_run(args):
    """지금 떠 있는 단지 하나."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg = connect(p)
        d = load_xrx(pg)
        run_complex(pg, d, Path(args.out or ROOT / "out" / str(d["id"])), args)


def cmd_batch(args):
    """여러 단지 URL 을 차례로 연다. 단지마다 capture/out/<번호>/ (이미 끝난 단지는 건너뜀)."""
    from playwright.sync_api import sync_playwright
    urls = list(args.urls)
    if args.file:
        urls += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip().startswith("http")]
    root = Path(args.out or ROOT / "out")
    with sync_playwright() as p:
        br, pg = connect(p)
        summary = []
        for url in urls:
            cid = re.search(r"complexes/(\d+)", url)
            cid = cid.group(1) if cid else safe_name(url)
            out = root / cid
            done_path = out / "DONE"
            if done_path.exists():
                try:
                    previous = json.loads(done_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    previous = {}
                if not previous.get("fail"):
                    log(f"[skip] {cid} 이미 완료")
                    continue
            try:
                ok, xurl = open_tour(pg, url)
                if not ok:
                    log(f"[{cid}] FAIL 뷰어 로딩 실패")
                    summary.append((cid, "load fail"))
                    continue
                d = load_xrx(pg, xurl)
                done, failed = run_complex(pg, d, out, args, url)
                if failed:
                    done_path.unlink(missing_ok=True)
                else:
                    done_path.write_text(json.dumps({"ok": done, "fail": []}, ensure_ascii=False), encoding="utf-8")
                summary.append((cid, f"ok {len(done)} fail {failed}"))
            except Exception as ex:
                log(f"[{cid}] ERROR {type(ex).__name__}: {str(ex).splitlines()[0][:200]}")
                summary.append((cid, "error"))
        log("[batch summary]")
        for cid, s in summary:
            log(f"  {cid}: {s}")


def cmd_probe(args):
    """진단: 한 동에 포커스한 뒤 회전 방법(rotateAzimuthTo / rotate)별로 방위각·카메라 위치·화면이 실제로 바뀌는지 출력."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg = connect(p)
        d = load_xrx(pg)
        want = [s.strip() for s in args.dongs.split(",")] if args.dongs else None
        q = next(q for q in d["poi"] if not want or q["name"] in want)
        if pg.evaluate(JS_STATE)["focused"]:
            close_focus(pg)
        pg.evaluate(JS_GRAB_SCENE)
        if not focus_dong(pg, q):
            sys.exit(f"[probe] {q['name']} 포커스 실패")
        wait_rest(pg)
        box = canvas_box(pg)
        pg.add_style_tag(content=CSS_HIDE)
        info = pg.evaluate("() => { const c = window.__cc; return {minAz: c.minAzimuthAngle, maxAz: c.maxAzimuthAngle, enabled: c.enabled, "
                           "minPolar: c.minPolarAngle, maxPolar: c.maxPolarAngle, smooth: c.smoothTime, draggingSmooth: c.draggingSmoothTime}; }")
        log("[probe] controls", info)

        def snap():
            im = shot(pg, box)
            return np.asarray(im.resize((im.width // 8, im.height // 8)), dtype=np.int16)

        def rep(tag, prev):
            s0 = pg.evaluate(JS_STATE)
            c0 = pg.evaluate(JS_CAM)
            kick(pg)
            st = wait_rest(pg)
            time.sleep(1.0)
            c1 = pg.evaluate(JS_CAM)
            cur = snap()
            diff = float(np.abs(cur - prev).mean())
            log(f"[probe] {tag}: az {math.degrees(s0['az']):.1f} -> {math.degrees(st['az']):.1f} deg | "
                f"camera moved before kick {math.dist(c0['pos'], c1['pos']) * 100:.2f} m | picture change {diff:.2f} (0 = same picture)")
            return cur

        prev = snap()
        az0 = pg.evaluate(JS_STATE)["az"]
        log(f"[probe] start az {math.degrees(az0):.1f} deg")
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0 + math.pi / 4)
        prev = rep("rotateAzimuthTo(+45, no transition)", prev)
        pg.evaluate("(a) => window.__cc.rotate(a, 0, false)", math.pi / 4)
        prev = rep("rotate(+45, no transition)", prev)
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, true)", az0 + math.pi)
        time.sleep(2.0)
        prev = rep("rotateAzimuthTo(+180, with transition)", prev)
        # 촬영(sweep)이 하는 동작을 하나씩 따라 해서, 어느 동작이 방위각을 되돌리는지 본다
        st = pg.evaluate(JS_STATE)
        tx, ty, tz = st["target"]
        bnd = st["boundary"]
        log(f"[probe] sweep-like test: boundary {bnd}")
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0 + math.pi / 2)
        time.sleep(0.5)
        prev = rep("set az = +90", prev)
        if bnd:
            lo, hi = list(bnd[0]), list(bnd[1])
            lo[1] -= 0.2
            hi[1] += 0.2
            pg.evaluate(JS_SET_BOUNDARY, [lo, hi])
            prev = rep("setBoundary (widened)", prev)
            top = hi[1]
        else:
            top = ty
        pg.evaluate("(p) => window.__cc.moveTo(p[0], p[1], p[2], false)", [tx, top, tz])
        prev = rep("moveTo (top of range)", prev)
        pg.evaluate(JS_HIDE_HL)
        prev = rep("hide highlight meshes", prev)
        pg.evaluate("(p) => window.__cc.moveTo(p[0], p[1], p[2], false)", [tx, ty, tz])
        prev = rep("moveTo (back to centre)", prev)
        if bnd:
            pg.evaluate(JS_SET_BOUNDARY, bnd)
            prev = rep("setBoundary (restored)", prev)
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0)
        time.sleep(0.5)
        pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
        close_focus(pg)
        log("[probe] done")


# ---------------------------------------------------------------- make_refs: 메타 -> photo_refs.json (브라우저 불필요)
def _facing_cos(shot, wall):
    pos = [t * 100 for t in shot["cam"]["pos"]]                      # 장면 단위 -> m
    mx, mz = (wall["p0"][0] + wall["p1"][0]) / 2, (wall["p0"][1] + wall["p1"][1]) / 2
    vx, vz = pos[0] - mx, pos[2] - mz
    hl = math.hypot(vx, vz) or 1.0
    return (vx * wall["normal"][0] + vz * wall["normal"][1]) / hl


def _side_frame(xz, walls):
    """긴 쪽 벽을 정면(front)으로 가정한 평면 좌표계. 정면 = 장면 +z 쪽을 향하는 긴 벽 (street 방향은 모르므로 가정)."""
    L = max(walls, key=lambda w: w["length_m"])
    long_ns = [w["normal"] for w in walls if abs(w["normal"][0] * L["normal"][0] + w["normal"][1] * L["normal"][1]) > 0.9]
    nf = max(long_ns, key=lambda n: n[1] if abs(n[1]) > 0.2 else n[0])
    r = (nf[1], -nf[0])                                               # 모델의 오른쪽(+X) 방향
    return nf, r


def _side_of(n, nf, r):
    c = {"front": nf, "back": (-nf[0], -nf[1]), "right": r, "left": (-r[0], -r[1])}
    return max(c, key=lambda k: n[0] * c[k][0] + n[1] * c[k][1])


def make_refs_one(meta, d, args):
    groups, shots = meta.get("walls") or [], meta.get("shots") or []
    xz = meta.get("footprint_m") or []
    if not groups or not shots:
        log(f"[{meta['dong']}] missing walls or shots - recapture with the current version")
        return None
    if not all("view" in s["cam"] for s in shots):
        log(f"[{meta['dong']}] missing camera matrices - recapture with the current version")
        return None
    walls = reference_walls_of(xz, groups, min_len=args.ref_min_wall,
                               angle_tol=args.ref_plane_deg, offset_tol=args.ref_plane_gap)
    box, dpr = meta["canvas_css"], meta["dpr"]
    g, roof = meta["ground_m"], meta["roof_m"]
    nf, r = _side_frame(xz, groups)
    facades, dbg = [], []
    for w in walls:
        side = _side_of(w["normal"], nf, r)
        cand = []
        for si, s in enumerate(shots):
            if "wall" in s and w["group_i"] is not None and s["wall"] != w["group_i"]:
                continue
            cf = _facing_cos(s, w)
            if cf < args.min_cos:
                continue
            W_, H_ = s["img"]
            mx, my = W_ * args.margin, H_ * args.margin
            N = 240
            ok = []
            for k in range(N + 1):
                y = g + (roof - g) * k / N
                a = project_px(s, [w["p0"][0], y, w["p0"][1]], box, dpr, s["img"])
                b = project_px(s, [w["p1"][0], y, w["p1"][1]], box, dpr, s["img"])
                good = bool(a and b and all(mx <= t[0] <= W_ - mx and my <= t[1] <= H_ - my for t in (a, b)))
                ok.append(good)
            best, run0 = (0, 0), None
            for k, good in enumerate(ok + [False]):
                if good and run0 is None:
                    run0 = k
                if not good and run0 is not None:
                    if k - 1 - run0 > best[1] - best[0]:
                        best = (run0, k - 1)
                    run0 = None
            y0 = g + (roof - g) * best[0] / N
            y1 = g + (roof - g) * best[1] / N
            coverage = min(1.0, (y1 - y0) / (roof - g))
            if y1 - y0 < args.min_h:
                continue
            P = lambda x_, z_, y_: project_px(s, [x_, y_, z_], box, dpr, s["img"])
            pa0, pa1 = P(*w["p0"], y1), P(*w["p0"], y0)
            pb0, pb1 = P(*w["p1"], y1), P(*w["p1"], y0)
            left_is_p0 = pa0[0] < pb0[0]
            TL, BL = (pa0, pa1) if left_is_p0 else (pb0, pb1)
            TR, BR = (pb0, pb1) if left_is_p0 else (pa0, pa1)
            wpx = ((TR[0] - TL[0]) + (BR[0] - BL[0])) / 2
            if wpx < args.min_px:
                continue
            ppm = wpx / w["length_m"]
            score = cf ** 4 * coverage * math.sqrt(ppm)
            cand.append((score, si, s, y0, y1, [TL, TR, BR, BL], ppm, cf, coverage))
        cand.sort(key=lambda c: -c[0])
        for _, si, s, y0, y1, cs, ppm, cf, coverage in cand[: args.per_wall or None]:
            name = f"{meta['dong']}_p{w['i']}_{si + 1}"
            confidence = "high" if cf >= 0.95 else "medium" if cf >= 0.90 else "low"
            facades.append({
                "file": args.prefix + s["file"], "side": side, "name": name,
                "corners": [[round(p[0], 1), round(p[1], 1)] for p in cs],
                "size_m": [round(w["length_m"], 2), round(y1 - y0, 2)],
                "x_m": [0.0, round(w["length_m"], 2)], "z_m": [round(y0 - g, 2), round(y1 - g, 2)],
                "normal_deg": w["azimuth_deg"], "source_wall_i": w["group_i"], "source_plane_i": w["i"],
                "camera_az_deg": s.get("az_deg_actual"), "face_cos": round(cf, 4),
                "visible_fraction": round(coverage, 3), "plane_error_m": w["plane_error_m"],
                "confidence": confidence,
                "paint": {"use_for_color": bool(cf >= 0.95),
                          "reason": "frontal planar view" if cf >= 0.95 else "oblique view: geometry reference only"},
                "paint_exclude": [],
                "_info": f"plane {w['i']} group {w['group_i']} px/m {ppm:.1f} face_cos {cf:.2f}; camera-projected planar homography"})
            dbg.append((s["file"], name, cs))
    # 평면도(위성 대용): 외곽선을 정면이 아래로 오게 그린 이미지
    sat = None
    if xz:
        mpp = args.plan_mpp
        us = [p[0] * r[0] + p[1] * r[1] for p in xz]
        vs = [p[0] * nf[0] + p[1] * nf[1] for p in xz]
        M = 20
        toimg = lambda u, v: ((u - min(us)) / mpp + M, (v - min(vs)) / mpp + M)
        W_ = int((max(us) - min(us)) / mpp + 2 * M)
        H_ = int((max(vs) - min(vs)) / mpp + 2 * M)
        from PIL import ImageDraw
        im = Image.new("RGB", (W_, H_), (235, 235, 235))
        dr = ImageDraw.Draw(im)
        pts = [toimg(u, v) for u, v in zip(us, vs)]
        dr.polygon(pts, fill=(150, 150, 150), outline=(0, 0, 0))
        pf = d / f"{meta['dong']}_plan.png"
        im.save(pf)
        c = [toimg(min(us), max(vs)), toimg(max(us), max(vs)), toimg(max(us), min(vs)), toimg(min(us), min(vs))]
        sat = {"file": args.prefix + pf.name, "corners": [[round(a, 1), round(b, 1)] for a, b in c], "m_per_px": mpp,
               "_note": "plan drawn from the footprint (not a real satellite photo); front = the long wall facing scene +z (ASSUMED, street side unknown)"}
    out = {"_schema": "naver-vr-planar-v2",
           "_help": f"made by naver_vr.py make_refs from camera matrices; dong {meta['dong']}. sides are a guess: check/rename them",
           "_paint": "paint_exclude uses normalized whole-entry wall coordinates: u=[left,right], v=[bottom,top]. Unknown cells stay unpainted.",
           "facades": facades}
    if sat:
        out["satellite"] = sat
    if args.debug:
        from PIL import ImageDraw
        dd = d / "refs_check"
        dd.mkdir(exist_ok=True)
        for fn, nm, cs in dbg:
            im = Image.open(d / fn).convert("RGB")
            dr = ImageDraw.Draw(im)
            dr.line([tuple(p[:2]) for p in cs] + [tuple(cs[0][:2])], fill=(255, 0, 0), width=4)
            for k, p in enumerate(cs):
                dr.text((p[0] + 6, p[1] + 6), "TL TR BR BL".split()[k], fill=(255, 255, 0))
            im.save(dd / f"{nm}.png")
    log(f"[{meta['dong']}] planar refs {len(walls)} -> facades {len(facades)}"
        + "".join(f"  p{w['i']}:{sum(1 for f in facades if f.get('source_plane_i') == w['i'])}" for w in walls))
    return out


def cmd_make_refs(args):
    d = Path(args.dir)
    metas = sorted(d.glob("*_meta.json"))
    want = [s.strip() for s in args.dongs.split(",")] if args.dongs else None
    n = 0
    for mf in metas:
        meta = json.loads(mf.read_text(encoding="utf-8"))
        if "dong" not in meta:
            continue
        if want and meta["dong"] not in want:
            continue
        res = make_refs_one(meta, d, args)
        if res is None:
            continue
        of = Path(args.out) if args.out and len(metas) == 1 else d / f"{meta['dong']}_photo_refs.json"
        of.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  -> {of}")
        n += 1
    if not n:
        sys.exit("만든 파일 없음 (메타가 없거나 옛 버전)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list")
    r = sp.add_parser("run", help="지금 떠 있는 단지")
    b = sp.add_parser("batch", help="여러 단지 URL 차례로")
    b.add_argument("urls", nargs="*")
    b.add_argument("--file", help="URL 목록 파일(한 줄에 하나)")
    for x in (r, b):
        x.add_argument("--overwrite", action="store_true", help="같은 설정으로 완료한 동도 다시 캡처")
        x.add_argument("--fit-wall", action="store_true", help="벽마다 정면으로 찍는다(8방향 대신). 외곽선 데이터가 있어야 함")
        x.add_argument("--wall-frac", type=float, default=None,
                       help="--fit-wall: 면 폭 / 화면 폭으로 더 가까이 (기본: 안 씀 = --width 기준. 0.8 이면 해상도는 높지만 사진 수가 몇 배)")
        x.add_argument("--min-wall", type=float, default=4.0, help="--fit-wall: 이보다 좁은 면(m)은 건너뜀")
        x.add_argument("--wall-group-deg", type=float, default=20.0, help="--fit-wall: 이 각도 안의 같은 방향 변은 한 면으로")
        x.add_argument("--wall-depth-gap", type=float, default=3.0, help="--fit-wall: 깊이 차가 이보다 크면 다른 면(ㄱ자 날개 등)")
        x.add_argument("--overview", action="store_true", help="동 촬영 전에 단지 전체 사진(danji_<k>.png, 글자 숨김)도 찍는다")
        x.add_argument("--overview-angles", type=int, default=4, help="--overview 방향 수")
        x.add_argument("--dongs", help="쉼표로 구분 (기본: 전부)")
        x.add_argument("--width", type=float, default=0.4, help="건물 폭 / 화면 폭")
        x.add_argument("--overlap", type=float, default=0.3)
        x.add_argument("--extra", type=float, default=0.05, help="맨 위·맨 아래를 화면 높이의 이만큼 더 이동")
        x.add_argument("--center", action="store_true",
                       help="이동 범위 중앙에서 한 장만 찍는다(전체 면을 한 프레임에 담을 때)")
        x.add_argument("--angles", type=int, default=None, help="방향 수 (기본 8, --fit-wall 이면 4 = 가장 긴 면 정면부터 90도씩)")
        x.add_argument("--quality", default="고화질", help="화질 버튼 값 (빈 문자열이면 그대로)")
        x.add_argument("--out")
    ov = sp.add_parser("overview", help="단지 전체 사진만 (글자·아이콘·매물 강조 숨김)")
    ov.add_argument("--angles", type=int, default=4, help="방향 수 (4 = 90도씩, 8 = 45도씩)")
    ov.add_argument("--quality", default="고화질")
    ov.add_argument("--out")
    pr = sp.add_parser("probe", help="진단: 회전 방법별로 화면이 실제로 바뀌는지")
    pr.add_argument("--dongs")
    m = sp.add_parser("make_refs", help="찍어 둔 폴더에서 photo_refs.json 만들기 (벽 꼭짓점을 카메라로 투영)")
    m.add_argument("--dir", required=True, help="캡쳐 폴더 (<동>_meta.json 이 있는 곳)")
    m.add_argument("--dongs")
    m.add_argument("--out", help="출력 json (동이 하나일 때만. 기본: <dir>/<동>_photo_refs.json)")
    m.add_argument("--prefix", default="", help="사진 파일 이름 앞에 붙일 경로 (예: photos/)")
    m.add_argument("--min-cos", type=float, default=0.85, help="벽 정면과 카메라 방향의 cos 하한 (0.85 = 약 32도)")
    m.add_argument("--margin", type=float, default=0.02, help="화면 가장자리에서 이만큼 안쪽만 인정")
    m.add_argument("--min-h", type=float, default=6.0, help="한 사진에서 보이는 벽 높이(m) 하한")
    m.add_argument("--min-px", type=float, default=300, help="사진에서 벽 폭(px) 하한")
    m.add_argument("--per-wall", type=int, default=1, help="best N images per exact plane by frontality, coverage and resolution (0 = all)")
    m.add_argument("--ref-min-wall", type=float, default=1.0, help="refs 로 만들 실제 평면의 최소 폭(m)")
    m.add_argument("--ref-plane-deg", type=float, default=2.0, help="연속 변을 같은 평면으로 보는 최대 각도 차이")
    m.add_argument("--ref-plane-gap", type=float, default=0.05, help="연속 변을 같은 평면으로 보는 최대 깊이 오차(m)")
    m.add_argument("--plan-mpp", type=float, default=0.25)
    m.add_argument("--debug", action="store_true", help="refs_check/ 에 꼭짓점을 그린 사진 저장")
    a = ap.parse_args()
    {"list": cmd_list, "run": cmd_run, "batch": cmd_batch, "make_refs": cmd_make_refs, "probe": cmd_probe, "overview": cmd_overview}[a.cmd](a)


if __name__ == "__main__":
    main()
