# -*- coding: utf-8 -*-
"""propose_spec.py -- offline draft tool: page image -> spec draft + text review table.

Usage:
  python -I propose_spec.py <image> --kind q|a [--cols L:44-258,R:262-497] [--x 8-218] [--y 20-660] [--out out.json] [--start N]

What it does:
  1. row segmentation (verbatim copy of guide.py / measure_page.py rules, so L03 here == L03 in spec)
  2. left-edge OCR (rapidocr, offline) on each column to find question numbers "N." and option letters "A./B./C./D."
  3. assign rows to questions, split stem vs options, emit a spec draft
  4. print a pure-number/text review table with per-item confidence

New in this revision (two gates around the unchanged segmentation, never touching it):

  A. PAGE GATE (before any draft). The page is measured against the *verified* layout
     profiles in page_profiles.json. Only pages whose measurable features match a
     verified profile are allowed to proceed. Verdict A (auto) / B (draft + pending
     checks) / C (refuse -- no draft is produced). Features are numeric with a
     measured value and a threshold, so a refusal is reproducible.
  B. GENERAL INVARIANTS (after the draft is built). Hard violations (rules 1-4) refuse
     the whole page: 1 question-number chain, 2 number count == interval length,
     3 reading order (no interleaving across columns), 4 boxes do not overlap / run out
     of bounds / cross columns. Soft violations (rules 5-7) downgrade the draft to B and
     are listed as pending human checks instead of refusing: 5 option count is 0/2/4,
     6 stem box height >= page line spacing, 7 body text row not covered by a box
     (escalates to hard only when a tall uncovered row carries a question-number text).

Confidence comes from concrete signals only (anchor OCR score, number continuity,
vertical gap inside a stem, horizontal vs vertical option split, option count).
Anything ambiguous is marked low instead of guessed high.

This tool never touches ego-browser, never writes to the platform, and only reads the
image + writes local files.
"""
import sys, os, io, json, re, math

from PIL import Image
import numpy as np

CANVAS = {"q": (519.7784108488579, 669.1), "a": (436.7083435058594, 669.0)}
MIN_H = 2.0
GAP_CSS = 4.0
# Vertical gap (CSS) above which two consecutive rows are treated as a section/page
# break rather than part of the same question. Tall fractions/figures inside one
# question reach ~60-81 CSS on these pages; section headers / page numbers sit ~85+.
GAP_SPLIT = 84.0
# A vertical gap inside a stem is only "ambiguous" (worth a low flag) when it is
# close to GAP_SPLIT and NOT explained by a sub-question marker "(n)" on the next
# row. Sub-question spacing is a known structure, not a hidden section header.
STEM_AMBIG = 70.0
LOW_CONF = 0.65

# Rule 7 (uncovered body row) is soft by default; it only escalates to a hard
# refusal when the uncovered row is tall enough to be a dropped multi-line question
# body AND its OCR text looks like a question number. This keeps headers/footers
# from failing known-good pages while still catching a silently dropped question.
COVERAGE_UPGRADE_HEIGHT_X = 2.0

# default column ranges (same as every existing qspec)
DEFAULT_COLS = {"L": [44.0, 258.0], "R": [262.0, 497.0]}
DEFAULT_Y = [20.0, 660.0]

NUM_RE = re.compile(r"^(\d{1,3})[.、．](?!\d)")
OPT_RE = re.compile(r"^([ABCDabcd])\s*[.、,，]")
OPT_IN_TEXT = re.compile(r"([ABCDabcd])\s*[.、,，]")
SUBQ_RE = re.compile(r"^[（(]\s*(\d{1,2})\s*[)）]")
HEADER_RE = [
    re.compile(r"^[一二三四五六七八九十]{1,2}\s*[、.．]"),
    re.compile(r"^[（(][一二三四五六七八九十]+[)）]"),
    re.compile(r"^第\s*\d+\s*[课时节章]"),
    re.compile(r"[知如]识点\s*\d"),
    re.compile(r"^(基础|中档|综合|拔高|拓展|提升|培优)题?"),
]

SPAN_RE = re.compile(r"^([LR])(\d{1,3})(?:-([LR])(\d{1,3}))?$")

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES_PATH = os.path.join(HERE, "page_profiles.json")


def is_header(text):
    t = (text or "").strip()
    return bool(t) and any(p.match(t) for p in HEADER_RE)


def log(*a):
    print(*a)


def detect_rows(a, Y0, Y1, X0, X1, TH, MIN_INK, SS, GAP_CSS, MIN_H):
    """Same rule as guide.py detect_rows / measure_page.row_blocks."""
    px = lambda v: int(round(v * SS))
    sub = a[px(Y0):px(Y1), px(X0):px(X1)]
    ink_r = (sub < TH).sum(axis=1)
    raw, cur = [], None
    for i, v in enumerate(ink_r):
        if v > MIN_INK:
            cur = [i, i] if cur is None else [cur[0], i]
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
        band = sub[ra:rb + 1]
        ink_c = (band < TH).sum(axis=0)
        segs, cur2 = [], None
        for i, v in enumerate(ink_c):
            if v > 0:
                cur2 = [i, i] if cur2 is None else [cur2[0], i]
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
        blocks = [b for b in blocks
                  if not ((b[1] - b[0]) / SS < 3.0 and X0 + b[1] / SS >= X1 - 6)]
        rows.append({
            "y0": Y0 + ra / SS, "y1": Y0 + rb / SS,
            "blocks": [[X0 + b[0] / SS, X0 + b[1] / SS] for b in blocks],
        })
    return rows


_OCR = None


def get_ocr():
    global _OCR
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        except Exception as e:
            raise SystemExit("OCR unavailable (rapidocr_onnxruntime): %s" % e)
    return _OCR


def ocr_strip(img_rgb, x0css, x1css, y0css, y1css, SS):
    """OCR a CSS-space strip, return detections with absolute CSS coords."""
    crop = img_rgb.crop((int(x0css * SS), int(y0css * SS),
                         int(x1css * SS), int(y1css * SS)))
    eng = get_ocr()
    result, _ = eng(np.array(crop))
    dets = []
    if not result:
        return []
    for box, txt, cf in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        dets.append({
            "text": (txt or "").strip(),
            "conf": float(cf),
            "x0": x0css + min(xs) / SS, "x1": x0css + max(xs) / SS,
            "y0": y0css + min(ys) / SS, "y1": y0css + max(ys) / SS,
        })
    return dets


