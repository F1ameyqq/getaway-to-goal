# -*- coding: utf-8 -*-
"""Probe a page's row/anchor/subq structure for debugging propose_spec."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import propose_spec as P
from PIL import Image
import numpy as np

def main():
    img = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else 'L'
    col = {'L': [44.0, 258.0], 'R': [262.0, 497.0]}[tag]
    x0, x1 = col
    im = Image.open(img)
    rgb = im.convert("RGB")
    gray = np.array(im.convert("L"))
    SS = im.width / P.CANVAS['q'][0]
    rows = P.detect_rows(gray, 20, 660, x0, x1, 200, 20, SS, P.GAP_CSS, P.MIN_H)
    print("SS=%.3f col=%s nrows=%d" % (SS, tag, len(rows)))
    # line gap distribution
    gaps = []
    for i in range(1, len(rows)):
        gaps.append(rows[i]['y0'] - rows[i-1]['y1'])
    gaps_sorted = sorted(gaps)
    import statistics
    med = statistics.median(gaps) if gaps else 0
    print("gaps=%s" % [round(g,1) for g in gaps])
    print("gap median=%.1f q25=%.1f q75=%.1f" % (med, np.percentile(gaps,25), np.percentile(gaps,75)))
    # anchors via narrow OCR
    narrow = P.ocr_strip(rgb, x0, min(x1, x0+55.0), 20, 660, SS)
    full = P.ocr_strip(rgb, x0, x1, 20, 660, SS)
    print("-- narrow OCR --")
    for d in narrow:
        print("  y=%.1f-%.1f x=%.1f conf=%.2f text=%r" % (d['y0'], d['y1'], d['x0'], d['conf'], d['text']))
    print("-- full OCR (subq/letters/headers) --")
    for d in full:
        flags = []
        if P.SUBQ_RE.match(d['text']): flags.append('SUBQ')
        if P.OPT_IN_TEXT.search(d['text']): flags.append('OPT')
        if P.is_header(d['text']): flags.append('HDR')
        if P.NUM_RE.match(d['text']): flags.append('NUM')
        if flags:
            print("  y=%.1f-%.1f conf=%.2f text=%r %s" % (d['y0'], d['y1'], d['conf'], d['text'], ','.join(flags)))

if __name__ == "__main__":
    main()
