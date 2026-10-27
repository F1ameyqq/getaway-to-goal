// 单题执行器：一题一轮，参数逐题显式写。conf = { n, q:[box], w:[box], a:[box], type }
// box = [x1,y1,x2,y2]，坐标是**源图像素**（题目区 1220x1693 / 答案区 1145x1620）
import { P } from "./config.mjs";

const SRC_Q = [1220, 1693];
const SRC_A = [1145, 1620];

export async function run(conf) {
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);
  const T = [];
  const T0 = Date.now();
  const mark = (k) => T.push([k, Date.now() - T0]);

  async function st() {
    return await page.evaluate(() => {
      const cs = [...document.querySelectorAll("canvas.pdf-canvas")].map((c) => {
        const r = c.getBoundingClientRect();
        return { ox: r.x, oy: r.y, w: r.width, h: r.height };
      });
      const btns = {};
      for (const txt of ["题目(Q)", "选项(W)", "答案(A)", "一键识别", "提交修改"]) {
        const els = [...document.querySelectorAll("span,button,div")]
          .filter((e) => e.getBoundingClientRect().width > 0)
          .filter((e) => (e.innerText || "").replace(/\s+/g, "") === txt);
        if (!els.length) continue;
        els.sort((a, b) => a.getBoundingClientRect().width - b.getBoundingClientRect().width);
        const r = els[0].getBoundingClientRect();
        btns[txt] = { x: r.x + r.width / 2, y: r.y + r.height / 2 };
      }
      const t = document.body.innerText.replace(/\s+/g, " ");
      const m = t.match(/题目框\s*(\d+)\s*答案\s*(\d+)\s*选项\s*(\d+)\s*解析\s*(\d+)\s*知识点\s*(\d+)/);
      return {
        cs, btns,
        counts: m ? { question: +m[1], answer: +m[2], choice: +m[3], analysis: +m[4], kp: +m[5] } : null,
        cur: (t.match(/当前题目[:：]\s*(\d+)/) || [])[1] || null,
      };
    });
  }

  function mapper(g, srcW, srcH) {
    const s = Math.min(g.w / srcW, g.h / srcH);
    const px = (g.w - srcW * s) / 2;
    const py = (g.h - srcH * s) / 2;
    return (b) => ({ x1: px + b[0] * s, y1: py + b[1] * s, x2: px + b[2] * s, y2: py + b[3] * s });
  }

  async function drag(g, box) {
    await page.mouse.move(g.ox + box.x1, g.oy + box.y1);
    await page.waitForTimeout(200);
    await page.mouse.down();
    await page.waitForTimeout(200);
    await page.mouse.move(g.ox + box.x2, g.oy + box.y2, { steps: 16 });
    await page.waitForTimeout(250);
    await page.mouse.up();
    await page.waitForTimeout(800);
  }

  async function clk(name) {
    const s = await st();
    const b = s.btns[name];
    if (!b) throw new Error("no button " + name);
    await page.mouse.click(b.x, b.y);
  }

  // 提交后平台的「当前题目」内部指针会滞后：显示的是下一题，画框却仍落到刚提交的那题上。
  // 点一次目录节点可强制同步（页码不变，已实测）。
  async function syncDir() {
    const ok = await page.evaluate((dirNode) => {
      const e = [...document.querySelectorAll(".el-tree-node__content")].find((x) => x.innerText.replace(/\s+/g, " ").trim() === dirNode);
      if (!e) return false;
      e.scrollIntoView({ block: "center" });
      return true;
    }, P.dirNode);
    if (!ok) throw new Error("目录节点未找到: " + P.dirNode);
    await page.waitForTimeout(800);
    const p = await page.evaluate((dirNode) => {
      const e = [...document.querySelectorAll(".el-tree-node__content")].find((x) => x.innerText.replace(/\s+/g, " ").trim() === dirNode);
      const r = e.getBoundingClientRect();
      return { x: Math.round(r.x + 40), y: Math.round(r.y + r.height / 2) };
    }, P.dirNode);
    await page.mouse.click(p.x, p.y);
    await page.waitForTimeout(3200);
  }
  if (conf.sync) {
    await syncDir();
    const pg = await page.evaluate(() => [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0).map((i) => i.value));
    // 只在调用方明确给了页码时才校验（pageRun 每题全量 restore，不走这条路径）
    if (conf.qPage && String(pg[0]) !== String(conf.qPage)) throw new Error("同步后题目页变了: " + JSON.stringify(pg.slice(0, 2)));
    if (conf.aPage && String(pg[1]) !== String(conf.aPage)) throw new Error("同步后答案页变了: " + JSON.stringify(pg.slice(0, 2)));
  }

  let s = await st();
  if (conf.expectCur && s.cur !== String(conf.expectCur))
    throw new Error(`当前题目 ${s.cur}，期望新建态 ${conf.expectCur} —— 页面已加载了别的题，中止`);
  if (s.counts && (s.counts.question || s.counts.answer || s.counts.choice))
    throw new Error("画框前已有残留框: " + JSON.stringify(s.counts));
  const gq = s.cs[0], ga = s.cs[1];
  const mq = mapper(gq, SRC_Q[0], SRC_Q[1]);
  const ma = mapper(ga, SRC_A[0], SRC_A[1]);

  await page.evaluate(() => {
    window.__cap2 = { ocr: null, commit: null };
    const OX = window.XMLHttpRequest;
    const op = OX.prototype.open, se = OX.prototype.send;
    OX.prototype.open = function (m, u) { this.__u = u; return op.apply(this, arguments); };
    OX.prototype.send = function (b) {
      this.addEventListener("load", () => {
        const u = String(this.__u || "");
        if (u.includes("batch-ocr-task")) window.__cap2.ocr = String(this.responseText).slice(0, 8000);
        if (u.includes("commit_unified_submit")) window.__cap2.commit = { req: typeof b === "string" ? b.slice(0, 8000) : null, body: String(this.responseText).slice(0, 2000) };
      });
      return se.apply(this, arguments);
    };
  });

  if (conf.q.length) {
    await clk("题目(Q)");
    await page.waitForTimeout(600);
    for (const b of conf.q) await drag(gq, mq(b));
  }
  if (conf.w.length) {
    await clk("选项(W)");
    await page.waitForTimeout(600);
    for (const b of conf.w) await drag(gq, mq(b));
  }
  if (conf.a.length) {
    await page.mouse.click(ga.ox + 350, ga.oy + 620);
    await page.waitForTimeout(500);
    await clk("答案(A)");
    await page.waitForTimeout(1600);
    for (const b of conf.a) await drag(ga, ma(b));
  }
  mark("boxes_done");

  s = await st();
  const want = { question: conf.q.length, choice: conf.w.length, answer: conf.a.length };
  const bad = Object.entries(want).filter(([k, v]) => s.counts[k] !== v);
  if (bad.length) throw new Error("counts bad: want " + JSON.stringify(want) + " got " + JSON.stringify(s.counts));

  const sel = await page.evaluate(() => {
    const s = [...document.querySelectorAll(".el-select")].find((e) => e.getBoundingClientRect().width > 0);
    const r = s.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  });
  await page.mouse.click(sel.x, sel.y);
  await page.waitForTimeout(800);
  await page.evaluate((name) => {
    const t = [...document.querySelectorAll(".el-select-dropdown__item")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .find((e) => e.innerText.trim() === name);
    if (!t) throw new Error("no option " + name);
    t.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    t.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    t.click();
  }, conf.type);
  await page.waitForTimeout(600);
  mark("type_done");

  await clk("一键识别");
  let ocr = null;
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(500);
    ocr = await page.evaluate(() => window.__cap2 && window.__cap2.ocr);
    if (ocr) break;
  }
  mark("ocr_done");

  let parsed = null;
  try { parsed = JSON.parse(ocr).data; } catch (e) { throw new Error("no ocr result"); }
  let orders = [...new Set((parsed.results || []).map((r) => r.question_order))];

  // 识别可能返回上一题的缓存结果（SOP 坑清单 #5）。order 对不上就重试一次，还不对就中止，绝不提交。
  if (conf.order && (orders.length !== 1 || String(orders[0]) !== String(conf.order))) {
    await page.evaluate(() => { window.__cap2.ocr = null; });
    await clk("一键识别");
    for (let i = 0; i < 40; i++) {
      await page.waitForTimeout(500);
      ocr = await page.evaluate(() => window.__cap2 && window.__cap2.ocr);
      if (ocr) break;
    }
    parsed = JSON.parse(ocr).data;
    orders = [...new Set((parsed.results || []).map((r) => r.question_order))];
  }
  if (conf.order && (orders.length !== 1 || String(orders[0]) !== String(conf.order)))
    throw new Error(`识别归属错误：期望 order ${conf.order}，实际 ${JSON.stringify(orders)} —— 框画到了别的题上，不要提交`);

  const lines = (parsed.results || []).map((r) => `${r.zone}: ${r.ocr_result}`);

  await clk("提交修改");
  let cm = null;
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(500);
    cm = await page.evaluate(() => window.__cap2 && window.__cap2.commit);
    if (cm) break;
  }
  mark("commit_done");

  s = await st();
  const cdata = cm ? JSON.parse(cm.body).data : null;
  // quiet: 整页跑的时候不打印 OCR 全文（单条输出 6k+ 字符，跑 14 题就是几万 token）
  if (!conf.quiet) console.log(JSON.stringify({
    n: conf.n,
    ocrLines: lines,
    ocrOrders: orders,
    processed: parsed.processed,
    commit: cdata,
    cur: s.cur,
    T,
  }, null, 1));
  if (conf.order && (!cdata || String(cdata.question_order) !== String(conf.order) || cdata.inserted !== true))
    throw new Error("提交结果异常（不是新建）：" + JSON.stringify(cdata));
  return { n: conf.n, order: orders[0], commit: cdata, cur: s.cur, T };
}
