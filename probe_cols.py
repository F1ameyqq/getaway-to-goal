# -*- coding: utf-8 -*-
"""打印列投影的低墨区间，用来找双栏页的中缝。
阈值按整页墨量的分位数自适应，避免纸纹把每列都填满。"""
import sys
from PIL import Image
import numpy as np

path, s = sys.argv[1], float(sys.argv[2])
TH = int(sys.argv[3]) if len(sys.argv) > 3 else 210
im = Image.open(path).convert("L")
a = np.array(im)
S = s
ink_c = (a < TH).sum(axis=0)
print("W=%d H=%d s=%.3f css=%.1fx%.1f" % (im.width, im.height, S, im.width / S, im.height / S))
print("ink_c: min=%d p10=%d median=%d p90=%d max=%d" % (
    ink_c.min(), np.percentile(ink_c, 10), np.median(ink_c), np.percentile(ink_c, 90), ink_c.max()))
# 低于 p15 分位当作"近空白列"
lim = max(2, int(np.percentile(ink_c, 15)))
runs, cur = [], None
for i, v in enumerate(ink_c):
    if v <= lim:
        cur = [i, i] if cur is None else [cur[0], i]
    else:
        if cur is not None:
            runs.append(cur); cur = None
if cur:
    runs.append(cur)
print("lim=%d  bands(width>=3css):" % lim)
for r in runs:
    if (r[1] - r[0]) / S >= 3:
        print("  css x %.1f - %.1f  (w=%.1f)" % (r[0] / S, r[1] / S, (r[1] - r[0]) / S))