def yc(d):
    return (d["y0"] + d["y1"]) / 2.0


def row_of(y, rows):
    """Index of the row whose y-range contains y (nearest by center distance)."""
    best, best_d = None, 1e9
    for i, r in enumerate(rows):
        d = abs((r["y0"] + r["y1"]) / 2.0 - y)
        if d < best_d:
            best_d, best = d, i
    return best


def row_for_top(y, rows):
    """Assign a letter whose OCR box top edge is at y: prefer the row containing y,
    else the row whose interval is closest to y. Option letters sit at the top of
    their content, so their top edge is a more stable anchor than their center."""
    best, best_d = None, 1e9
    for i, r in enumerate(rows):
        if r["y0"] <= y <= r["y1"]:
            return i
        d = (r["y0"] - y) if y < r["y0"] else (y - r["y1"])
        if d < best_d:
            best_d, best = d, i
    return best


def union_box(rowlist):
    return [
        round(min(b[0] for r in rowlist for b in r["blocks"]), 1),
        round(min(r["y0"] for r in rowlist), 1),
        round(max(b[1] for r in rowlist for b in r["blocks"]), 1),
        round(max(r["y1"] for r in rowlist), 1),
    ]


def clean_row(r):
    return all((b[1] - b[0]) >= 1.5 for b in r["blocks"])


def union_box_clean(rowlist):
    bl = [b for r in rowlist for b in r["blocks"] if (b[1] - b[0]) >= 1.5]
    if not bl:
        bl = [b for r in rowlist for b in r["blocks"]]
    return [
        round(min(b[0] for b in bl), 1),
        round(min(r["y0"] for r in rowlist), 1),
        round(max(b[1] for b in bl), 1),
        round(max(r["y1"] for r in rowlist), 1),
    ]


def fmt_box(b):
    return "@%.1f,%.1f,%.1f,%.1f" % tuple(b)


def span_str(tag, i, j):
    if i == j:
        return "%s%02d" % (tag, i)
    return "%s%02d-%s%02d" % (tag, i, tag, j)


def row_gaps(rows, i):
    up = (rows[i]["y0"] - rows[i - 1]["y1"]) if i > 0 else 999.0
    dn = (rows[i + 1]["y0"] - rows[i]["y1"]) if i + 1 < len(rows) else 999.0
    return up, dn


def seg_gaps(rows, i, j):
    up, _ = row_gaps(rows, i)
    _, dn = row_gaps(rows, j)
    return up, dn


def ink_extent_y(gray, SS, x0, x1, y0, y1, up_gap, dn_gap, PAD=15.0, TH=200):
    """Ink's true top/bottom edge (CSS) inside [x0,x1], searched in a window that
    never crosses the midpoint to the neighbouring rows. Returns (y0, y1)."""
    up = min(up_gap / 2.0, PAD)
    dn = min(dn_gap / 2.0, PAD)
    X0 = max(0, int(x0 * SS))
    X1 = min(gray.shape[1], int(math.ceil(x1 * SS)))
    if X1 <= X0:
        return y0, y1
    win_y0 = max(0, int((y0 - up) * SS))
    win_y1 = min(gray.shape[0], int(math.ceil((y1 + dn) * SS)))
    if win_y1 <= win_y0:
        return y0, y1
    sub = gray[win_y0:win_y1, X0:X1]
    ys = np.where((sub < TH).any(axis=1))[0]
    if ys.size == 0:
        return y0, y1
    return round((win_y0 + ys[0]) / SS, 1), round((win_y0 + ys[-1] + 1) / SS, 1)


def ink_extent_y_cluster(gray, SS, x0, x1, y0, y1, PAD=15.0, TH=200, GAP=3.0):
    """Ink's vertical extent of the glyph cluster that contains the row band [y0,y1].

    Unlike ink_extent_y (which is gap-clamped for stems), this searches a generous
    window and then keeps only the ink cluster connected to the row band, so tall
    fractions/superscripts are captured but a neighbouring row's ink is not.
    """
    X0 = max(0, int(x0 * SS))
    X1 = min(gray.shape[1], int(math.ceil(x1 * SS)))
    if X1 <= X0:
        return y0, y1
    win_y0 = max(0, int((y0 - PAD) * SS))
    win_y1 = min(gray.shape[0], int(math.ceil((y1 + PAD) * SS)))
    if win_y1 <= win_y0:
        return y0, y1
    ink = (gray[win_y0:win_y1, X0:X1] < TH).any(axis=1)
    gap_px = int(math.ceil(GAP * SS))
    raw, cur = [], None
    for i, v in enumerate(ink):
        if v:
            cur = [i, i] if cur is None else [cur[0], i]
        else:
            if cur is not None:
                raw.append(cur); cur = None
    if cur:
        raw.append(cur)
    clusters = []
    for c in raw:
        if clusters and c[0] - clusters[-1][1] <= gap_px:
            clusters[-1][1] = c[1]
        else:
            clusters.append(list(c))
    if not clusters:
        return y0, y1
    row_i0 = int(round(y0 * SS)) - win_y0
    row_i1 = int(round(y1 * SS)) - win_y0
    best = None
    for c in clusters:
        if c[0] <= row_i1 and c[1] >= row_i0:
            best = c
            break
    if best is None:
        best = min(clusters, key=lambda c: min(abs(c[0] - row_i1), abs(c[1] - row_i0)))
    return round((win_y0 + best[0]) / SS, 1), round((win_y0 + best[1] + 1) / SS, 1)


def ink_box(box, gray, SS):
    y0, y1 = ink_extent_y_cluster(gray, SS, box[0], box[2], box[1], box[3])
    return [box[0], y0, box[2], y1]


