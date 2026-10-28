# -*- coding: utf-8 -*-
"""For each row, measure how far ink extends above y0 and below y1 within [x0,x1]."""
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
SS = im.width / P.CANVAS[kind][0]
rows = P.detect_rows(gray, 20.0, 660.0, x0, x1, 200, 20, SS, P.GAP_CSS, P.MIN_H)

for i, r in enumerate(rows):
    up_gap = (r["y0"] - rows[i-1]["y1"]) if i > 0 else 999
    dn_gap = (rows[i+1]["y0"] - r["y1"]) if i+1 < len(rows) else 999
    X0 = int(r["blocks"][0][0] * SS); X1 = int(max(b[1] for b in r["blocks"]) * SS)
    win_y0 = int((r["y0"] - min(up_gap/2, 15)) * SS)
    win_y1 = int((r["y1"] + min(dn_gap/2, 15)) * SS)
    win_y0 = max(0, win_y0); win_y1 = min(gray.shape[0], win_y1)
    sub = gray[win_y0:win_y1, X0:X1]
    ys = np.where((sub < 200).any(axis=1))[0]
    if ys.size == 0:
        print("R%02d y=[%.1f,%.1f] up_gap=%.1f dn_gap=%.1f NO_INK" % (i, r["y0"], r["y1"], up_gap, dn_gap))
        continue
    ink_y0 = (win_y0 + ys[0]) / SS
    ink_y1 = (win_y0 + ys[-1] + 1) / SS
    print("R%02d y=[%.1f,%.1f] up_gap=%.1f dn_gap=%.1f ink=[%.1f,%.1f] over_up=%.1f over_dn=%.1f" % (
        i, r["y0"], r["y1"], up_gap, dn_gap, ink_y0, ink_y1,
        r["y0"] - ink_y0, ink_y1 - r["y1"]))
