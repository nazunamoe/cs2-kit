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
  if (window.__scene) return res(true);
  let target = null, P = Object.getPrototypeOf(cc.camera);
  while (P && P !== Object.prototype) { if (Object.prototype.hasOwnProperty.call(P, 'updateMatrixWorld')) target = P; P = Object.getPrototypeOf(P); }
  const orig = target.updateMatrixWorld;
  target.updateMatrixWorld = function (f) { if (this.isScene) window.__scene = this; return orig.call(this, f); };
  cc.rotate(0.0002, 0, true); setTimeout(() => cc.rotate(-0.0002, 0, true), 250);
  setTimeout(() => { target.updateMatrixWorld = orig; res(!!window.__scene); }, 1200); })
"""
# 매물 층 강조(파랑 #0a7df3, 보라 #c759d4 등 반투명 0.3 판) 숨기기 - 색과 상관없이 반투명 메시 전부
JS_HIDE_HL = r"""
() => { let n = 0; if (!window.__scene) return -1;
  window.__scene.traverse(o => { const m = Array.isArray(o.material) ? o.material[0] : o.material;
    if (o.isMesh && m && m.color && m.transparent && m.opacity < 0.9) { if (o.visible) n++; o.visible = false; } });
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
() => { const c = window.__cc.camera; c.updateMatrixWorld(); const d = new c.position.constructor(); c.getWorldDirection(d);
  return {pos: c.position.toArray(), dir: d.toArray(), fov: c.fov, aspect: c.aspect}; }
"""
JS_SET_BOUNDARY = r"""
(b) => { const cc = window.__cc, B = cc._boundary;
  const box = new B.constructor(new B.min.constructor(...b[0]), new B.max.constructor(...b[1]));
  cc.setBoundary(box); }
"""


def sweep(pg, box, out, name, n0, overlap, extra, shots):
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
    step = scr_h * (1 - overlap)
    n, y, last = n0, ytop, None
    try:
        while True:
            pg.evaluate("(p) => window.__cc.moveTo(p[0], p[1], p[2], false)", [tx, max(y, ybot), tz])
            pg.evaluate(JS_HIDE_HL)
            kick(pg)
            real = pg.evaluate(JS_STATE)["target"][1]
            if last is not None and abs(real - last) < 1e-5:  # 더 안 내려감
                break
            f = out / f"{name}_side{n}.png"
            stable_shot(pg, box).save(f)
            # 카메라 기록(장면 단위 = m/100): 나중에 벽 꼭짓점을 사진에 투영해 photo_refs 를 만들 때 쓴다
            shots.append({"file": f.name, "target_y": round(real, 6), "cam": pg.evaluate(JS_CAM)})
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


def overview(pg, out, n=4):
    """단지 전체 보기 n 방향(90도씩) -> danji_<k>.png. 동 라벨·매물 수·시설 라벨(DOM)과 매물 층 강조 메시를 숨긴다."""
    import math
    box = canvas_box(pg)
    for k in range(1, n + 1):
        wait_rest(pg)
        pg.add_style_tag(content=CSS_HIDE)
        pg.evaluate(JS_HIDE_HL)
        kick(pg)
        stable_shot(pg, box).save(out / f"danji_{k}.png")
        pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
        pg.evaluate("(a) => window.__cc.rotate(a, 0, false)", 2 * math.pi / n)
    log(f"[overview] {n} shots -> danji_1..{n}.png")


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
    if os.environ.get("OVERVIEW") == "1":                # off by default: rotating the full view upset the dong captures
        try:
            overview(pg, out)
        except Exception as ex:
            log(f"[overview] ERROR {type(ex).__name__}: {str(ex).splitlines()[0][:200]}")
            pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
    done, failed = [], []
    for q in pois:
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
    box = canvas_box(pg)
    vh = pg.evaluate("innerHeight")
    dpr = pg.evaluate("devicePixelRatio")
    az0 = st["az"]
    meta = {"complex": d["id"], "dong": name, "floors": q.get("floor", {}).get("maxFloor"),
            "height_m": round((yhi - ylo) * 100, 2), "dist_m": round(dist * 100, 2), "fov_v_deg": st["fov"],
            "width_frac": round(w, 3), "canvas_css": box, "dpr": dpr,
            # 타깃(건물 중심) 거리 평면에서의 축척. 앞 벽은 더 가까워 이보다 조금 크다
            "px_per_m_at_target": round(vh * dpr / (2 * dist * 100 * math.tan(math.radians(st["fov"]) / 2)), 3),
            "shots": []}
    n = 1
    try:
        for k in range(args.angles):
            ang = round(k * 360 / args.angles)
            pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0 - math.radians(ang))
            time.sleep(0.4)
            real_az = pg.evaluate(JS_STATE)["az"]
            if k and abs((real_az - az0) + math.radians(ang)) > 0.02:
                log(f"[{name}] WARN 방위각이 안 돌아감 (want {-ang}, got {math.degrees(real_az - az0):.1f})")
            shots = []
            n1 = sweep(pg, box, out, name, n, args.overlap, args.extra, shots)
            for s in shots:
                s["angle_deg"] = ang
            meta["shots"] += shots
            log(f"[{name}] {ang:3d} deg  side{n}~side{n1 - 1}")
            n = n1
        pg.evaluate("(a) => window.__cc.rotateAzimuthTo(a, false)", az0)  # 처음 각도로
        time.sleep(0.5)
    finally:
        pg.evaluate("() => document.querySelectorAll('style').forEach(s => { if (s.textContent.startsWith('body *{visibility:hidden')) s.remove(); })")
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
            if (out / "DONE").exists():
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
                (out / "DONE").write_text(json.dumps({"ok": done, "fail": failed}, ensure_ascii=False), encoding="utf-8")
                summary.append((cid, f"ok {len(done)} fail {failed}"))
            except Exception as ex:
                log(f"[{cid}] ERROR {type(ex).__name__}: {str(ex).splitlines()[0][:200]}")
                summary.append((cid, "error"))
        log("[batch summary]")
        for cid, s in summary:
            log(f"  {cid}: {s}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list")
    r = sp.add_parser("run", help="지금 떠 있는 단지")
    b = sp.add_parser("batch", help="여러 단지 URL 차례로")
    b.add_argument("urls", nargs="*")
    b.add_argument("--file", help="URL 목록 파일(한 줄에 하나)")
    for x in (r, b):
        x.add_argument("--dongs", help="쉼표로 구분 (기본: 전부)")
        x.add_argument("--width", type=float, default=0.4, help="건물 폭 / 화면 폭")
        x.add_argument("--overlap", type=float, default=0.3)
        x.add_argument("--extra", type=float, default=0.05, help="맨 위·맨 아래를 화면 높이의 이만큼 더 이동")
        x.add_argument("--angles", type=int, default=8)
        x.add_argument("--quality", default="고화질", help="화질 버튼 값 (빈 문자열이면 그대로)")
        x.add_argument("--out")
    a = ap.parse_args()
    {"list": cmd_list, "run": cmd_run, "batch": cmd_batch}[a.cmd](a)


if __name__ == "__main__":
    main()
