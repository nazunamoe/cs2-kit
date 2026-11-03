# -*- coding: utf-8 -*-
"""Launcher example. Data: facade_slab_wing_data.py, machinery: facade_engine.py (kit root)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import facade_slab_wing_data as D  # noqa: E402  (also puts the kit root on sys.path)
import facade_engine as E  # noqa: E402

if __name__ == "__main__":
    print("WROTE", E.run(D.tower, atlas=D.atlas_extra))
