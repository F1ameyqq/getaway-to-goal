# -*- coding: utf-8 -*-
"""Dump rows/blocks/OCR for a given image+column, to pick numeric thresholds."""
import sys, os, io
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import propose_spec as P

img_path = sys.argv[1]
x0, x1 = float(sys.argv[2]), float(sys.argv[3])
y0, y1 = float(sys.argv[4]), float(sys.argv[5])
kind = sys.argv[6] if len(sys.argv) > 6 else "q"

im = Image.open(img_path)
gray = np.array(im.convert("L"))
rgb = im.convert("RGB")
SS = im.width / P.CANVAS[kind][0]
TH = 200 if kind == "q" else 225
MIN_INK = 20 if kind == "q" else 2

rows = P.detect_rows(gray, y0, y1, x0, x1, TH, MIN_INK, SS, P.GAP_CSS, P.MIN_H)
print("== %s x=[%s,%s] y=[%s,%s] SS=%.3f rows=%d" % (kind, x0, x1, y0, y1, SS, len(rows)))

narrow = P.ocr_strip(rgb, x0, min(x1, x0 + 55.0), y0, y1, SS)
full = P.ocr_strip(rgb, x0, x1, y0, y1, SS)

for i, r in enumerate(rows):
    gap = (rows[i + 1]["y0"] - r["y1"]) if i + 1 < len(rows) else float("nan")
    # narrow OCR text whose y-center is inside this row
    txts = [d["text"] for d in narrow if r["y0"] - 2 <= P.yc(d) <= r["y1"] + 2]
    ftxts = [d["text"] for d in full if r["y0"] - 2 <= P.yc(d) <= r["y1"] + 2]
    print("R%02d y=[%.1f,%.1f] gap=%.1f blocks=%s narrow=%r full=%r" % (
        i, r["y0"], r["y1"], gap, r["blocks"], txts, ftxts))
