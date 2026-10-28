# -*- coding: utf-8 -*-
"""One-command full-set runner for propose_spec.py (offline).

Usage:
  python -I drafts/run_all.py

Runs every regression / verified / blind page through the q-page pipeline and
prints one table:

  页 | GATE | 条目数 | 硬违规 | 软违规 | 判决 | 与标准/基准比对

The pipeline itself lives in propose_spec.py; this runner only drives it, keeps
stdout quiet, and does the standard/baseline comparison. It never writes to the
platform and never runs any .mjs.
"""
import io, os, sys, json, contextlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import propose_spec as P  # noqa: E402
import numpy as np  # noqa: E402

SRC = r"C:/Users/ASUS/ego-install-tmp/srcpages"
DRAFTS = os.path.join(HERE, "_run_%s.json")

CANVAS = P.CANVAS

# (name, image file, standard qspec or None, baseline-draft for byte compare or None)
REGRESSION = [
    ("p29", "p29_hi.jpg", "p29_qspec.json", None),
    ("p30", "p30_hi.jpg", "p30_qspec.json", None),
    ("p31", "p31_hi.jpg", "p31_qspec.json", None),
    ("p32", "p32_hi.jpg", "p32_qspec.json", None),
    ("p33", "p33_hi.jpg", "p33_qspec.json", None),
    ("p34", "p34_hi.jpg", "p34_qspec.json", os.path.join(HERE, "_resume", "p34.json")),
    ("p35", "p35_hi.jpg", "p35_qspec.json", os.path.join(HERE, "_resume", "p35.json")),
]

# Blind pages have no standard spec; the baseline is qualitative (kept here so the
# verdict can be re-checked by hand).
BLIND = [
    ("p174_hi", "p174_hi.jpg", "单栏答案/解析页,不属于双栏数学题家族 -> C"),
    ("r34_A", "r34_A.jpg", "横向条带(2160x252,非整页) -> C"),
    ("r34_B", "r34_B.jpg", "横向条带(1764x252,非整页) -> C"),
    ("r8910", "r8910.jpg", "横向条带(2520x270,非整页) -> C"),
]


def load_page(img_path, kind="q"):
    im = P.Image.open(img_path)
    rgb = im.convert("RGB")
    gray = np.array(im.convert("L"))
    SS = im.width / CANVAS[kind][0]
    small = im.convert("L")
    small.thumbnail((600, 600))
    ink = float((np.array(small) < 200).mean())
    return im, rgb, gray, SS, ink


def run_q(name, img_file):
    img_path = os.path.join(SRC, img_file)
    im, rgb, gray, SS, ink = load_page(img_path, "q")
    out_path = DRAFTS % name
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            res = P.build_q(rgb, gray, SS, img_path,
                            {"L": [44.0, 258.0], "R": [262.0, 497.0]},
                            20.0, 660.0, 200, 20, out_path,
                            ink=ink, img_height=im.height, start_n=None)
        except Exception as e:
            res = {"page": name, "gate": "?", "verdict": "CRASH", "items": 0,
                   "hard": [], "soft": [], "spec": None, "error": repr(e)}
    return res


def load_json(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compare(name, res, std_path, base_path):
    if res.get("verdict") == "CRASH":
        return "崩溃: " + res.get("error", "?")
    if res["verdict"] == "REFUSE" and res["gate"] == "C":
        return "GATE C(版面不符)"
    if res["verdict"] == "REFUSE":
        std = load_json(std_path)
        if std:
            return "硬违规判废(标准有%d题: %s)" % (
                len(std["items"]), [i["n"] for i in std["items"]])
        return "硬违规判废"
    # emitted draft
    if base_path:
        base = load_json(base_path)
        if base is not None:
            prod = load_json(res["spec"])
            same = prod is not None and prod["items"] == base["items"]
            return "坐标逐字节一致" if same else "坐标不一致"
    std = load_json(std_path)
    if std is None:
        return "无标准"
    prod = load_json(res["spec"])
    pn = [i["n"] for i in prod["items"]] if prod else []
    sn = [i["n"] for i in std["items"]]
    if pn == sn:
        return "n链=标准(%d题)" % len(sn)
    return "n链: 工具%s vs 标准%s" % (pn, sn)


def main():
    rows = []
    for name, img_file, std_file, base_file in REGRESSION:
        std_path = os.path.join(SRC, std_file)
        res = run_q(name, img_file)
        hard = len(res["hard"])
        soft = len(res["soft"])
        main_rule = ("(主因 rule=%d)" % res["hard"][0]["rule"]) if res["hard"] else ""
        rows.append((name, res["gate"], res["items"], "%d%s" % (hard, main_rule), soft,
                     res["verdict"], compare(name, res, std_path, base_file)))

    for name, img_file, base_text in BLIND:
        res = run_q(name, img_file)
        hard = len(res["hard"])
        soft = len(res["soft"])
        rows.append((name, res["gate"], res["items"], hard, soft, res["verdict"],
                     "基准: %s" % base_text))

    hdr = ("页", "GATE", "条目数", "硬违规", "软违规", "判决", "与标准/基准比对")
    widths = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]
    widths = [w + 2 for w in widths]

    def fmt(row):
        return "".join(str(c).ljust(w) for c, w in zip(row, widths))

    print(fmt(hdr))
    for r in rows:
        print(fmt(r))

    # acceptance summary
    blind_ok = all(r[5] == "REFUSE" for r in rows if r[0] in
                   [b[0] for b in BLIND])
    p34 = next(r for r in rows if r[0] == "p34")
    p35 = next(r for r in rows if r[0] == "p35")
    p33 = next(r for r in rows if r[0] == "p33")
    print("\n验收: 盲测误放行=%d  p34=%s  p35=%s  p33=%s" % (
        0 if blind_ok else 1, p34[5], p35[5], p33[5]))


if __name__ == "__main__":
    main()
