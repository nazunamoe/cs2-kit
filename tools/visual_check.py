"""Load each visual-check asset/photo once and share warps and elevation renders.

Walls are checked in parallel on a thread pool; the printed lines and the files left in previews/ are the
same as a one-by-one run. Set VISUAL_SERIAL=1 to run the walls one at a time (debugging)."""
import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proj import ROOT  # noqa: E402
from objio import load_asset  # noqa: E402
from render import Tex  # noqa: E402
from extract_texture import warp  # noqa: E402
import elevation_cache as EC  # noqa: E402
import photo_check as PC  # noqa: E402
import tile_compare as TC  # noqa: E402


def p(value):
    sys.stdout.write(value.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--refs", default=os.path.join(ROOT, "photo_refs.json"))
    parser.add_argument("--tiles", action="store_true")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()
    with open(args.refs, encoding="utf-8-sig") as f:
        import json
        refs = json.load(f)
    jobs = ([('satellite', refs['satellite'])] if refs.get("satellite") else []) + [
        (ref.get("side", "front"), ref) for ref in refs.get("facades", [])]
    if not jobs:
        p("[visual] FAIL: no satellite or facade checks")
        sys.exit(2)
    base = os.path.dirname(os.path.abspath(args.refs))
    asset, meshes, texdir, manifest = load_asset(args.path)
    tex = Tex(texdir, asset, False, "color")
    tiles_root = os.path.join(ROOT, "previews", "tiles")

    def run_job(job):
        """One wall: warp the photo, fetch the model view, run the photo and tile checks.
        Returns (photo_lines, tile_lines, photo_failed, tile_failed, deferred image writes)."""
        name, ref = job
        photo_lines, tile_lines, saves = [], [], []
        photo_failed = tile_failed = 0
        PC._SAVE.sink = lambda im, path: saves.append((path, im))
        try:
            img = Image.open(os.path.join(base, ref["file"])).convert("RGB")
            if name == "satellite":
                Wm, Hm = PC.extents(meshes, "top")
                box = None
            else:
                Wm, Hm, box = PC.wall_measure(ref, meshes, name, manifest)
            corners = ref["corners"]
            if name == "satellite":
                corners = [corners[3], corners[2], corners[1], corners[0]]
            w30, h30 = int(Wm * 30), int(Hm * 30)
            photo30 = warp(img, corners, w30, h30)
            yaw, pitch = (0, 90) if name == "satellite" else (PC.wall_yaw(ref, name, manifest), 0)
            model = TC.model_crop(meshes, tex, yaw, pitch, 2200, box=box)
            model30 = model.resize((w30, h30))
            w20, h20 = int(Wm * PC.PX_PER_M), int(Hm * PC.PX_PER_M)
            prepared = (photo30.resize((w20, h20)), model30.resize((w20, h20)))
            try:
                if name == "satellite":
                    photo_lines += PC.check_satellite(ref, meshes, tex, base, prepared=prepared)
                else:
                    photo_lines += PC.check_facade(ref, meshes, tex, base, prepared=prepared, manifest=manifest)
            except Exception as exc:  # noqa
                photo_failed += 1
                photo_lines.append(f"INFO     {name} photo check failed: {exc}")
            if args.tiles:
                try:
                    tile_lines += TC.run_wall(name, photo30, model30, 30, (15, 15) if name == "satellite" else (10, 9),
                                              args.top, os.path.join(tiles_root, name), Wm, Hm)
                except Exception as exc:  # noqa
                    tile_failed += 1
                    tile_lines.append(f"INFO tiles {name} failed: {exc}")
        except Exception as exc:  # noqa
            photo_failed += 1
            tile_failed += int(args.tiles)
            photo_lines.append(f"INFO     {name} preparation failed: {exc}")
        finally:
            PC._SAVE.sink = None
        return photo_lines, tile_lines, photo_failed, tile_failed, saves

    def write(item):
        path, im = item
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        im.save(path, compress_level=PC.PNG_LEVEL)

    # Walls are independent and the heavy steps (decode, warp, resize, filters, numpy) release the GIL,
    # so they run on a thread pool sharing one asset/texture. Results are merged in job order, and image
    # writes are deferred: when several walls target the same file only the last one (the file a serial
    # run would leave behind) is encoded.
    workers = 1 if os.environ.get("VISUAL_SERIAL") == "1" else max(1, min(len(jobs), os.cpu_count() or 2))
    for mesh in meshes.values():                      # hash once up front instead of racing in the workers
        EC._mesh_hash(mesh)
    EC._texture_hash(tex)
    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_job, jobs))
            final = {}
            for result in results:
                for path, im in result[4]:
                    final[os.path.normcase(os.path.abspath(path))] = (path, im)
            list(pool.map(write, final.values()))
    else:
        results = [run_job(job) for job in jobs]
        final = {}
        for result in results:
            for path, im in result[4]:
                final[os.path.normcase(os.path.abspath(path))] = (path, im)
        for item in final.values():
            write(item)
    photo_lines = [line for r in results for line in r[0]]
    tile_lines = [line for r in results for line in r[1]]
    photo_failed = sum(r[2] for r in results)
    tile_failed = sum(r[3] for r in results)
    mismatch = sum(line.startswith("MISMATCH") for line in photo_lines)
    photo_status = "FAIL" if photo_failed or mismatch else "PASS"
    tile_status = "NOT_CHECKED" if not args.tiles else "FAIL" if tile_failed else "PASS"
    p(f"[photo] status={photo_status} mismatch={mismatch} checks={len(jobs)} failed={photo_failed}")
    for line in photo_lines:
        p("   " + line)
    p(f"[tiles] status={tile_status}")
    for line in tile_lines:
        p("   " + line)
    p(f"[visual] photo_status={photo_status} tile_status={tile_status} checks={len(jobs)} "
      f"photo_failed={photo_failed} tile_failed={tile_failed}")
    sys.exit(2 if photo_failed or tile_failed else 1 if mismatch else 0)


if __name__ == "__main__":
    main()
