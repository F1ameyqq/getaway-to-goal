// 一次调用跑完一整页：坐标 JSON → 逐题 (restore + run) → 服务端回读校验
//
// 用法（ego-browser 每个 -e 都是新进程，所以导出 main 而不是顶层执行）：
//   ego-browser nodejs -e "const m=await import('file:///<本目录>/pageRun.mjs'); await m.main('<本目录>/pages/p33.json')"
//
// 选项：
//   { from: 5 }       从第 5 题开始（前面已成功的不重跑）
//   { dry: true }     只解析坐标、打印计划，不碰浏览器（可直接用 node 跑，不需要 ego）
//   { fileId: "..." } 回读用的书籍 id，默认取 config.json 的 platform.fileId
//   { noCheck: true } 跳过最后的回读
//
// 设计约束（都是血换来的，别为了省时间改掉）：
//   1. 每题都全量 restore —— 提交后平台内部指针会滞后，唯一 100% 可靠的路径
//   2. 出错立刻 break，绝不带病跑下一题 —— 页面状态脏了继续跑就是往库里写垃圾
//   3. 最后回读必须做 —— 框在 != 结构对，只有服务端能回答
import { readFile } from "node:fs/promises";
import { restore } from "./restorefn.mjs";
import { run } from "./lib.mjs";
import { P } from "./config.mjs";

async function readback(orders, fileId) {
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);
  const tok = await page.evaluate(() => JSON.parse(localStorage.getItem("user")).access_token);
  const r = await page.fetch(`/qieti/api/annotate_pic/get_manual_annotations_unified/${fileId}`, {
    headers: { authorization: "Bearer " + tok },
    timeout: 30000,
  });
  const j = JSON.parse(r.body);
  const want = new Set(orders.map(String));
  const m = {};
  for (const a of j.data || []) {
    const k = String(a.order_in_level);
    if (!want.has(k)) continue;
    (m[k] = m[k] || { q: 0, w: 0, a: 0 });
    if (a.type === "question") m[k].q++;
    else if (a.type === "choice") m[k].w++;
    else if (a.type === "answer") m[k].a++;
  }
  return m;
}

export async function main(coordFile, opts = {}) {
  // 两种格式都收：纯数组，或 { qPage, aPage, items: [...] }
  const raw = JSON.parse(await readFile(coordFile, "utf8"));
  const items = Array.isArray(raw) ? raw : raw.items;
  if (!Array.isArray(items) || !items.length) throw new Error("坐标文件为空: " + coordFile);
  const qPage = opts.qPage || raw.qPage || 28;
  const aPage = opts.aPage || raw.aPage || 174;

  const from = opts.from || items[0].n;
  const to = opts.to || items[items.length - 1].n;
  const todo = items.filter((it) => it.n >= from && it.n <= to);
  if (!todo.length) throw new Error(`没有 n 在 ${from}..${to} 的题`);

  if (opts.dry) {
    console.log(`DRY ${coordFile}: 页 ${qPage}/${aPage}，共 ${items.length} 题，将跑 ${todo.length} 题 (n=${todo.map((i) => i.n).join(",")})`);
    for (const it of todo) console.log(`  n=${it.n}\t${it.type}\tq${it.q.length}\tw${it.w.length}\ta${it.a.length}`);
    // 几何自检结果一路带过来，跳过 measure 那一步也躲不掉
    const chk = Array.isArray(raw) ? [] : (raw._check || []);
    if (chk.length) {
      console.log(`CHECK_WARN ${chk.length} -- 几何自检有警告，别提交：`);
      for (const c of chk) console.log("  " + c);
    } else {
      console.log("CHECK_CLEAN 0（注意：自检不等于框对，overlay 看图仍必做，见 HANDOFF 第一节）");
    }
    return { dry: true, count: todo.length, check: chk.length };
  }

  const done = [], failed = [];
  const t0 = Date.now();

  for (const it of todo) {
    const ts = Date.now();
    try {
      const ctx = await restore({ qPage, aPage });
      const out = await run({
        n: it.n, expectCur: ctx.cur, order: ctx.cur,
        q: it.q, w: it.w, a: it.a, type: it.type, quiet: true,
      });
      const ms = Date.now() - ts;
      done.push({ n: it.n, order: out.order, ms });
      console.log(`n=${it.n}\torder=${out.order}\tOK\t${ms}ms`);
    } catch (e) {
      const ms = Date.now() - ts;
      failed.push({ n: it.n, err: e.message, ms });
      console.log(`n=${it.n}\tFAIL\t${ms}ms\t${e.message}`);
      break;
    }
  }

  // 回读：框在 != 结构对
  let checked = null;
  if (!opts.noCheck && done.length) {
    try {
      const m = await readback(done.map((d) => d.order), opts.fileId || P.fileId);
      checked = done.map((d) => {
        const e = m[String(d.order)] || { q: 0, w: 0, a: 0 };
        const it = todo.find((x) => x.n === d.n);
        // 一题可以有多个框：跨栏题就是左栏末 + 右栏首两个题目框。
        // 这里按实际框数比，别假设「有就 1」——那是 p28 那批单框题留下的假设。
        const want = { q: it.q.length, w: it.w.length, a: it.a.length };
        const ok = e.q === want.q && e.w === want.w && e.a === want.a;
        return { n: d.n, order: d.order, got: e, want, ok };
      });
      for (const c of checked) {
        if (!c.ok) console.log(`n=${c.n}\torder=${c.order}\tREADBACK_MISMATCH\tgot=${JSON.stringify(c.got)} want=${JSON.stringify(c.want)}`);
      }
    } catch (e) {
      console.log(`READBACK_FAILED ${e.message}`);
    }
  }

  const bad = checked ? checked.filter((c) => !c.ok).length : -1;
  console.log(`RESULT ${JSON.stringify({
    ok: done.length,
    fail: failed.length,
    readbackBad: bad,
    totalMs: Date.now() - t0,
    orders: done.map((d) => d.order),
    failed,
  })}`);
  return { done, failed, checked };
}
