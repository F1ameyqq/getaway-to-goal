# -*- coding: utf-8 -*-
"""
整栏 + 行号标尺，分上下两半输出。用来一次看清整栏的题目分组。
行号规则与 qmeasure.py 一致（同一套 TH/MIN_INK/MIN_H 过滤）。
"""
import sys, os, io, json
from PIL import Image, ImageDraw
import numpy as np

# 输出目录取 config.json 的 paths.srcDir（相对本文件所在目录）
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    with io.open(os.path.join(HERE, "config.json"), encoding="utf-8") as _f:
        _cfg = json.load(_f)
    SRC_DIR = os.path.join(HERE, (_cfg.get("paths") or {}).get("srcDir") or "srcpages")
except FileNotFoundError:
    SRC_DIR = os.path.join(HERE, "srcpages")
os.makedirs(SRC_DIR, exist_ok=True)

path, S = sys.argv[1], float(sys.argv[2])
tag, X0, X1 = sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
# 可选: TH MIN_INK Y0 Y1（答案区用 225 2 10 200）
rest = [float(x) for x in sys.argv[6:10]]
TH = int(rest[0]) if len(rest) > 0 else 200
MIN_INK = int(rest[1]) if len(rest) > 1 else 20
Y0 = rest[2] if len(rest) > 2 else 20.0
Y1 = rest[3] if len(rest) > 3 else 660.0
MIN_H = 2.0
LAB = 40


def px(v):
    return int(round(v * S))


im = Image.open(path).convert("L")
a = np.array(im)
sub = a[px(Y0):px(Y1), px(X0):px(X1)]
ink_r = (sub < TH).sum(axis=1)
rows, cur = [], None
for i, v in enumerate(ink_r):
    if v > MIN_INK:
        cur = [i, i] if cur is None else [cur[0], i]
    else:
        if cur is not None:
            rows.append(cur); cur = None
if cur:
    rows.append(cur)
merged = []
for r in rows:
    if merged and r[0] - merged[-1][1] <= 4:
        merged[-1][1] = r[1]
    else:
        merged.append(list(r))
keep = [r for r in merged if (r[1] - r[0]) / S >= MIN_H]

base = Image.fromarray(sub).convert("RGB")
full = Image.new("RGB", (base.width + LAB, base.height), "white")
full.paste(base, (LAB, 0))
d = ImageDraw.Draw(full)
for i, r in enumerate(keep):
    d.text((2, r[0] + 2), "%02d" % i, fill=(200, 0, 0))
    d.line([(LAB, r[0]), (LAB + 8, r[0])], fill=(0, 160, 0), width=1)
    d.line([(LAB, r[1]), (LAB + 8, r[1])], fill=(0, 120, 220), width=1)

# 输出名带源图前缀，否则录下一页时会把上一页的栏图覆盖掉
stem = os.path.splitext(os.path.basename(path))[0]
for i, (ya, yb) in enumerate([(0, full.height // 2), (full.height // 2, full.height)]):
    full.crop((0, ya, full.width, yb)).save(
        os.path.join(SRC_DIR, "%s_col_%s_%d.png" % (stem, tag, i)))
print("%s rows=%d out %dx%d -> %s" % (tag, len(keep), full.width, full.height, os.path.join(SRC_DIR, "%s_col_%s_*.png" % (stem, tag))))
