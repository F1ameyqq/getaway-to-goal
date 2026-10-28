# -*- coding: utf-8 -*-
"""Reproduce build_q stem/block logic for one column to explain low flags."""
import sys, os
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import propose_spec as P

img_path = sys.argv[1]
x0, x1 = float(sys.argv[2]), float(sys.argv[3])
kind = "q"
im = Image.open(img_path)
gray = np.array(im.convert("L"))
rgb = im.convert("RGB")
SS = im.width / P.CANVAS[kind][0]
Y0, Y1 = 20.0, 660.0
TH, MIN_INK = 200, 20
rows = P.detect_rows(gray, Y0, Y1, x0, x1, TH, MIN_INK, SS, P.GAP_CSS, P.MIN_H)

narrow = P.ocr_strip(rgb, x0, min(x1, x0 + 55.0), Y0, Y1, SS)
full = P.ocr_strip(rgb, x0, x1, Y0, Y1, SS)

anchors = []
for d in narrow:
    m = P.NUM_RE.match(d["text"])
    if m and (d["x0"] - x0) < 25.0:
        anchors.append({"n": int(m.group(1)), "conf": d["conf"], "y": P.yc(d), "x0": d["x0"], "text": d["text"]})
anchors.sort(key=lambda a: a["y"])
dedup = []
for a in anchors:
    if dedup and abs(a["y"] - dedup[-1]["y"]) < 12 and a["n"] == dedup[-1]["n"]:
        if a["conf"] > dedup[-1]["conf"]:
            dedup[-1] = a
        continue
    dedup.append(a)
anchors = dedup

letters_by_row = {}
for d in narrow + full:
    lets = P.OPT_IN_TEXT.findall(d["text"])
    if not lets:
        continue
    r = P.row_for_top(d["y0"], rows)
    letters_by_row.setdefault(r, set()).update(L.upper() for L in lets)

print("anchors:", [(a["n"], round(a["y"], 1), P.row_of(a["y"], rows)) for a in anchors])
for ai, a in enumerate(anchors):
    arow = P.row_of(a["y"], rows)
    nxt_row = P.row_of(anchors[ai + 1]["y"], rows) if ai + 1 < len(anchors) else len(rows)
    block_end = arow
    for r in range(arow, nxt_row - 1):
        g = rows[r + 1]["y0"] - rows[r]["y1"]
        if g > P.GAP_SPLIT:
            print("  n=%d block break at r=%d gap=%.1f" % (a["n"], r, g))
            break
        block_end = r + 1
    else:
        block_end = nxt_row - 1
    opt_rows = sorted(r for r in letters_by_row if arow <= r <= block_end)
    first_opt = None
    for r in opt_rows:
        if r > arow:
            first_opt = r
            break
    stem_end = (first_opt - 1) if first_opt is not None else block_end
    print("n=%d arow=%d block_end=%d first_opt=%r stem_end=%d" % (a["n"], arow, block_end, first_opt, stem_end))
    if stem_end >= arow:
        for r in range(arow, stem_end):
            g = rows[r + 1]["y0"] - rows[r]["y1"]
            flag = " >SPLIT" if g > P.GAP_SPLIT else (" >55" if g > 55 else "")
            print("   gap r%d->r%d = %.1f%s" % (r, r + 1, g, flag))