def page_gap_stats(rows):
    """Per-column vertical-gap distribution -> a 'sponge' threshold (CSS).

    A horizontal blank band inside a candidate box that is clearly wider than the
    page's own normal line spacing means several text segments were merged into one
    box. The threshold is derived from the column's own gap distribution (median /
    upper quantile), never a hard-coded pixel value.
    """
    gaps = [rows[i]["y0"] - rows[i - 1]["y1"]
            for i in range(1, len(rows))
            if rows[i]["y0"] > rows[i - 1]["y1"]]
    if not gaps:
        return {"median": 0.0, "q75": 0.0, "sponge": 0.0}
    g = sorted(gaps)
    median = g[len(g) // 2]
    q75 = g[min(len(g) - 1, int(math.ceil(0.75 * len(g))) - 1)]
    sponge = max(median * 1.6, q75)
    return {"median": round(median, 1), "q75": round(q75, 1),
            "sponge": round(sponge, 1)}


def is_figure_row(row, x0, x1, text_rows, i):
    """A row with ink but no OCR text whose block shape looks like a figure
    (many small blocks = tick marks, or one very wide thin block = an axis),
    rather than a missed text line."""
    if i in text_rows or not row["blocks"]:
        return False
    colw = x1 - x0
    if colw <= 0:
        return False
    if len(row["blocks"]) >= 3:
        return True
    return max(b[1] - b[0] for b in row["blocks"]) > 0.5 * colw


def stem_box(tag, rows, i, j, gray, SS):
    """Emit an L-span when the row union is exact, else an @ box with the ink's
    true vertical extent (tall fractions/radicals extend past the row band)."""
    seg = rows[i:j + 1]
    box_raw = union_box(seg)
    box_clean = union_box_clean(seg)
    up, dn = seg_gaps(rows, i, j)
    y0, y1 = ink_extent_y(gray, SS, box_clean[0], box_clean[2],
                          box_clean[1], box_clean[3], up, dn)
    clean_exact = max(abs(a - b) for a, b in zip(box_raw, box_clean)) < 0.1
    ink_exact = abs(y0 - box_raw[1]) < 0.3 and abs(y1 - box_raw[3]) < 0.3
    if clean_exact and ink_exact:
        return span_str(tag, i, j)
    return fmt_box([box_clean[0], y0, box_clean[2], y1])


def split_row_boxes(row, k):
    """Split one row into k horizontal boxes (largest-gap), dropping zero-width noise blocks."""
    bl = [b for b in row["blocks"] if (b[1] - b[0]) >= 1.0]
    if not bl:
        return [union_box([row])]
    if len(bl) <= 1 or k <= 1:
        return [union_box([row])]
    if len(bl) <= k:
        return [[b[0], row["y0"], b[1], row["y1"]] for b in bl]
    gaps = sorted(range(len(bl) - 1), key=lambda i: bl[i + 1][0] - bl[i][1], reverse=True)
    cuts = sorted(gaps[:k - 1])
    out = []
    start = 0
    for c in cuts:
        out.append([bl[start][0], row["y0"], bl[c][1], row["y1"]])
        start = c + 1
    out.append([bl[start][0], row["y0"], bl[-1][1], row["y1"]])
    return out


def parse_cols(arg):
    """'L:44-258,R:262-497' -> dict. bare 'L,R' -> default ranges."""
    cols = {}
    for part in arg.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            tag, rng = part.split(":")
            a0, a1 = rng.split("-")
            cols[tag.strip()] = [float(a0), float(a1)]
        else:
            tag = part.strip()
            if tag not in DEFAULT_COLS:
                raise SystemExit("unknown column tag %r; give --cols L:44-258,R:262-497" % tag)
            cols[tag] = list(DEFAULT_COLS[tag])
    return cols


def parse_range(arg, default):
    if arg is None:
        return list(default)
    a0, a1 = arg.split("-")
    return [float(a0), float(a1)]


# --------------------------------------------------------------------------- #
# Page gate: measure the page against verified layout profiles.               #
# --------------------------------------------------------------------------- #

def load_profiles():
    if not os.path.exists(PROFILES_PATH):
        return {"profiles": []}
    try:
        return json.load(io.open(PROFILES_PATH, encoding="utf-8"))
    except Exception:
        return {"profiles": []}


def page_gate(analysis, profiles, ink, ss, img_height, kind, gray=None, TH=200):
    """Judge whether this page belongs to a verified layout profile.

    Returns (verdict, feature_rows) where verdict is A / B / C.
    Every feature is numeric (measured value + threshold) so the decision can be
    reproduced from the printed rows.

    The gate is a *layout family* judgment, not a page identity judgment: it checks
    measurable layout facts (canvas aspect, ink density, a real empty gutter between
    two columns, at least one left-edge question-number anchor anywhere on the page).
    It deliberately does NOT require every column to carry its own question number --
    a question may legitimately span both columns (e.g. p30). Content errors (broken
    number chains, overlapping boxes, ...) are left to check_invariants.
    """
    cols = analysis["cols"]
    col_tags = analysis["col_tags"]
    col_rows = analysis["col_rows"]
    col_anchors = analysis["col_anchors"]

    height_ratio = img_height / (CANVAS[kind][1] * ss)
    rows = []

    # Collect the raw measurements once (reported even when no profile matches).
    meas = {
        "height_ratio": round(height_ratio, 4),
        "ink": round(ink, 3),
        "n_columns": len(col_tags),
        "rows_per_column": {t: len(col_rows[t]) for t in col_tags},
        "anchors_per_column": {t: len(col_anchors[t]) for t in col_tags},
        "total_anchors": sum(len(col_anchors[t]) for t in col_tags),
        "min_anchor_conf": (min(a["conf"] for t in col_tags for a in col_anchors[t])
                            if any(col_anchors[t] for t in col_tags) else None),
    }

    prof = None
    for p in profiles.get("profiles", []):
        if p.get("kind") == kind:
            prof = p
            break

    if prof is None:
        rows.append({"feature": "profile", "measured": "none", "threshold": "kind=%s" % kind,
                     "pass": False, "hard": True})
        return "C", rows

    f = prof.get("features", {})

    def feature(name, value, thr, hard, passed):
        rows.append({"feature": name, "measured": value, "threshold": thr,
                     "pass": passed, "hard": hard})
        return passed

    # hard: canvas aspect (height must match the known canvas at the page's scale)
    hr_lo, hr_hi = f.get("height_ratio", [0.99, 1.01])
    hard_ok = feature("height_ratio", meas["height_ratio"], "[%.2f,%.2f]" % (hr_lo, hr_hi),
                      True, hr_lo <= meas["height_ratio"] <= hr_hi)

    # hard: ink density (too sparse -> blank/partial page, too dense -> not this layout)
    ink_lo, ink_hi = f.get("ink_density", [0.09, 0.30])
    hard_ok = feature("ink_density", meas["ink"], "[%.2f,%.2f]" % (ink_lo, ink_hi),
                      True, ink_lo <= meas["ink"] <= ink_hi) and hard_ok

    # hard: expected column count
    want_cols = f.get("expected_columns", 2)
    hard_ok = feature("column_count", meas["n_columns"], "==%d" % want_cols,
                      True, meas["n_columns"] == want_cols) and hard_ok

    # hard: a real two-column gutter -- the band between the two column ranges must be
    # empty. A single-column or table page has ink crossing that band -> C.
    gutter_ink = None
    if gray is not None and len(col_tags) >= 2:
        st = sorted(col_tags, key=lambda t: cols[t][0])
        a, b = st[0], st[1]
        mid = (cols[a][1] + cols[b][0]) / 2.0
        margin = float(f.get("gutter_margin_css", 8.0))
        X0 = max(0, int((mid - margin) * ss))
        X1 = min(gray.shape[1], int(math.ceil((mid + margin) * ss)))
        if X1 > X0:
            gutter_ink = round(float((gray[:, X0:X1] < TH).mean()), 4)
    if gutter_ink is not None:
        gmax = f.get("gutter_ink_max", 0.07)
        hard_ok = feature("gutter_ink", gutter_ink, "<=%.2f" % gmax,
                          True, gutter_ink <= gmax) and hard_ok
    else:
        hard_ok = feature("gutter_ink", "n/a", "two-column", True, False) and hard_ok

    # hard: each column has enough ink rows (catches strips/partial pages)
    min_rows = f.get("min_rows_per_column", 5)
    for t in col_tags:
        n = meas["rows_per_column"].get(t, 0)
        hard_ok = feature("rows_%s" % t, n, ">=%d" % min_rows,
                          True, n >= min_rows) and hard_ok

    # hard: the page carries at least one left-edge question-number anchor somewhere.
    # Page-level, not per-column -- a question may span both columns.
    min_anch = f.get("min_anchors_total", 1)
    hard_ok = feature("anchors_total", meas["total_anchors"], ">=%d" % min_anch,
                      True, meas["total_anchors"] >= min_anch) and hard_ok

    if not hard_ok:
        return "C", rows

    # soft: low anchor OCR confidence -> still emit a draft but require human checks (B)
    min_conf = meas["min_anchor_conf"]
    conf_ok = min_conf is None or min_conf >= f.get("min_anchor_conf", 0.75)
    feature("min_anchor_conf", (round(min_conf, 2) if min_conf is not None else "n/a"),
            ">=%.2f" % f.get("min_anchor_conf", 0.75), False, conf_ok)

    verdict = "A" if conf_ok else "B"
    rows.append({"feature": "profile", "measured": prof.get("name", "?"),
                 "threshold": "verified_pages=%s" % ",".join(prof.get("verified_pages", [])),
                 "pass": True, "hard": False})
    return verdict, rows


def print_gate(verdict, rows):
    log("--- gate ---")
    for r in rows:
        mark = "PASS" if r["pass"] else "FAIL"
        log("%-8s %s  measured=%s threshold=%s" %
            (mark, r["feature"], r["measured"], r["threshold"]))
    log("GATE %s" % verdict)


# --------------------------------------------------------------------------- #
# General invariants (post-draft hard checks).                                #
# --------------------------------------------------------------------------- #

def expand_span(s, cols, col_rows):
    """Expand a span string ('L10', 'R03-R05') or @box into [x0,y0,x1,y1]."""
    s = (s or "").strip()
    if s.startswith("@"):
        return [float(v) for v in s[1:].split(",")]
    m = SPAN_RE.match(s)
    if not m:
        return None
    tag = m.group(1)
    if tag not in col_rows:
        return None
    i = int(m.group(2))
    j = int(m.group(4)) if m.group(4) is not None else i
    if i > j:
        i, j = j, i
    return union_box(col_rows[tag][i:j + 1])


def boxes_of_item(item, cols, col_rows):
    boxes = []
    for s in item.get("stem", []):
        b = expand_span(s, cols, col_rows)
        if b:
            boxes.append(b)
    for s in item.get("opt", []):
        b = expand_span(s, cols, col_rows)
        if b:
            boxes.append(b)
    return boxes


def check_invariants(analysis, items, item_col, start_n):
    """Return {"hard": [...], "soft": [...]} violation dicts.

    Hard violations refuse the whole page; they are all content-level errors:
      rule 1 question-number chain (illegal / gap / jump),
      rule 2 number count == interval length,
      rule 3 reading order (no interleaving across columns),
      rule 4 boxes do not overlap / run out of bounds / cross columns.
    Soft violations downgrade the draft to B (pending human checks) but still emit it:
      rule 5 option count is 0 / 2 / 4 (otherwise suspicious),
      rule 6 stem box height >= page line spacing,
      rule 7 body text row not covered by any box -- interpreted as a likely
             header / footer, unless the row is tall AND carries a question-number
             text, in which case it escalates to hard (a silently dropped question).
    """
    cols = analysis["cols"]
    col_rows = analysis["col_rows"]
    col_tags = analysis["col_tags"]
    col_ocr_rows = analysis["col_ocr_rows"]
    col_headers = analysis["col_headers"]
    col_ocr_text = analysis.get("col_ocr_text", {})
    Y0, Y1 = analysis["Y0"], analysis["Y1"]
    hard, soft = [], []

    def add(rule, msg, where, severity):
        v = {"rule": rule, "msg": msg, "where": where, "severity": severity}
        (hard if severity == "hard" else soft).append(v)

    nums = [it["n"] for it in items]

    # rule 1: strictly increasing, step 1 (start is --start or first detected)
    if not nums:
        add(1, "未检出任何题目", "page", "hard")
    else:
        start = start_n if start_n is not None else nums[0]
        if nums[0] != start:
            add(1, "题号链起点错误: 首题号=%d 期望=%d" % (nums[0], start), "item[0]", "hard")
        prev = nums[0]
        for i in range(1, len(nums)):
            cur = nums[i]
            if cur < 1:
                add(1, "非法题号 %d" % cur, "item[%d]" % i, "hard")
            if cur != prev + 1:
                add(1, "题号链断链: %d -> %d (步长 %d)" % (prev, cur, cur - prev),
                    "item[%d]->item[%d]" % (i - 1, i), "hard")
            prev = cur

    # rule 2: number count == interval length (no gap between first and last number)
    if nums:
        first = nums[0]
        last = nums[-1]
        exp_first = start_n if start_n is not None else first
        length = last - exp_first + 1
        if length < 1:
            add(2, "题号区间非法: [%d..%d] 长度=%d" % (exp_first, last, length), "page", "hard")
        elif len(nums) != length:
            add(2, "条目数=%d 但题号区间 [%d..%d] 长度=%d" % (len(nums), exp_first, last, length),
                "page", "hard")

    # rule 3: reading order -- left column fully before right column, no interleave
    if len(col_tags) > 1:
        col_nums = {}
        for n, c in zip(nums, item_col):
            col_nums.setdefault(c, []).append(n)
        col_order = sorted(col_nums, key=lambda t: cols[t][0])
        for c in col_order:
            seq = col_nums[c]
            for i in range(1, len(seq)):
                if seq[i] <= seq[i - 1]:
                    add(3, "列 %s 题号非递增: %d -> %d" % (c, seq[i - 1], seq[i]),
                        "column %s" % c, "hard")
        for a, b in zip(col_order, col_order[1:]):
            if col_nums[a] and col_nums[b]:
                if min(col_nums[b]) <= max(col_nums[a]):
                    add(3, "题号跨栏交错: 列 %s 最大=%d >= 列 %s 最小=%d" %
                           (a, max(col_nums[a]), b, min(col_nums[b])),
                        "columns %s/%s" % (a, b), "hard")

    # rule 4: boxes do not overlap, do not run out of bounds, do not cross columns
    TOL = 2.0
    all_boxes = []
    for it, c in zip(items, item_col):
        for b in boxes_of_item(it, cols, col_rows):
            all_boxes.append((b, it["n"], c))
    for b, n, c in all_boxes:
        x0b, y0b, x1b, y1b = b
        cx = cols[c]
        if x0b < cx[0] - TOL or x1b > cx[1] + TOL:
            add(4, "框越界: n=%d @%.1f,%.1f,%.1f,%.1f 超出列 %s [%.0f,%.0f]" %
                   (n, x0b, y0b, x1b, y1b, c, cx[0], cx[1]), "n=%d" % n, "hard")
        if y0b < Y0 - TOL or y1b > Y1 + TOL:
            add(4, "框越界(纵向): n=%d @%.1f,%.1f,%.1f,%.1f 超出 [%.0f,%.0f]" %
                   (n, x0b, y0b, x1b, y1b, Y0, Y1), "n=%d" % n, "hard")
        for c2 in col_tags:
            if c2 == c:
                continue
            ox = min(x1b, cols[c2][1]) - max(x0b, cols[c2][0])
            if ox > TOL:
                add(4, "框跨栏: n=%d @%.1f,%.1f,%.1f,%.1f 跨入列 %s" %
                       (n, x0b, y0b, x1b, y1b, c2), "n=%d" % n, "hard")
    for i in range(len(all_boxes)):
        for j in range(i + 1, len(all_boxes)):
            a, na, _ = all_boxes[i]
            b2, nb, _ = all_boxes[j]
            ox = min(a[2], b2[2]) - max(a[0], b2[0])
            oy = min(a[3], b2[3]) - max(a[1], b2[1])
            if ox > TOL and oy > TOL:
                add(4, "框重叠: n=%d 与 n=%d (x重叠%.1f y重叠%.1f)" % (na, nb, ox, oy),
                    "n=%d/n=%d" % (na, nb), "hard")

    # page line spacing (from the page's own gap distribution), used by rules 6 and 7
    all_gaps = []
    for c in col_tags:
        rows = col_rows[c]
        for i in range(1, len(rows)):
            g = rows[i]["y0"] - rows[i - 1]["y1"]
            if g > 0:
                all_gaps.append(g)
    line_spacing = (sorted(all_gaps)[len(all_gaps) // 2] if all_gaps else 0.0)

    # rule 5: option count must be 0 (fill-in), 2, or 4 (multiple choice). 3 or 5 is
    # suspicious (usually a missed/wrong option letter).
    for it in items:
        oc = len(it.get("opt", []))
        if oc not in (0, 2, 4):
            add(5, "选项数=%d (应为0/2/4)" % oc, "n=%d" % it["n"], "soft")

    # rule 6: stem box height >= page line spacing (1.0x, -1 CSS absorbs row/OCR
    # quantization so a single-line stem is never falsely flagged)
    if line_spacing > 0:
        for it, c in zip(items, item_col):
            for s in it.get("stem", []):
                b = expand_span(s, cols, col_rows)
                if not b:
                    continue
                h = b[3] - b[1]
                if h < line_spacing - 1.0:
                    add(6, "题干框高度 %.1f < 行距 %.1f" % (h, line_spacing),
                        "n=%d stem=%s" % (it["n"], s), "soft")

    # rule 7: coverage -- every body text row (OCR text, not a header) must fall
    # inside some item box of its column. Defaults to soft (likely title / header /
    # footer), and escalates to hard only when the uncovered row is tall AND its OCR
    # text carries a question-number-style marker -- i.e. a real dropped question.
    for c in col_tags:
        rows = col_rows[c]
        text_rows = set(col_ocr_rows.get(c, set()))
        headers = set(col_headers.get(c, set()))
        body = sorted(r for r in text_rows if r not in headers)
        if not body:
            continue
        col_boxes = [b for (b, _, cc) in all_boxes if cc == c]
        for r in body:
            ymid = (rows[r]["y0"] + rows[r]["y1"]) / 2.0
            covered = any(b[1] - TOL <= ymid <= b[3] + TOL for b in col_boxes)
            if covered:
                continue
            h = rows[r]["y1"] - rows[r]["y0"]
            texts = col_ocr_text.get(c, {}).get(r, [])
            has_num = any(NUM_RE.match((t or "").strip()) for t in texts)
            tall = line_spacing > 0 and h >= COVERAGE_UPGRADE_HEIGHT_X * line_spacing
            sev = "hard" if (tall and has_num) else "soft"
            if sev == "soft":
                msg = "疑似标题/页眉/页脚行未归入任何题: 列 %s row%d (y %.1f-%.1f h=%.1f)" % \
                      (c, r, rows[r]["y0"], rows[r]["y1"], h)
            else:
                msg = "疑似漏题: 未覆盖行含题号且高度异常: 列 %s row%d (y %.1f-%.1f h=%.1f)" % \
                      (c, r, rows[r]["y0"], rows[r]["y1"], h)
            add(7, msg, "column %s row%d" % (c, r), sev)

    return {"hard": hard, "soft": soft}


# --------------------------------------------------------------------------- #
# q-page analysis + item building (segmentation logic kept verbatim).         #
# --------------------------------------------------------------------------- #

def analyze_q(rgb, gray, SS, cols, Y0, Y1, TH, MIN_INK):
    """Per-column rows + OCR anchors/letters/headers/subq/ocr-rows.

    This is the analysis half of the original build_q, split out so the page gate
    can consume the same measurements the draft builder uses. The row detection and
    OCR rules are unchanged.
    """
    col_tags = sorted(cols.keys(), key=lambda t: cols[t][0])
    col_rows, col_anchors, col_letters = {}, {}, {}
    col_headers, col_subq, col_ocr_rows, col_ocr_text = {}, {}, {}, {}

    for tag in col_tags:
        x0, x1 = cols[tag]
        rows = detect_rows(gray, Y0, Y1, x0, x1, TH, MIN_INK, SS, GAP_CSS, MIN_H)
        col_rows[tag] = rows

        narrow = ocr_strip(rgb, x0, min(x1, x0 + 55.0), Y0, Y1, SS)
        full = ocr_strip(rgb, x0, x1, Y0, Y1, SS)

        anchors = []
        for d in narrow:
            m = NUM_RE.match(d["text"])
            if m and (d["x0"] - x0) < 25.0:
                anchors.append({"n": int(m.group(1)), "conf": d["conf"],
                                "y": yc(d), "x0": d["x0"], "text": d["text"]})

        anchors.sort(key=lambda a: a["y"])
        dedup = []
        for a in anchors:
            if dedup and abs(a["y"] - dedup[-1]["y"]) < 12 and a["n"] == dedup[-1]["n"]:
                if a["conf"] > dedup[-1]["conf"]:
                    dedup[-1] = a
                continue
            dedup.append(a)
        col_anchors[tag] = dedup

        letters_by_row = {}
        headers = set()
        subq = set()
        ocr_rows = set()
        ocr_text = {}
        for d in narrow + full:
            r = row_for_top(d["y0"], rows)
            if r is None:
                continue
            ocr_rows.add(r)
            ocr_text.setdefault(r, []).append(d["text"])
            lets = OPT_IN_TEXT.findall(d["text"])
            if lets:
                s = letters_by_row.setdefault(r, set())
                for L in lets:
                    s.add(L.upper())
            if is_header(d["text"]):
                headers.add(r)
            if SUBQ_RE.match(d["text"]):
                subq.add(r)
        col_letters[tag] = letters_by_row
        col_headers[tag] = headers
        col_subq[tag] = subq
        col_ocr_rows[tag] = ocr_rows
        col_ocr_text[tag] = ocr_text

    return {
        "cols": cols,
        "col_tags": col_tags,
        "col_rows": col_rows,
        "col_anchors": col_anchors,
        "col_letters": col_letters,
        "col_headers": col_headers,
        "col_subq": col_subq,
        "col_ocr_rows": col_ocr_rows,
        "col_ocr_text": col_ocr_text,
        "Y0": Y0, "Y1": Y1,
    }


def build_items_q(analysis, gray, SS):
    """Build items/review from the analysis. This is the second half of the original
    build_q, unchanged except that each item also records its column tag in item_col
    (used by the invariants; never written into the spec)."""
    cols = analysis["cols"]
    col_tags = analysis["col_tags"]
    col_rows = analysis["col_rows"]
    col_anchors = analysis["col_anchors"]
    col_letters = analysis["col_letters"]
    col_headers = analysis["col_headers"]
    col_subq = analysis["col_subq"]
    col_ocr_rows = analysis["col_ocr_rows"]

    items = []
    review = []
    low_count = 0
    gap_note = []
    item_col = []

    # Page-top continuation: when the first numbered question is n>1, the rows above
    # it may be the tail of question n-1 (usually starting with a "(n)" sub-marker).
    # Emit it as a guessed number + low, instead of silently dropping the rows.
    prev_n = None
    left_tag = col_tags[0]
    if col_anchors[left_tag]:
        a0 = col_anchors[left_tag][0]
        first_anchor_row = row_of(a0["y"], col_rows[left_tag])
        if a0["n"] > 1 and first_anchor_row > 0:
            lrows = col_rows[left_tag]
            k = 0
            for r in range(first_anchor_row - 1):
                g = lrows[r + 1]["y0"] - lrows[r]["y1"]
                if g > 60.0 or (r + 1) in col_headers[left_tag]:
                    break
                k = r + 1
            if any(r in col_subq[left_tag] for r in range(0, k + 1)):
                cont_n = a0["n"] - 1
                span = stem_box(left_tag, lrows, 0, k, gray, SS)
                items.append({"n": cont_n, "stem": [span]})
                review.append("n=%-3d stem %-22s conf=0.40 low: page-top-continuation"
                              % (cont_n, span))
                low_count += 1
                gap_note.append("%s top continuation n=%d rows0-%d" % (left_tag, cont_n, k))
                prev_n = cont_n
                item_col.append(left_tag)

    for tag in col_tags:
        x0, x1 = cols[tag]
        rows = col_rows[tag]
        anchors = col_anchors[tag]
        letters_by_row = col_letters[tag]
        headers = col_headers[tag]
        subq = col_subq[tag]
        gap_stats = page_gap_stats(rows)
        sponge_thr = gap_stats["sponge"]
        text_rows = set(col_ocr_rows[tag])
        # rows before first anchor -> possible missed top question / header
        if anchors:
            first_row = row_of(anchors[0]["y"], rows)
            if first_row > 0:
                gap_note.append("%s rows0-%d before first anchor" % (tag, first_row - 1))
        for ai, a in enumerate(anchors):
            arow = row_of(a["y"], rows)
            nxt_row = row_of(anchors[ai + 1]["y"], rows) if ai + 1 < len(anchors) else len(rows)
            # question block: rows [arow .. nxt_row-1], truncated at a big gap or a
            # section-header row (一、/知识点N/第N课时/基础题...).
            block_end = arow
            for r in range(arow, nxt_row - 1):
                if rows[r + 1]["y0"] - rows[r]["y1"] > GAP_SPLIT:
                    break
                if (r + 1) in headers:
                    break
                block_end = r + 1
            else:
                block_end = nxt_row - 1

            # option letters inside the block
            opt_rows = sorted(r for r in letters_by_row if arow <= r <= block_end)
            first_opt = None
            for r in opt_rows:
                if r > arow:
                    first_opt = r
                    break
            stem_end = (first_opt - 1) if first_opt is not None else block_end

            # stem spans. Split on two signals, in order:
            #  1. section-size gap (> GAP_SPLIT) -> new span
            #  2. internal blank band wider than the page's own normal line spacing
            #     -> keep the box but assert it merged several segments (low)
            # A third check flags a stem that mixes text rows with figure rows
            # (ink but no OCR text) -- the text/figure boundary is ambiguous (a
            # figure's own labels may OCR as text), so we flag low, never split.
            stem_spans = []
            stem_flags = []
            if stem_end >= arow:
                seg_start = arow
                for r in range(arow, stem_end):
                    g = rows[r + 1]["y0"] - rows[r]["y1"]
                    if g > GAP_SPLIT:
                        stem_spans.append(stem_box(tag, rows, seg_start, r, gray, SS))
                        seg_start = r + 1
                    elif g > sponge_thr:
                        ymid = (rows[r]["y1"] + rows[r + 1]["y0"]) / 2.0
                        stem_flags.append("内部空白带y=%.1f" % ymid)
                    elif g > STEM_AMBIG and (r + 1) not in subq:
                        stem_flags.append("stem-gap")
                stem_spans.append(stem_box(tag, rows, seg_start, stem_end, gray, SS))
                for rr in range(arow, stem_end + 1):
                    if is_figure_row(rows[rr], x0, x1, text_rows, rr):
                        stem_flags.append("题干含图块")
                        break

            # option entries: @ boxes with the ink's true vertical extent.
            opt_entries = []
            opt_kind = None
            opt_count = 0
            opt_wrap = False
            if first_opt is not None:
                lettered = [r for r in opt_rows if r >= first_opt]
                ks = sorted({len(letters_by_row[r]) for r in lettered})
                if len(lettered) == 1:
                    r0 = lettered[0]
                    k_letters = len(letters_by_row[r0])
                    n_blocks = len(rows[r0]["blocks"])
                    # horizontal options on one row: multiple choice is almost always 4.
                    k = 4 if (k_letters >= 1 and n_blocks >= 4) else k_letters
                    if k < 1:
                        k = 1
                    opt_entries = [fmt_box(ink_box(b, gray, SS))
                                   for b in split_row_boxes(rows[r0], k)]
                    opt_kind = "H"
                    opt_count = k
                elif ks[0] >= 2 and all(len(letters_by_row[r]) == ks[0] for r in lettered):
                    # regular grid: every option row carries the same k (e.g. 2x2 grid).
                    opt_kind = "G"
                    opt_count = ks[0] * len(lettered)
                    for r in lettered:
                        for b in split_row_boxes(rows[r], ks[0]):
                            opt_entries.append(fmt_box(ink_box(b, gray, SS)))
                else:
                    # vertical, possibly with wrapped rows -> exact @ boxes.
                    # A repeated letter on consecutive rows is a wrap of the same
                    # option (OCR may re-read the tail as the letter), not a new one.
                    opt_kind = "V"
                    boxes = []
                    cur = []
                    cur_letters = None
                    for r in range(first_opt, block_end + 1):
                        if r in letters_by_row:
                            lets = letters_by_row[r]
                            if cur and lets == cur_letters:
                                cur.append((r, rows[r]))
                            else:
                                if cur:
                                    i0, j0 = cur[0][0], cur[-1][0]
                                    boxes.append(ink_box(union_box([x[1] for x in cur]),
                                                         gray, SS))
                                    if j0 > i0:
                                        opt_wrap = True
                                cur = [(r, rows[r])]
                                cur_letters = lets
                        else:
                            if cur:
                                cur.append((r, rows[r]))
                    if cur:
                        i0, j0 = cur[0][0], cur[-1][0]
                        boxes.append(ink_box(union_box([x[1] for x in cur]),
                                             gray, SS))
                        if j0 > i0:
                            opt_wrap = True
                    opt_entries = [fmt_box(b) for b in boxes]
                    opt_count = len(boxes)

            # confidence: concrete assertions only. Every low carries at least one
            # assertion; when none fire the item is high (no "this layout is scary").
            conf = 0.90
            reasons = []
            if a["conf"] < 0.75:
                conf -= 0.15; reasons.append("anchor-ocr-low")
            if prev_n is not None:
                if a["n"] == prev_n:
                    conf -= 0.30; reasons.append("重复题号")
                elif a["n"] < prev_n:
                    conf -= 0.40; reasons.append("题号回退")
                elif a["n"] != prev_n + 1:
                    conf -= 0.20; reasons.append("题号跳号")
            for fl in stem_flags:
                conf -= 0.35 if fl.startswith("内部空白带") else 0.25
                reasons.append(fl)
            if opt_entries:
                if opt_wrap:
                    conf -= 0.15; reasons.append("opt-wrap")
                if opt_count not in (2, 4):
                    conf -= 0.10; reasons.append("opt-count=%d" % opt_count)
            conf = max(0.10, min(0.95, round(conf, 2)))
            if conf <= LOW_CONF:
                low_count += 1

            item = {"n": a["n"], "stem": list(stem_spans)}
            if opt_entries:
                item["opt"] = list(opt_entries)
            items.append(item)
            item_col.append(tag)

            stem_s = "+".join(stem_spans)
            opt_s = " opt%d[%s]" % (opt_count, opt_kind) if opt_entries else ""
            flag = ("  low: " + ",".join(reasons)) if conf <= LOW_CONF else ""
            review.append("n=%-3d stem %-22s%s conf=%.2f%s" % (a["n"], stem_s, opt_s, conf, flag))
            prev_n = a["n"]

    return items, review, low_count, gap_note, item_col


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__.strip())
        sys.exit(2)

    img_path = argv[0]
    kind = None
    cols_arg, x_arg, y_arg, out_path, start_arg = None, None, None, None, None
    i = 1
    while i < len(argv):
        k = argv[i]
        if k == "--kind":
            kind = argv[i + 1]; i += 2
        elif k == "--cols":
            cols_arg = argv[i + 1]; i += 2
        elif k == "--x":
            x_arg = argv[i + 1]; i += 2
        elif k == "--y":
            y_arg = argv[i + 1]; i += 2
        elif k == "--out":
            out_path = argv[i + 1]; i += 2
        elif k == "--start":
            start_arg = int(argv[i + 1]); i += 2
        else:
            raise SystemExit("unknown arg " + k)

    if kind not in ("q", "a"):
        raise SystemExit("--kind must be q or a")

    img_path = os.path.abspath(img_path)
    im = Image.open(img_path)
    rgb = im.convert("RGB")
    gray = np.array(im.convert("L"))
    SS = im.width / CANVAS[kind][0]

    Y0, Y1 = parse_range(y_arg, DEFAULT_Y)
    TH = 200 if kind == "q" else 225
    MIN_INK = 20 if kind == "q" else 2

    # image self-check (same as guide.py)
    small = im.convert("L")
    small.thumbnail((600, 600))
    ink = float((np.array(small) < 200).mean())
    log("IMG_OK %s %dx%d ink=%.1f%%" % (img_path, im.width, im.height, ink * 100))
    if ink < 0.005:
        raise SystemExit("IMG_BLANK")

    if kind == "q":
        cols = parse_cols(cols_arg) if cols_arg else {k: list(v) for k, v in DEFAULT_COLS.items()}
        build_q(rgb, gray, SS, img_path, cols, Y0, Y1, TH, MIN_INK, out_path,
                ink=ink, img_height=im.height, start_n=start_arg)
    else:
        X0, X1 = parse_range(x_arg, [8.0, 218.0])
        build_a(rgb, gray, SS, img_path, X0, X1, Y0, Y1, TH, MIN_INK, out_path)


def build_q(rgb, gray, SS, img_path, cols, Y0, Y1, TH, MIN_INK, out_path,
            ink=None, img_height=None, start_n=None):
    """Run the full q-page pipeline and return a structured result dict.

    The result is also used by drafts/run_all.py (which suppresses stdout), so the
    printed text and the returned dict carry the same information.
    """
    page = os.path.basename(img_path)
    analysis = analyze_q(rgb, gray, SS, cols, Y0, Y1, TH, MIN_INK)

    profiles = load_profiles()
    if ink is None:
        ink = 0.0
    if img_height is None:
        img_height = gray.shape[0]
    gate_verdict, gate_rows = page_gate(analysis, profiles, ink, SS, img_height, "q",
                                        gray=gray, TH=TH)
    print_gate(gate_verdict, gate_rows)

    if gate_verdict == "C":
        log("REFUSE gate=C 页面不属于已验证版面类型,不出草案")
        log("VERDICT REFUSE")
        return {"page": page, "gate": "C", "verdict": "REFUSE", "items": 0,
                "hard": [], "soft": [], "spec": None}

    items, review, low_count, gap_note, item_col = build_items_q(analysis, gray, SS)

    inv = check_invariants(analysis, items, item_col, start_n)
    hard, soft = inv["hard"], inv["soft"]

    log("\n--- review ---")
    for line in review:
        log(line)
    if gap_note:
        log("GAP_NOTE " + "; ".join(gap_note))
    log("SUMMARY items=%d low=%d" % (len(items), low_count))

    if hard:
        main = hard[0]["rule"]
        for v in hard:
            log("INVARIANT_FAIL rule=%d %s | %s" % (v["rule"], v["msg"], v["where"]))
        for v in soft:
            log("INVARIANT_SOFT rule=%d %s | %s" % (v["rule"], v["msg"], v["where"]))
        log("REFUSE 不变量硬违规 %d 条(主因 rule=%d),整页判废" % (len(hard), main))
        log("VERDICT REFUSE")
        return {"page": page, "gate": gate_verdict, "verdict": "REFUSE",
                "items": len(items), "hard": hard, "soft": soft, "spec": None}

    final_verdict = "B" if (gate_verdict == "B" or soft) else "A"
    for v in soft:
        log("INVARIANT_SOFT rule=%d %s | %s" % (v["rule"], v["msg"], v["where"]))

    spec = {
        "src": img_path.replace("\\", "/"),
        "kind": "q",
        "cols": cols,
        "items": items,
        "gate": gate_verdict,
        "verdict": final_verdict,
        "invariants": {"passed": True, "hard": [], "soft": soft},
    }
    write_out(spec, out_path, img_path, "q")
    log("VERDICT %s" % final_verdict)
    return {"page": page, "gate": gate_verdict, "verdict": final_verdict,
            "items": len(items), "hard": hard, "soft": soft, "spec": out_path}


def build_a(rgb, gray, SS, img_path, X0, X1, Y0, Y1, TH, MIN_INK, out_path):
    rows = detect_rows(gray, Y0, Y1, X0, X1, TH, MIN_INK, SS, GAP_CSS, MIN_H)
    items = []
    for i, r in enumerate(rows):
        b = union_box([r])
        items.append({"n": i + 1, "stem": [fmt_box(b)]})
    spec = {
        "src": img_path.replace("\\", "/"),
        "kind": "a",
        "x": [X0, X1],
        "y": [Y0, Y1],
        "items": items,
        "gate": "B",
        "verdict": "B",
        "invariants": {"passed": True, "hard": [], "soft": []},
    }
    write_out(spec, out_path, img_path, "a")
    log("\n--- review ---")
    for i, r in enumerate(rows):
        b = union_box([r])
        log("n=%-3d %s conf=0.30 low: answer-row skeleton (manual @ needed)" % (i + 1, fmt_box(b)))
    log("SUMMARY items=%d low=%d (answer pages: rows are a skeleton, n is a guess)" % (len(items), len(items)))
    log("VERDICT B")
    return {"page": os.path.basename(img_path), "gate": "B", "verdict": "B",
            "items": len(items), "hard": [], "soft": [], "spec": out_path}


def write_out(spec, out_path, img_path, kind):
    if out_path is None:
        base = os.path.splitext(os.path.basename(img_path))[0]
        out_path = "%s_%sspec.proposed.json" % (base, kind)
    text = json.dumps(spec, ensure_ascii=False, indent=1)
    io.open(out_path, "w", encoding="utf-8").write(text)
    log("WROTE %s" % os.path.abspath(out_path))


if __name__ == "__main__":
    main()
