# -*- coding: utf-8 -*-
"""
一页纸的坐标生成器。人只给「行归属」，其余（行分割、块切分、坐标换算）全自动。

分组表格式（spec.json）:
{
  "src": "p29_hi.jpg",
  "kind": "q",                       // q=题目页(1220x1693, 双栏)  a=答案页(1145x1620, 单栏)
  "cols": {"L": [44, 258], "R": [262, 497]},   // kind=q 时必需
  "items": [
    {"n": 1, "stem": ["L03-L06"]},
    {"n": 3, "stem": ["L08"], "opt": ["L09x4"]},   // x4 = 该行横向切 4 个选项
    {"n": 4, "stem": ["L10"], "opt": ["L11-L14"]}, // 每行一个选项框
    {"n": 7, "stem": ["L23-L25", "R00-R01"]}
  ]
}

输出 items: [{n, q:[[x0,y0,x1,y1],...], w:[[...],...]}]，源坐标。
"""
import json, io, sys
from PIL import Image
import numpy as np

spec_path, out_path = sys.argv[1], sys.argv[2]
GROW = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
spec = json.load(io.open(spec_path, encoding="utf-8"))
im = Image.open(spec["src"]).convert("L")
a = np.array(im)

KIND = spec["kind"]
if KIND == "q":
    CANVAS = (519.7784108488579, 669.1)
    SRC = (1220.0, 1693.0)
else:
    CANVAS = (436.7083435058594, 669.0)
    SRC = (1145.0, 1620.0)
SS = im.width / CANVAS[0]
s_src = min(CANVAS[0] / SRC[0], CANVAS[1] / SRC[1])
pad_x = (CANVAS[0] - SRC[0] * s_src) / 2.0
pad_y = (CANVAS[1] - SRC[1] * s_src) / 2.0

TH = spec.get("th", 200 if KIND == "q" else 225)
MIN_INK = spec.get("min_ink", 20 if KIND == "q" else 2)
MIN_H = 2.0
GAP_CSS = spec.get("gap_css", 4.0)
Y0, Y1 = spec.get("y", [20.0, 660.0])


def px(v):
    return int(round(v * SS))


def row_blocks(X0, X1):
    """返回该栏每行的 y 范围 + 该行的块切分（CSS）。"""
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
    rows = []
    for ra, rb in merged:
        if (rb - ra) / SS < MIN_H:
            continue
        band = sub[ra:rb + 1]
        ink_c = (band < TH).sum(axis=0)
        segs, cur2 = [], None
        for i, v in enumerate(ink_c):
            if v > 0:
                cur2 = [i, i] if cur2 is None else [cur2[0], i]
            else:
                if cur2 is not None:
                    segs.append(cur2); cur2 = None
        if cur2:
            segs.append(cur2)
        blocks = []
        for s in segs:
            if blocks and s[0] - blocks[-1][1] < GAP_CSS * SS:
                blocks[-1][1] = s[1]
            else:
                blocks.append(list(s))
        # 扫描页右边缘常留一条淡竖线，会被切成「紧贴栏边界 + 很窄」的伪块，
        # 一旦并进选项组就把框拉宽到栏边界。丢掉它。
        blocks = [b for b in blocks
                  if not ((b[1] - b[0]) / SS < 3.0 and X0 + b[1] / SS >= X1 - 6)]
        rows.append({
            "y0": Y0 + ra / SS, "y1": Y0 + rb / SS,
            "blocks": [[X0 + b[0] / SS, X0 + b[1] / SS] for b in blocks],
        })
    return rows


CACHE = {}


def rows(tag):
    if tag not in CACHE:
        if KIND == "q":
            X0, X1 = spec["cols"][tag]
        else:
            X0, X1 = spec["x"]
        CACHE[tag] = row_blocks(float(X0), float(X1))
    return CACHE[tag]


def span(spec_str):
    """'L03-L06' -> (tag, i, j)"""
    tag = spec_str[0] if KIND == "q" else ""
    sp = spec_str[1:] if KIND == "q" else spec_str
    if "-" in sp:
        a1, a2 = sp.split("-")
        a2 = a2.lstrip("LR")
    else:
        a1 = a2 = sp
    return tag, int(a1), int(a2)


def merge_box(tag, i, j):
    rs = rows(tag)[i:j + 1]
    return [min(r["blocks"][0][0] for r in rs), min(r["y0"] for r in rs),
            max(r["blocks"][-1][1] for r in rs), max(r["y1"] for r in rs)]


def raw_box(sp):
    """'@x0,y0,x1,y1' = 直接给的 CSS 矩形（整块答案用，不必过行分割）。"""
    x0, y0, x1, y1 = map(float, sp[1:].split(","))
    return [x0, y0, x1, y1]


def grow(b):
    """整页统一外扩若干 CSS 像素（命令行第三参数，默认 0）。

    行分割只贴墨迹主体，分数上下标、根号横线、下划线常被切掉半截。
    框比内容略大无害，切掉内容才是错。"""
    if not GROW:
        return b
    return [max(0.0, b[0] - GROW), max(0.0, b[1] - GROW),
            min(CANVAS[0], b[2] + GROW), min(CANVAS[1], b[3] + GROW)]


def ans_box(sp):
    """答案区语法 'A7-8:0' = 行 7..8 的第 0 块，合并成一个框；'A4:0-5' = 行 4 的块 0..5。"""
    body = sp[1:]
    rowpart, br = body.split(":")
    if "-" in rowpart:
        i, j = map(int, rowpart.split("-"))
    else:
        i = j = int(rowpart)
    if "-" in br:
        b0, b1 = map(int, br.split("-"))
    else:
        b0 = b1 = int(br)
    rs = rows("")[i:j + 1]
    return [min(r["blocks"][b0][0] for r in rs), min(r["y0"] for r in rs),
            max(r["blocks"][b1][1] for r in rs), max(r["y1"] for r in rs)]


