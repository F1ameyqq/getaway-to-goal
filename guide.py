# -*- coding: utf-8 -*-
"""一页一张图：把 cols.py 的四张栏图压成一张带行号的图。

用法:
  # 题目页：左右栏并排，左侧标尺标 L00/L01... R00/R01...
  python guide.py <题目图> <out.png> q --cols L:44-258,R:262-497 [--y 20-660] [--th 200] [--min-ink 20]

  # 答案页（单栏）：只截指定 x 范围，标 A00/A01...，并在块上方标块号 0/1/2...
  # 同时打印每行的 y 范围和每块的 x 范围（等价于 ans_dump），可直接写 @ 矩形。
  python guide.py <答案图> <out.png> a --x 8-218 [--y 20-660] [--th 225] [--min-ink 2]

  # 答案页（找上下文）：整页 + y 坐标标尺，用来看课时标题和确定 y 范围
  python guide.py <答案图> <out.png> a --full [--y 20-660]

行号规则与 measure_page.py 完全一致（同一套 TH/MIN_INK/MIN_H/合并逻辑），
所以 guide 图上看到的 L03 就是 spec 里的 L03。

顺带做图像自检（尺寸 + 墨迹占比），用 IMG_OK 一行代替「打开原图看一眼」。
"""
import sys, os, io, math
from PIL import Image, ImageDraw, ImageFont
import numpy as np

CANVAS = {
    "q": (519.7784108488579, 669.1),
    "a": (436.7083435058594, 669.0),
}
MIN_H = 2.0
GAP_CSS = 4.0

if len(sys.argv) < 4:
    print(__doc__.strip())
    sys.exit(2)

img_path, out_path, KIND = sys.argv[1], sys.argv[2], sys.argv[3]
if KIND not in CANVAS:
    raise SystemExit("kind 必须是 q 或 a")

cols = {}
X0 = X1 = None
Y0, Y1 = 20.0, 660.0
TH = 200 if KIND == "q" else 225
MIN_INK = 20 if KIND == "q" else 2
FULL = False

i = 4
while i < len(sys.argv):
    k = sys.argv[i]
    if k == "--cols":
        for part in sys.argv[i + 1].split(","):
            tag, rng = part.split(":")
            a0, a1 = rng.split("-")
            cols[tag.strip()] = (float(a0), float(a1))
        i += 2
    elif k == "--x":
        a0, a1 = sys.argv[i + 1].split("-")
        X0, X1 = float(a0), float(a1)
        i += 2
    elif k == "--y":
        a0, a1 = sys.argv[i + 1].split("-")
        Y0, Y1 = float(a0), float(a1)
        i += 2
    elif k == "--th":
        TH = int(sys.argv[i + 1])
        i += 2
    elif k == "--min-ink":
        MIN_INK = int(sys.argv[i + 1])
        i += 2
    elif k == "--full":
        FULL = True
        i += 1
    else:
        raise SystemExit("未知参数: " + k)

im = Image.open(img_path)
a = np.array(im.convert("L"))
S = im.width / CANVAS[KIND][0]
SS = S  # 与 measure_page.py 的命名保持一致


def px(v):
    return int(round(v * S))


def font(size):
    for f in (
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


FS = max(16, int(round(7.5 * S)))
LAB = FS * 3 + 16
fnt = font(FS)


def detect_rows(x0, x1):
    """与 measure_page.row_blocks 同一套规则，只不过 x 范围显式传入。"""
    sub = a[px(Y0):px(Y1), px(x0):px(x1)]
    ink_r = (sub < TH).sum(axis=1)
    raw, cur = [], None
    for i2, v in enumerate(ink_r):
        if v > MIN_INK:
            cur = [i2, i2] if cur is None else [cur[0], i2]
        else:
            if cur is not None:
                raw.append(cur)
                cur = None
    if cur:
        raw.append(cur)
    merged = []
    for r in raw:
        if merged and r[0] - merged[-1][1] <= 4:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))

    rows = []
    for ra, rb in merged:
        if (rb - ra) / SS < MIN_H:
            continue
        band = sub[ra : rb + 1]
        ink_c = (band < TH).sum(axis=0)
        segs, cur2 = [], None
        for i2, v in enumerate(ink_c):
            if v > 0:
                cur2 = [i2, i2] if cur2 is None else [cur2[0], i2]
            else:
                if cur2 is not None:
                    segs.append(cur2)
                    cur2 = None
        if cur2:
            segs.append(cur2)
        blocks = []
        for s in segs:
            if blocks and s[0] - blocks[-1][1] < GAP_CSS * SS:
                blocks[-1][1] = s[1]
            else:
                blocks.append(list(s))
        # 页右边缘的淡竖线，与 measure_page.py 一致丢弃
        blocks = [
            b
            for b in blocks
            if not ((b[1] - b[0]) / SS < 3.0 and x0 + b[1] / SS >= x1 - 6)
        ]
        rows.append(
            {
                "y0": Y0 + ra / SS,
                "y1": Y0 + rb / SS,
                "blocks": [[x0 + b[0] / SS, x0 + b[1] / SS] for b in blocks],
            }
        )
    return rows, sub


