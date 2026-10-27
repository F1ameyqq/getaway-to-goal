# -*- coding: utf-8 -*-
"""打印答案区每行的 y 范围 + 该行内每块(即每题答案)的 x 范围。
用法: ans_dump.py <图> <S> <X0> <X1> <Y0> <Y1> [TH] [MIN_INK]
"""
import sys
from PIL import Image
import numpy as np

path = sys.argv[1]
S = float(sys.argv[2])
X0, X1 = float(sys.argv[3]), float(sys.argv[4])
Y0, Y1 = float(sys.argv[5]), float(sys.argv[6])
TH = int(sys.argv[7]) if len(sys.argv) > 7 else 225
MIN_INK = int(sys.argv[8]) if len(sys.argv) > 8 else 2
GAP_CSS = 4.0

im = Image.open(path).convert("L")
a = np.array(im)
px = lambda v: int(round(v * S))
sub = a[px(Y0):px(Y1), px(X0):px(X1)]
ink_r = (sub < TH).sum(axis=1)
raw, cur = [], None
for i, v in enumerate(ink_r):
    if v > MIN_INK:
        cur = [i, i] if cur is None else [cur[0], i]
    else:
        if cur is not None:
            raw.append(cur); cur = None
if cur:
    raw.append(cur)
merged = []
for r in raw:
    if merged and r[0] - merged[-1][1] <= 4:
        merged[-1][1] = r[1]
    else:
        merged.append(list(r))
keep = [r for r in merged if (r[1] - r[0]) / S >= 2.0]

for i, (ra, rb) in enumerate(keep):
    band = sub[ra:rb + 1]
    ink_c = (band < TH).sum(axis=0)
    segs, c2 = [], None
    for k, v in enumerate(ink_c):
        if v > 0:
            c2 = [k, k] if c2 is None else [c2[0], k]
        else:
            if c2 is not None:
                segs.append(c2); c2 = None
    if c2:
        segs.append(c2)
    bl = []
    for s in segs:
        if bl and s[0] - bl[-1][1] < GAP_CSS * S:
            bl[-1][1] = s[1]
        else:
            bl.append(list(s))
    y0, y1 = Y0 + ra / S, Y0 + rb / S
    xs = " ".join("[%.1f,%.1f]" % (X0 + b[0] / S, X0 + b[1] / S) for b in bl)
    print("A%02d y=%.1f-%.1f blocks=%d %s" % (i, y0, y1, len(bl), xs))
