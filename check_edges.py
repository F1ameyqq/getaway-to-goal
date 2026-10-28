# -*- coding: utf-8 -*-
"""边框审计：每个框外面再套一圈 1.2 CSS 宽的环，看环里有没有墨迹。

有墨迹 = 框把内容切掉了一截（overlay 上很难看出来，尤其是括号、分数线这种淡笔画）。
只在「框的边界就是要切的地方」时才有用 —— 相邻的选项框之间本来就有空白，
所以本脚本只报环内墨迹，不给结论，自己看坐标。

用法:
  python -I check_edges.py <pages/pNN.json> [<qspec> <aspec>]
"""
import io, json, sys
import numpy as np
from PIL import Image

CANVAS = {"q": (519.7784108488579, 669.1), "a": (436.7083435058594, 669.0)}
SRC = {"q": (1220.0, 1693.0), "a": (1145.0, 1620.0)}

page_path = sys.argv[1]
specs = sys.argv[2:]
page = json.load(io.open(page_path, encoding="utf-8"))

imgs = {}
for sp in specs:
    spec = json.load(io.open(sp, encoding="utf-8"))
    imgs[spec["kind"]] = (spec["src"], spec.get("nop"))


def load(kind):
    if kind in imgs:
        src = imgs[kind][0]
    else:
        raise SystemExit("缺 %s 的 spec" % kind)
    im = Image.open(src).convert("L")
    arr = np.array(im)
    SS = im.width / CANVAS[kind][0]
    s_src = min(CANVAS[kind][0] / SRC[kind][0], CANVAS[kind][1] / SRC[kind][1])
    pad_x = (CANVAS[kind][0] - SRC[kind][0] * s_src) / 2.0
    pad_y = (CANVAS[kind][1] - SRC[kind][1] * s_src) / 2.0
    return arr, SS, s_src, pad_x, pad_y


def to_px(b, s_src, pad_x, pad_y, SS):
    x0 = (b[0] * s_src + pad_x) * SS
    x1 = (b[2] * s_src + pad_x) * SS
    y0 = (b[1] * s_src + pad_y) * SS
    y1 = (b[3] * s_src + pad_y) * SS
    return x0, y0, x1, y1


M = 1.2  # 环宽（CSS 像素）
cache = {}
bad = 0
for it in page["items"]:
    for key in ("q", "w", "a"):
        kind = "a" if key == "a" else "q"   # 选项框和题目框在同一张图上
        for b in it.get(key, []):
            if kind not in cache:
                cache[kind] = load(kind)
            arr, SS, s_src, pad_x, pad_y = cache[kind]
            x0, y0, x1, y1 = to_px(b, s_src, pad_x, pad_y, SS)
            m = M * SS
            X0, Y0 = int(max(0, x0 - m)), int(max(0, y0 - m))
            X1, Y1 = int(min(arr.shape[1], x1 + m)), int(min(arr.shape[0], y1 + m))
            if X1 <= X0 or Y1 <= Y0:
                continue
            sub = arr[Y0:Y1, X0:X1]
            bb = np.zeros_like(sub, dtype=bool)
            ix0, iy0 = int(x0) - X0, int(y0) - Y0
            ix1, iy1 = int(x1) - X0, int(y1) - Y0
            bb[max(0, iy0):max(0, iy1), max(0, ix0):max(0, ix1)] = True
            ring = (sub < 200) & (~bb)
            n = int(ring.sum())
            if n >= 20:
                bad += 1
                print("EDGE n=%-2d %s [%.0f,%.0f,%.0f,%.0f] ring_ink=%d" % (it["n"], kind, x0, y0, x1, y1, n))
print("EDGE_TOTAL %d" % bad)
