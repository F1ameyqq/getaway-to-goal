# -*- coding: utf-8 -*-
"""在截图上画出 measure_page.py 生成的框，供目视复核。

用法: overlay.py <图.jpg> <坐标.json> <输出.png> [q|a]
  q = 题目区(canvas 519.778x669.1)  a = 答案区(canvas 436.708x669.0)

颜色/标签（每页只需看这一张图）:
  q   红框  q12       题目框
  w   蓝框  w13:1..4  选项框（同一题多个时带序号）
  a   绿框  a15       答案框（kind=a 时 measure 输出里的 q 就是答案）

两种 JSON 都收：measure_page.py 的纯数组，或 pages/pNN.json 的 {items:[...]}。
"""
import sys, json, io, os
from PIL import Image, ImageDraw, ImageFont

path, js, out = sys.argv[1], sys.argv[2], sys.argv[3]
kind = sys.argv[4] if len(sys.argv) > 4 else "q"
# --crop auto: 只保留所有框的外接区域（+80px 边距）。答案页整页图里框往往只占一小块，
# 裁掉后视觉 token 能省一半以上；题目页框铺满整页，不加这个参数。
CROP_AUTO = "--crop" in sys.argv and "auto" in sys.argv
CANVAS_W = 519.7784108488579 if kind == "q" else 436.7083435058594
SRC_W = 1220.0 if kind == "q" else 1145.0
SRC_H = 1693.0 if kind == "q" else 1620.0
s_src = min(CANVAS_W / SRC_W, 669.0 / SRC_H)
pad_x = (CANVAS_W - SRC_W * s_src) / 2.0
pad_y = (669.0 - SRC_H * s_src) / 2.0

im = Image.open(path).convert("RGB")
SS = im.width / CANVAS_W
raw = json.load(io.open(js, encoding="utf-8"))
items = raw if isinstance(raw, list) else raw["items"]
d = ImageDraw.Draw(im)

FS = max(16, int(round(6.0 * SS)))
FONT_PATH = next(
    (f for f in (
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ) if os.path.exists(f)),
    None,
)
try:
    fnt = ImageFont.truetype(FONT_PATH, FS) if FONT_PATH else ImageFont.load_default(size=FS)
except TypeError:  # Pillow < 10.1
    fnt = ImageFont.load_default()

COLORS = {
    "q": (220, 0, 0),
    "w": (0, 110, 220),
    "a": (0, 130, 0),
}


def to_px(b):
    return [
        (b[0] * s_src + pad_x) * SS,
        (b[1] * s_src + pad_y) * SS,
        (b[2] * s_src + pad_x) * SS,
        (b[3] * s_src + pad_y) * SS,
    ]


def label(x, y, text, color):
    bb = d.textbbox((x + 4, y + 2), text, font=fnt)
    d.rectangle([bb[0] - 2, bb[1] - 1, bb[2] + 2, bb[3] + 1], fill=(255, 255, 255))
    d.text((x + 4, y + 2), text, font=fnt, fill=color)


BOXES = []


def draw_boxes(n, boxes, key, label_key):
    for i, b in enumerate(boxes):
        p = to_px(b)
        d.rectangle(p, outline=COLORS[key], width=3 if key == "q" else 2)
        tag = "%s%d" % (label_key, n)
        if len(boxes) > 1:
            tag += ":%d" % (i + 1)
        # 答案框标签一律放框外上方：框里是答案正文，标签盖上去就看不清要核对的内容。
        ly = (p[1] - FS - 6) if key == "a" else p[1]
        label(p[0], max(0, ly), tag, COLORS[key])
        BOXES.append(p)


counts = {"q": 0, "w": 0, "a": 0}
for it in items:
    n = it["n"]
    if kind == "a":
        draw_boxes(n, it.get("q", []), "a", "a")
        counts["a"] += len(it.get("q", []))
    else:
        draw_boxes(n, it.get("q", []), "q", "q")
        draw_boxes(n, it.get("w", []), "w", "w")
        counts["q"] += len(it.get("q", []))
        counts["w"] += len(it.get("w", []))

if CROP_AUTO and BOXES:
    pad = 80
    x0 = max(0, int(min(b[0] for b in BOXES)) - pad)
    y0 = max(0, int(min(b[1] for b in BOXES)) - pad)
    x1 = min(im.width, int(max(b[2] for b in BOXES)) + pad)
    y1 = min(im.height, int(max(b[3] for b in BOXES)) + pad)
    im = im.crop((x0, y0, x1, y1))

im.save(out)
print(
    "overlay -> %s  %dx%d  items=%d  boxes q=%d w=%d a=%d  (红=题目 蓝=选项 绿=答案)"
    % (out, im.width, im.height, len(items), counts["q"], counts["w"], counts["a"])
)
