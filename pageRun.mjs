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
//   3. 提交后逐题对账（order / 归属课时 directory_id / page_index / 框数）—— 服务端回答，硬证据
//   4. 第一次提交前先残局预检 —— 半途死掉的运行留下的残局必须被挡住，不能被继承
import { readFile } from "node:fs/promises";
import { restore } from "./restorefn.mjs";
import { run } from "./lib.mjs";
import { P } from "./config.mjs";
import { preflightReport, reconcileOne } from "./ordercheck.mjs";

async function fetchAnnotations(fileId) {
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);
  const tok = await page.evaluate(() => JSON.parse(localStorage.getItem("user")).access_token);
  const r = await page.fetch(`/qieti/api/annotate_pic/get_manual_annotations_unified/${fileId}`, {
    headers: { authorization: "Bearer " + tok },
    timeout: 30000,
  });
  const j = JSON.parse(r.body);
  return (j.data || []).map((a) => ({
    order_in_level: a.order_in_level,
    type: a.type,
    page_index: a.page_index,
    directory_id: a.directory_id,
    belong_to_level: a.belong_to_level,
    rect_id: a.rect_id,
    parent_rect_id: a.parent_rect_id,
    rect_bbox: a.rect_bbox,
    created_at: a.created_at,
    image_path: a.image_path,
  }));
}

// 逐题对账：服务端回读，独立证明这一题的 order / 归属课时 / 页 / 框数。
// 任何一条不符都抛错，由调用方立刻停止整个运行，不许自动重试。
async function verifyOne(order, item, { fileId, dirId, qPage, aPage }) {
  const rows = (await fetchAnnotations(fileId)).filter((r) => String(r.order_in_level) === String(order));
  const problems = reconcileOne(order, rows, {
    directoryId: dirId,
    qPage,
    aPage,
    q: item.q.length,
    w: item.w.length,
    a: item.a.length,
  });
  if (problems.length)
    throw new Error(`第 ${item.n} 题 (order ${order}) 对账失败: ${problems.join("；")}`);
}

