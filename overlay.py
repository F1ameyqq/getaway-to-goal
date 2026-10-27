# -*- coding: utf-8 -*-
"""在截图上画出 measure_page.py 生成的框，供目视复核。
用法: overlay.py <图.jpg> <坐标.json> <输出.png> [q|a]
q=题目区(canvas 519.778x669.1)  a=答案区(436.708x669.0)
"""
import sys, json, io
from PIL import Image, ImageDraw

path, js, out = sys.argv[1], sys.argv[2], sys.argv[3]
kind = sys.argv[4] if len(sys.argv) > 4 else "q"
CANVAS_W = 519.7784108488579 if kind == "q" else 436.7083435058594
SRC_W = 1220.0 if kind == "q" else 1145.0
SRC_H = 1693.0 if kind == "q" else 1620.0
s_src = min(CANVAS_W / SRC_W, 669.0 / SRC_H)
pad_x = (CANVAS_W - SRC_W * s_src) / 2.0
pad_y = (669.0 - SRC_H * s_src) / 2.0

im = Image.open(path).convert("RGB")
SS = im.width / CANVAS_W
raw = json.load(io.open(js, encoding="utf-8"))
# 两种都收：measure_page.py 的纯数组，或 pages/pNN.json 的 {items:[...]}
items = raw if isinstance(raw, list) else raw["items"]
d = ImageDraw.Draw(im)


def to_px(b):
    return [(b[0] * s_src + pad_x) * SS, (b[1] * s_src + pad_y) * SS,
            (b[2] * s_src + pad_x) * SS, (b[3] * s_src + pad_y) * SS]


for it in items:
    for b in it.get("q", []):
        d.rectangle(to_px(b), outline=(220, 0, 0), width=3)
        d.text((to_px(b)[0] + 4, to_px(b)[1] + 2), "q%d" % it["n"], fill=(220, 0, 0))
    for b in it.get("w", []):
        d.rectangle(to_px(b), outline=(0, 120, 220), width=2)

im.save(out)
print("overlay -> %s  %dx%d  items=%d" % (out, im.width, im.height, len(items)))