def opt_boxes(spec_str):
    tag, i, j = span(spec_str.split("x")[0])
    per_row = int(spec_str.split("x")[1]) if "x" in spec_str else 1
    out = []
    for ri in range(i, j + 1):
        r = rows(tag)[ri]
        bl = r["blocks"]
        if per_row <= 1 or len(bl) < per_row:
            # 竖排：整行就是一个选项，块之间的间隙是选项内部的
            out.append([bl[0][0], r["y0"], bl[-1][1], r["y1"]])
            continue
        if len(bl) == per_row:
            for b in bl:
                out.append([b[0], r["y0"], b[1], r["y1"]])
            continue
        # 选项之间一定是该行最大的几个间隙：按最大的 per_row-1 个间隙切，
        # 不要按块数均分（块数会随噪声块变化，均分点会跑到选项内部）。
        gaps = sorted(range(len(bl) - 1),
                      key=lambda k: bl[k + 1][0] - bl[k][1], reverse=True)
        cuts = sorted(gaps[:per_row - 1])
        segs = []
        start = 0
        for c in cuts:
            segs.append((start, c)); start = c + 1
        segs.append((start, len(bl) - 1))
        for lo, hi in segs:
            out.append([bl[lo][0], r["y0"], bl[hi][1], r["y1"]])
    return out


def to_src(b):
    return [int(round((b[0] - pad_x) / s_src)), int(round((b[1] - pad_y) / s_src)),
            int(round((b[2] - pad_x) / s_src)), int(round((b[3] - pad_y) / s_src))]


def _ink(bb):
    """框内墨迹像素数（源图尺度）。"""
    y0, y1 = px(bb[1]), px(bb[3])
    x0, x1 = px(bb[0]), px(bb[2])
    sub = a[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    if not sub.size:
        return 0
    return int((sub < TH).sum())


def _overlap(r1, r2):
    w = min(r1[2], r2[2]) - max(r1[0], r2[0])
    h = min(r1[3], r2[3]) - max(r1[1], r2[1])
    return w * h if (w > 0 and h > 0) else 0.0


def check_items(recs):
    """只报高置信度的错 —— 误报多的自检会被忽略，反而有害。

    能自动判的：退化框 / 空框 / 同题选项框互相吞 / 跨题重叠。
    不能自动判的（框内到底是哪个字）：只有 overlay 看图，见 HANDOFF 第一节。
    """
    warns = []
    for n, kind, b in recs:
        w, h = b[2] - b[0], b[3] - b[1]
        pos = "[%.1f,%.1f,%.1f,%.1f]" % tuple(b)
        if w < 2 or h < 2:
            warns.append("CHECK degenerate box %s%d %s w=%.1f h=%.1f" % (kind, n, pos, w, h))
        if _ink(b) == 0:
            warns.append("CHECK empty box %s%d %s (boxed over blank area)" % (kind, n, pos))
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            n1, k1, b1 = recs[i]
            n2, k2, b2 = recs[j]
            ov = _overlap(b1, b2)
            if ov <= 0:
                continue
            if n1 == n2 and k1 == "w" and k2 == "w":
                area = (b1[2] - b1[0]) * (b1[3] - b1[1])
                if area > 0 and ov > 0.5 * area:
                    warns.append("CHECK option boxes overlap on q%d (may collapse into one on submit)" % n1)
            elif n1 != n2 and ov > 10.0:
                warns.append("CHECK cross-question overlap q%d/%s vs q%d/%s area=%.1f" % (n1, k1, n2, k2, ov))
    return warns


items = []
ALL_BOXES = []
for it in spec["items"]:
    q_boxes = []
    for sp in it.get("stem", []):
        if sp.startswith("@"):
            q_boxes.append(raw_box(sp))
            continue
        if sp.startswith("A"):
            q_boxes.append(ans_box(sp))
            continue
        tag, i, j = span(sp)
        q_boxes.append(merge_box(tag, i, j))
    w_boxes = []
    for sp in it.get("opt", []):
        if sp.startswith("@"):
            w_boxes.append(raw_box(sp))
        else:
            w_boxes.extend(opt_boxes(sp))
    items.append({
        "n": it["n"],
        "q": [to_src(grow(b)) for b in q_boxes],
        "w": [to_src(grow(b)) for b in w_boxes],
        "q_css": [[round(v, 1) for v in grow(b)] for b in q_boxes],
    })
    ALL_BOXES.extend((it["n"], "q", grow(b)) for b in q_boxes)
    ALL_BOXES.extend((it["n"], "w", grow(b)) for b in w_boxes)

io.open(out_path, "w", encoding="utf-8").write(json.dumps(items, ensure_ascii=False, indent=1))
print("s_src=%.6f pad=(%.2f,%.2f) items=%d" % (s_src, pad_x, pad_y, len(items)))
for it in items:
    print("  n=%-2d q=%s w=%d" % (it["n"], it["q"], len(it["w"])))

warns = check_items(ALL_BOXES)
# 落盘一份，让 make_page.py / dry run 也能看到（防 agent 跳过这一步）
io.open(out_path + ".check.txt", "w", encoding="utf-8").write("\n".join(warns))
for w in warns:
    print(w)
if warns:
    print("CHECK_TOTAL %d -- warnings above. Overlay review still required: the self-check covers geometry only, never box content." % len(warns))
else:
    print("CHECK_OK 0 -- geometry self-check passed. This does NOT mean the boxes are correct; overlay review is still required.")
