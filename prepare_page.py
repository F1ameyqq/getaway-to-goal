# -*- coding: utf-8 -*-
"""离线链路一条命令跑完：图像自检 → measure_page → make_page → overlay。

用法:
  python prepare_page.py <qspec> <aspec|-> <qPage> <aPage> <types.json|-> <outpage.json>
                         [--outdir DIR] [--no-overlay]

例:
  python prepare_page.py specs\\p31_qspec.json specs\\p31_aspec.json 31 175 specs\\p31_types.json pages\\p31.json

输出刻意压到十几行：IMG_OK / PAGE / CHECK_* / VIEW_* / NEXT。
不要再单独跑 measure_page.py、make_page.py、overlay.py。
"""
import argparse, io, json, os, subprocess, sys
from collections import Counter

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cfg():
    p = os.path.join(HERE, "config.json")
    if not os.path.exists(p):
        return {}
    return json.load(io.open(p, encoding="utf-8"))


CFG = load_cfg()
SRC_DIR = os.path.join(HERE, (CFG.get("paths") or {}).get("srcDir") or "srcpages")


def run(script, *args):
    """用同一个解释器跑子脚本。-X utf8 保证中文输出在管道里也能按 UTF-8 解。"""
    cmd = [sys.executable, "-I", "-X", "utf8", os.path.join(HERE, script)] + [str(a) for a in args]
    cp = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if cp.returncode != 0:
        if cp.stdout:
            print(cp.stdout.rstrip())
        if cp.stderr:
            print(cp.stderr.rstrip())
        raise SystemExit("%s 失败 (exit %d)" % (script, cp.returncode))
    return cp.stdout or ""


def check_img(path, tag):
    if not os.path.exists(path):
        raise SystemExit("IMG_MISSING %s %s" % (tag, path))
    im = Image.open(path)
    small = im.convert("L")
    small.thumbnail((600, 600))
    ink = float((np.array(small) < 200).mean())
    print("IMG_OK %s %s %dx%d ink=%.1f%%" % (tag, path, im.width, im.height, ink * 100))
    if ink < 0.005:
        raise SystemExit("IMG_BLANK %s —— 这张图基本是空白，别往下走" % path)
    return im.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("qspec")
    ap.add_argument("aspec")
    ap.add_argument("qpage", type=int)
    ap.add_argument("apage", type=int)
    ap.add_argument("types")
    ap.add_argument("outpage")
    ap.add_argument("--outdir", default=SRC_DIR)
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--grow", type=float, default=0.0,
                    help="所有框统一外扩的 CSS 像素数（默认 0）。细分数/上下标被切时用 1.5~2")
    ap.add_argument("--grow-a", type=float, default=None,
                    help="答案区单独的外扩量，默认跟 --grow。答案框常用手工 @ 紧排，不该跟着外扩")
    ap.add_argument("--lesson", default=None,
                    help="课时名，与左侧目录树显示文本完全一致；写入 pages json 的 lesson 字段，录入时按它精确选课时")
    args = ap.parse_args()

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    qspec = json.load(io.open(args.qspec, encoding="utf-8"))
    check_img(qspec["src"], "q")

    aspec = None
    if args.aspec != "-":
        aspec = json.load(io.open(args.aspec, encoding="utf-8"))
        check_img(aspec["src"], "a")

    q_base = os.path.splitext(os.path.basename(args.qspec))[0]
    q_out = os.path.join(outdir, q_base + "_out.json")
    run("measure_page.py", args.qspec, q_out, args.grow)
    print("MEASURE q %s" % q_out)

    a_out = None
    if aspec is not None:
        a_base = os.path.splitext(os.path.basename(args.aspec))[0]
        a_out = os.path.join(outdir, a_base + "_out.json")
        grow_a = args.grow if args.grow_a is None else args.grow_a
        run("measure_page.py", args.aspec, a_out, grow_a)
        print("MEASURE a %s" % a_out)

    run(
        "make_page.py",
        q_out,
        a_out if a_out else "-",
        args.qpage,
        args.apage,
        args.types,
        args.outpage,
    )

    page = json.load(io.open(args.outpage, encoding="utf-8"))
    if args.lesson:
        page["lesson"] = args.lesson
        io.open(args.outpage, "w", encoding="utf-8").write(
            json.dumps(page, ensure_ascii=False, indent=1))
        print("LESSON %s" % args.lesson)
    else:
        print("LESSON_MISSING (pages json 没有 lesson 字段；录入时 restore 会因缺课时名而中止)")
    items = page.get("items", [])
    boxes = Counter()
    for it in items:
        boxes["q"] += len(it.get("q", []))
        boxes["w"] += len(it.get("w", []))
        boxes["a"] += len(it.get("a", []))
    types = Counter(it.get("type", "?") for it in items)
    # 类型值本身是中文（填空/选择/问答）。控制台编码在 PowerShell/Git Bash 下不一致，
    # 这里统一映射成 ASCII，保证这行在任何终端都能读。
    TYPE_ASCII = {"填空": "fill", "选择": "choice", "问答": "qa", "解答": "qa"}
    tstr = " ".join(
        "%s%d" % (TYPE_ASCII.get(k, k), v) for k, v in types.most_common()
    )
    print(
        "PAGE %s  items=%d  boxes q=%d w=%d a=%d  types=%s"
        % (args.outpage, len(items), boxes["q"], boxes["w"], boxes["a"], tstr)
    )

    checks = page.get("_check") or []
    if checks:
        print("CHECK_WARN %d -- geometry self-check has warnings, do NOT submit:" % len(checks))
        for c in checks[:10]:
            print("  " + c)
        if len(checks) > 10:
            print("  ... %d more" % (len(checks) - 10))
    else:
        print("CHECK_CLEAN 0 (geometry only; box contents still require the overlay review)")

    if not args.no_overlay:
        q_ov = os.path.join(outdir, "p%d_q_overlay.png" % args.qpage)
        run("overlay.py", qspec["src"], q_out, q_ov, "q")
        print("VIEW_Q %s" % os.path.abspath(q_ov))
        if aspec is not None:
            a_ov = os.path.join(outdir, "a%d_a_overlay.png" % args.apage)
            run("overlay.py", aspec["src"], a_out, a_ov, "a", "--crop", "auto")
            print("VIEW_A %s" % os.path.abspath(a_ov))

        # dry run 不用 ego，直接 node。main() 收的是文件路径（不是 file:// URL）。
        run_url = "file:///" + os.path.join(HERE, "pageRun.mjs").replace("\\", "/")
        page_path = os.path.abspath(args.outpage).replace("\\", "/")
        print("NEXT dry run:")
        print(
            'node -e "import(\'%s\').then(async m=>{console.log(JSON.stringify(await m.main(\'%s\',{dry:true})))})"'
            % (run_url, page_path)
        )


if __name__ == "__main__":
    main()
