# -*- coding: utf-8 -*-
"""Compare a proposed qspec against the hand-written standard qspec, box by box.

Usage: python -I eval_q.py <std_spec.json> <proposed_spec.json>
Runs measure_page.py on both (grow 0), then reports per-n stem/opt count and
box-center deviation in CSS px.
"""
import io, json, os, subprocess, sys, math

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run_measure(spec):
    out = os.path.join(HERE, os.path.splitext(os.path.basename(spec))[0] + "_eval_out.json")
    cp = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", os.path.join(ROOT, "measure_page.py"), spec, out, "0"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if cp.returncode != 0:
        raise SystemExit(cp.stderr or cp.stdout)
    return json.load(io.open(out, encoding="utf-8")), cp.stdout


def css_of_src(b, s_src, pad_x, pad_y):
    return [b[0] * s_src + pad_x, b[1] * s_src + pad_y,
            b[2] * s_src + pad_x, b[3] * s_src + pad_y]


def center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def dev(c1, c2):
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])


def main():
    std_path, prop_path = sys.argv[1], sys.argv[2]
    std, std_out = run_measure(std_path)
    prop, prop_out = run_measure(prop_path)

    # s_src / pad printed by measure_page
    s_src = 0.395216
    pad_x, pad_y = 18.81, 0.0

    std_by_n = {it["n"]: it for it in std}
    prop_by_n = {it["n"]: it for it in prop}

    print("n | stem c | opt c | stem dev (CSS) | opt dev (CSS)")
    print("-" * 72)
    for n in sorted(std_by_n):
        s = std_by_n[n]
        p = prop_by_n.get(n)
        if p is None:
            print("n=%-3d MISSING in proposed" % n)
            continue
        s_stem = s["q_css"]  # CSS boxes
        p_stem = p["q_css"]
        stem_c = (len(s_stem), len(p_stem))
        s_opt = [css_of_src(b, s_src, pad_x, pad_y) for b in s["w"]]
        p_opt = [css_of_src(b, s_src, pad_x, pad_y) for b in p["w"]]
        opt_c = (len(s_opt), len(p_opt))

        stem_devs = []
        for i in range(min(len(s_stem), len(p_stem))):
            stem_devs.append(round(dev(center(s_stem[i]), center(p_stem[i])), 1))
        opt_devs = []
        for i in range(min(len(s_opt), len(p_opt))):
            opt_devs.append(round(dev(center(s_opt[i]), center(p_opt[i])), 1))

        print("n=%-3d stem=%d/%d opt=%d/%d stem_dev=%s opt_dev=%s" % (
            n, stem_c[0], stem_c[1], opt_c[0], opt_c[1],
            stem_devs, opt_devs,
        ))


if __name__ == "__main__":
    main()
