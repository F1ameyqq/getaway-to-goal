# -*- coding: utf-8 -*-
"""Driver: run propose_spec on each page and save the review log + proposal json.

Usage: python -I run_blind.py <tag>  where tag in {baseline, fixed}
Reads the page list below; writes drafts/_<tag>/<page>_prop.json and <page>.log
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = r"C:\Users\ASUS\ego-install-tmp\srcpages"
PAGES = ["p29", "p30", "p31", "p32", "p33", "p34", "p35"]

def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    outdir = os.path.join(HERE, "_" + tag)
    os.makedirs(outdir, exist_ok=True)
    for p in PAGES:
        img = os.path.join(SRC, p + "_hi.jpg")
        prop = os.path.join(outdir, p + "_prop.json")
        logp = os.path.join(outdir, p + ".log")
        cp = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", os.path.join(ROOT, "propose_spec.py"),
             img, "--kind", "q", "--out", prop],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        with open(logp, "w", encoding="utf-8") as f:
            f.write(cp.stdout)
            f.write(cp.stderr)
        print("%s rc=%d prop=%s log=%s" % (p, cp.returncode, prop, logp))

if __name__ == "__main__":
    main()
