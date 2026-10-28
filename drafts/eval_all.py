# -*- coding: utf-8 -*-
"""Run eval_q.py for each page against a tag's proposal dir. Prints comparison."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = r"C:\Users\ASUS\ego-install-tmp\srcpages"
PAGES = ["p29", "p30", "p31", "p32", "p33", "p34", "p35"]

def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    for p in PAGES:
        std = os.path.join(SRC, p + "_qspec.json")
        prop = os.path.join(HERE, "_" + tag, p + "_prop.json")
        print("\n########## %s ##########" % p)
        cp = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", os.path.join(HERE, "eval_q.py"), std, prop],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        print(cp.stdout, end="")
        if cp.returncode != 0:
            print("EVAL_RC=%d" % cp.returncode)
            print(cp.stderr)

if __name__ == "__main__":
    main()
