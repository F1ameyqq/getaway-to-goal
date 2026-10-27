# -*- coding: utf-8 -*-
"""把 measure_page.py 的两份输出合成 pages/pNN.json（录入用）。

用法:
  make_page.py <q.json> <a.json|-> <qPage> <aPage> <types.json> <out.json>

types.json: {"1":"选择","2":"填空",...}
  给 "-" 表示按 w 数量自动判：w==4 -> 选择，否则 填空。
a.json 给 "-" 表示这页没有答案图，全部 a=[]。
"""
import sys, json, io

q_path, a_path, qpage, apage, types_path, out_path = sys.argv[1:7]
q_items = json.load(io.open(q_path, encoding="utf-8"))

a_by_n = {}
if a_path != "-":
    for it in json.load(io.open(a_path, encoding="utf-8")):
        a_by_n[it["n"]] = it.get("q", [])

types = None
if types_path != "-":
    types = json.load(io.open(types_path, encoding="utf-8"))

# 把 measure_page.py 的自检结果带进 pages json，dry run 时会打出来。
# 这样即使 agent 跳过了 measure 那一步，警告也躲不掉。
checks = []
for p in (q_path, a_path):
    if p == "-":
        continue
    try:
        c = io.open(p + ".check.txt", encoding="utf-8").read().strip()
        checks.extend(x for x in c.splitlines() if x)
    except FileNotFoundError:
        checks.append("MISSING_CHECK %s (measure_page.py 未跑或未落盘自检)" % p)

items = []
for it in q_items:
    n = it["n"]
    if types is not None and str(n) in types:
        t = types[str(n)]
    else:
        t = "选择" if len(it.get("w", [])) == 4 else "填空"
    items.append({
        "n": n,
        "type": t,
        "q": it.get("q", []),
        "w": it.get("w", []),
        "a": a_by_n.get(n, []),
    })

out = {"qPage": int(qpage), "aPage": int(apage), "_check": checks, "items": items}
io.open(out_path, "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, indent=1))
print("wrote %s  %d items  (no-answer: %s)" % (
    out_path, len(items),
    ",".join(str(i["n"]) for i in items if not i["a"]) or "-"))
if checks:
    print("CHECK_TOTAL %d carried from measure_page.py -- see pages json _check" % len(checks))
else:
    print("CHECK_CLEAN")
