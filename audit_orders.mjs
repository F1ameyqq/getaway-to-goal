// 只读审计工具：把库里每个 order_in_level 的标注条数按类型打出来，并检查畸形记录。
// 同时支持单条 dump 和左侧树 dump。全程只读，不写库。用于每次录入前后对账。
//
// 用法 A（联网，经 ego，只读）:
//   .\run_ego.ps1 -Js .\audit_orders.mjs -Out "$env:TEMP\audit.txt" -TimeoutSec 240
//   可选（需先由 run_ego.ps1 的 prelude 传入，或直接编辑本文件）:
//     AUDIT_LO / AUDIT_HI   只打这个题号范围
//     AUDIT_ORDER           单条 dump 这个题号
//     AUDIT_TREE=1          改为 dump 左侧树（另需 AUDIT_LESSON；可选 AUDIT_QPAGE/AUDIT_APAGE）
//
// 用法 B（离线，读本地 dump，不需要浏览器，纯 node）:
//   node audit_orders.mjs <rows.json> [--lo X] [--hi Y] [--order N]
//   rows.json 是标注行数组，每行含 order_in_level / type / page_index / directory_id / created_at 等。
import fs from "node:fs";
import { P } from "./config.mjs";
import { groupByOrder, preflightReport, auditSummary } from "./ordercheck.mjs";

function dumpOrder(rows, order) {
  const by = groupByOrder(rows);
  const list = by[String(order)] || [];
  console.log(`ORDER ${order} rows=${list.length}`);
  for (const r of list) {
    console.log("REC " + JSON.stringify({
      order: r.order_in_level, type: r.type, t: r.created_at,
      pg: r.page_index, img: String(r.image_path || "").split("/").pop(),
      box: r.rect_bbox, rid: r.rect_id, par: r.parent_rect_id,
      dir: r.directory_id, lvl: r.belong_to_level,
    }));
  }
}

function printReport(rows, { lo = null, hi = null, order = null, now = null } = {}) {
  const s = auditSummary(rows, { lo, hi });
  const pre = preflightReport(rows, { now });
  console.log(`AUDIT total=${s.total} orders=${s.orders} min=${s.min ?? "-"} max=${s.max ?? "-"} holes=${pre.holes.length}`);
  for (const l of s.lines) console.log(`  ${l.order} q=${l.q} w=${l.w} a=${l.a} other=${l.other}`);
  if (pre.holes.length) console.log("HOLES " + JSON.stringify(pre.holes.slice(-20)));
  for (const a of pre.anomalies) console.log("ANOMALY " + a);
  if (!pre.anomalies.length) console.log("CLEAN 0");
  if (order !== null) dumpOrder(rows, order);
}

function parseArgs(argv) {
  const out = { lo: null, hi: null, order: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--lo") out.lo = Number(argv[++i]);
    else if (argv[i] === "--hi") out.hi = Number(argv[++i]);
    else if (argv[i] === "--order") out.order = Number(argv[++i]);
  }
  return out;
}

async function treeDump() {
  const { restore } = await import("./restorefn.mjs");
  const lesson = process.env.AUDIT_LESSON;
  if (!lesson) throw new Error("--tree 需要 $env:AUDIT_LESSON");
  const qPage = Number(process.env.AUDIT_QPAGE || 34);
  const aPage = Number(process.env.AUDIT_APAGE || 175);
  const ctx = await restore({ qPage, aPage, lesson });
  console.log("RESTORE " + JSON.stringify({ cur: ctx.cur, dir: ctx.dirLabel, dirId: ctx.dirId, counts: ctx.counts }));
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);
  const out = await page.evaluate(() => {
    const rows = [];
    let idx = -1;
    document.querySelectorAll(".el-tree-node").forEach((n) => {
      const c = n.querySelector(":scope > .el-tree-node__content");
      if (!c) return;
      const isQ = !!c.querySelector(".question-node");
      const t = (c.textContent || "").replace(/\s+/g, " ").trim();
      if (isQ) idx += 1;
      rows.push({ i: isQ ? idx : null, t: t.slice(0, 48) });
    });
    const labels = [...document.querySelectorAll("button, .el-button, a, span, div")]
      .map((e) => (e.textContent || "").replace(/\s+/g, " ").trim())
      .filter((s) => s && s.length <= 12 && /目录编辑|应用变更|重置|取消|删除题目|删除目录|添加子目录|编辑名称/.test(s));
    return { rows, labels: [...new Set(labels)] };
  });
  console.log("QNODES " + out.rows.filter((r) => r.i !== null).length);
  for (const r of out.rows) {
    if (r.i === null) console.log("DIR  " + r.t);
    else console.log("Q%03d %s", r.i, r.t);
  }
  console.log("LABELS " + JSON.stringify(out.labels));
}

const fileArg = process.argv[2];
if (fileArg && fs.existsSync(fileArg)) {
  const rows = JSON.parse(fs.readFileSync(fileArg, "utf8"));
  printReport(rows, { ...parseArgs(process.argv.slice(2)), now: null });
} else if (process.env.AUDIT_TREE === "1") {
  await treeDump();
} else {
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);
  const tok = await page.evaluate(() => JSON.parse(localStorage.getItem("user")).access_token);
  const r = await page.fetch(`/qieti/api/annotate_pic/get_manual_annotations_unified/${P.fileId}`, {
    headers: { authorization: "Bearer " + tok },
    timeout: 30000,
  });
  const j = JSON.parse(r.body);
  const rows = j.data || [];
  printReport(rows, {
    lo: process.env.AUDIT_LO ? Number(process.env.AUDIT_LO) : null,
    hi: process.env.AUDIT_HI ? Number(process.env.AUDIT_HI) : null,
    order: process.env.AUDIT_ORDER ? Number(process.env.AUDIT_ORDER) : null,
    now: Date.now(),
  });
}
