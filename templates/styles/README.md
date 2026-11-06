# Facade styles

`templates/facade_style.py` loads these YAML files. A project generator keeps
its mass and wall roles; a style supplies repeatable finish decisions:

- `palette`: material colours
- `window`: size, frame, glass, night policy
- `layers`: band/spandrel/frame/louver dimensions
- `night`: white/scattered light policy
- `zones`: intended facade treatment notes

## Use in a generator

```python
from templates.facade_style import load_style

STYLE = load_style(os.path.join(KIT, "templates", "styles", "apartment_2020_lightstone.yaml"))
SILL = STYLE.win("sill_m", 0.85)
WIN_W = STYLE.win("width_m", 1.85)
wall_color = STYLE.color("wall")
band_h = STYLE.layer("band_height_m", 0.18)
night_ratio = STYLE.night_value("lit_ratio", 0.38)
```

Geometry, floor count, bay counts, and wall roles stay project-specific.
Do not put real brand names, logos, or sign text in a style.

## Tools

```bash
python tools/style_catalog.py --project P --json
python tools/style_catalog.py --project P --validate
python tools/brief.py --project P --text "2010s slab apartment 25 floors" --json
```

`tools/brief.py` is a deterministic parser/scaffold, not an LLM call. A
DeepSeek parser can fill the same `building_brief.yaml` schema later; the
geometry still has to pass quick/visual/final.

## Adding a style

1. Copy an existing YAML under `templates/styles/`.
2. Set `id`, `era`, `type`, `tags`.
3. Fill palette/window/layers/night.
4. Run `python tools/style_catalog.py --project P --validate`.
5. Use it in a project generator or brief.