def ypx(css_y):
    return int(round((css_y - Y0) * S))


def make_column(tag, x0, x1, answer=False, table=None):
    rows, sub = detect_rows(x0, x1)
    col = Image.fromarray(sub).convert("RGB")
    canvas = Image.new("RGB", (LAB + col.width, col.height), "white")
    canvas.paste(col, (LAB, 0))
    d = ImageDraw.Draw(canvas)
    for i2, r in enumerate(rows):
        y = ypx(r["y0"])
        label = ("A%02d" if answer else tag + "%02d") % i2
        d.text((4, y - 2), label, font=fnt, fill=(200, 0, 0))
        d.line([(LAB - 10, y), (LAB + 12, y)], fill=(0, 150, 0), width=2)
        d.line([(LAB - 4, ypx(r["y1"])), (LAB + 4, ypx(r["y1"]))], fill=(0, 120, 220), width=1)
        if answer:
            for bi, (bx0, bx1) in enumerate(r["blocks"]):
                lx = LAB + int(round((bx0 - x0) * S))
                ly = max(0, y - FS - 2)
                txt = str(bi)
                bb = d.textbbox((lx + 2, ly), txt, font=fnt)
                d.rectangle(bb, fill=(255, 255, 255))
                d.text((lx + 2, ly), txt, font=fnt, fill=(0, 110, 220))
            if table is not None:
                table.append(
                    "A%02d y=%.1f-%.1f blocks=%d %s"
                    % (
                        i2,
                        r["y0"],
                        r["y1"],
                        len(r["blocks"]),
                        " ".join("[%.1f,%.1f]" % (b[0], b[1]) for b in r["blocks"]),
                    )
                )
    return canvas, len(rows)


# --- 图像自检：尺寸 + 墨迹占比 ------------------------------------------------
small = im.convert("L")
small.thumbnail((600, 600))
ink = float((np.array(small) < 200).mean())
print("IMG_OK %s %dx%d ink=%.1f%%" % (img_path, im.width, im.height, ink * 100))
if ink < 0.005:
    print("IMG_BLANK %s —— 这张图基本是空白，别往下走" % img_path)
    sys.exit(1)

os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

if KIND == "q":
    if not cols:
        raise SystemExit("题目页必须给 --cols，例如 --cols L:44-258,R:262-497")
    imgs = []
    counts = []
    for tag, (x0, x1) in cols.items():
        c, n = make_column(tag, x0, x1)
        imgs.append(c)
        counts.append("%s=%d" % (tag, n))
    gap = 24
    W = sum(c.width for c in imgs) + gap * (len(imgs) - 1)
    H = max(c.height for c in imgs)
    out = Image.new("RGB", (W, H), "white")
    x = 0
    for c in imgs:
        out.paste(c, (x, 0))
        x += c.width + gap
    out.save(out_path)
    print("GUIDE q %s %dx%d rows %s" % (out_path, out.width, out.height, " ".join(counts)))

elif FULL:
    x0, x1 = 0.0, CANVAS["a"][0]
    sub = a[px(Y0) : px(Y1), px(x0) : px(x1)]
    page_img = Image.fromarray(sub).convert("RGB")
    out = Image.new("RGB", (LAB + page_img.width, page_img.height), "white")
    out.paste(page_img, (LAB, 0))
    d = ImageDraw.Draw(out)
    for yy in range(int(math.ceil(Y0 / 20.0) * 20), int(Y1) + 1, 20):
        y = ypx(yy)
        if y < 0 or y >= out.height:
            continue
        d.line([(LAB - 10, y), (LAB, y)], fill=(200, 0, 0), width=1)
        d.text((4, y - FS // 2), str(int(yy)), font=fnt, fill=(200, 0, 0))
    out.save(out_path)
    print("GUIDE a-full %s %dx%d y=%g-%g（红字是 CSS 的 y 坐标，用来看区间、找课时标题）" % (out_path, out.width, out.height, Y0, Y1))

else:
    if X0 is None:
        raise SystemExit("答案页必须给 --x（答案所在栏的范围），或 --full 看整页")
    table = []
    c, n = make_column("A", X0, X1, answer=True, table=table)
    c.save(out_path)
    print("GUIDE a %s %dx%d rows=%d" % (out_path, c.width, c.height, n))
    for line in table[:120]:
        print(line)
    if len(table) > 120:
        print("... 还有 %d 行未打印" % (len(table) - 120))