export async function main(coordFile, opts = {}) {
  // 两种格式都收：纯数组，或 { qPage, aPage, lesson, items: [...] }
  const raw = JSON.parse(await readFile(coordFile, "utf8"));
  const items = Array.isArray(raw) ? raw : raw.items;
  if (!Array.isArray(items) || !items.length) throw new Error("坐标文件为空: " + coordFile);
  const qPage = opts.qPage || raw.qPage || 28;
  const aPage = opts.aPage || raw.aPage || 174;
  const lesson = opts.lesson || raw.lesson || null;
  // 这一页开跑之前，目标课时里应该已经有多少题（一课多页时由上一页累积而来）。
  // 对不上就是残局或跑错了页——停，报出实际值。
  const expectBefore = typeof raw.expectBefore === "number" ? raw.expectBefore : 0;

  const from = opts.from || items[0].n;
  const to = opts.to || items[items.length - 1].n;
  const todo = items.filter((it) => it.n >= from && it.n <= to);
  if (!todo.length) throw new Error(`没有 n 在 ${from}..${to} 的题`);

  if (opts.dry) {
    console.log(`DRY ${coordFile}: 页 ${qPage}/${aPage}，共 ${items.length} 题，将跑 ${todo.length} 题 (n=${todo.map((i) => i.n).join(",")})`);
    if (lesson) console.log(`LESSON ${lesson}`);
    else console.log("LESSON_MISSING -- 没有 lesson 字段，真跑时 restore 会中止");
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

  if (!lesson) throw new Error("坐标文件缺 lesson 字段（课时名）—— 拒绝按题号推算落点，请先 prepare_page.py --lesson 写入");

  const done = [], failed = [];
  const t0 = Date.now();
  const fileId = opts.fileId || P.fileId;
  let firstRestore = true;
  let expectedCur = null;

  for (const it of todo) {
    const ts = Date.now();
    try {
      const r0 = Date.now();
      const ctx = await restore({ qPage, aPage, lesson });
      const restoreMs = Date.now() - r0;
      if (firstRestore) {
        firstRestore = false;
        // 残局预检（第一次提交之前，只读）。必须放在第一次 restore 之后：
        // 此时页面已导航到平台 origin，localStorage 里的 token 才可读。
        const preRows = await fetchAnnotations(fileId);
        // 「有人在写」的精确判据：观察窗内题数/最大号有没有变化。
        // 以前用"近 10 分钟有新记录"当阻断，会把我们上一页刚写的记录当成外人（今天误拦两次）。
        const pre2 = preflightReport(await (async () => { await new Promise((r) => setTimeout(r, 2500)); return fetchAnnotations(fileId); })(), { now: Date.now() });
        const pre1 = preflightReport(preRows, { now: Date.now() - 2500 });
        const moved =
          pre1.orderCount !== pre2.orderCount || String(pre1.maxOrder) !== String(pre2.maxOrder);
        const pre = pre2;
        expectedCur = pre.maxOrder === null ? null : pre.maxOrder + 1;
        console.log(`PREFLIGHT orders=${pre.orderCount} maxOrder=${pre.maxOrder ?? "-"} holes=${pre.holes.length} expectedStart=${expectedCur ?? "（库里无记录，以现状为基线）"}`);
        for (const a of pre.warnings) console.log("PREFLIGHT_WARN " + a);
        if (moved)
          throw new Error(`观察窗内题数在变（${pre1.orderCount}→${pre2.orderCount}），有别人正在写，中止`);
        // 目标课时现有的题数必须等于本页声明的 expectBefore：
        //   多了 = 上一轮半途死掉留下的残局（先 cleanup），
        //   少了 = 前面那页没跑完 / 跑错了课时。
        if (typeof ctx.dirQ !== "number")
          throw new Error(`读不到目标课时「${lesson}」已有题数，无法确认是不是残局——中止（未提交）`);
        if (ctx.dirQ !== expectBefore)
          throw new Error(
            `目标课时「${lesson}」里已有 ${ctx.dirQ} 题，本页要求开跑前是 ${expectBefore} 题——中止（多了先 cleanup_orders.mjs，少了说明上一页没跑完）`
          );
        if (expectedCur !== null && String(ctx.cur) !== String(expectedCur))
          throw new Error(`起始题号对不上：平台当前题目=${ctx.cur}，期望=${expectedCur}（库里最大 order ${pre.maxOrder} + 1）——中止`);
      }
      if (!ctx.dirId)
        throw new Error(`读不到选中课时「${lesson}」的 directory_id，无法做提交后落点对账——中止（未提交）`);
      const out = await run({
        n: it.n, expectCur: ctx.cur, order: ctx.cur,
        q: it.q, w: it.w, a: it.a, type: it.type, quiet: true,
      });
      const ms = Date.now() - ts;
      // out.T 是 lib.mjs 里的累计时间点（相对 run() 开始）。
      // 拆成各阶段耗时，restore 之外的 11–24s 到底花在哪，一眼能看出来。
      const stages = {};
      let prev = 0;
      for (const [k, v] of out.T || []) {
        stages[k] = v - prev;
        prev = v;
      }
      const runMs = ms - restoreMs;
      if (runMs > prev) stages.tail = runMs - prev;
      // 逐题对账：任一不符立即抛错，停止整个运行。
      await verifyOne(out.order, it, { fileId, dirId: ctx.dirId, qPage, aPage });
      done.push({ n: it.n, order: out.order, ms, restoreMs, stages });
      console.log(`n=${it.n}\torder=${out.order}\tOK\t${ms}ms\trestore=${restoreMs}ms`);
      if (process.env.RESTORE_TIMING) console.log("  stages " + JSON.stringify(stages));
    } catch (e) {
      const ms = Date.now() - ts;
      failed.push({ n: it.n, err: e.message, ms });
      console.log(`n=${it.n}\tFAIL\t${ms}ms\t${e.message}`);
      break;
    }
  }

  // 最后的整页回读作为汇总（逐题对账已经在每道题提交后做过，且会中止）。
  let checked = null;
  if (!opts.noCheck && done.length) {
    try {
      const rows = await fetchAnnotations(fileId);
      const wantSet = new Set(done.map((d) => String(d.order)));
      const m = {};
      for (const a of rows) {
        const k = String(a.order_in_level);
        if (!wantSet.has(k)) continue;
        (m[k] = m[k] || { q: 0, w: 0, a: 0 });
        if (a.type === "question") m[k].q++;
        else if (a.type === "choice") m[k].w++;
        else if (a.type === "answer") m[k].a++;
      }
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
