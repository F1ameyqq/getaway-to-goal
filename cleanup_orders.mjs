// cleanup_orders.mjs —— 按题号区间删除题目（order_in_level）。
//
// 默认 dry-run：只读服务端标注数据，逐条打印区间内的题号，一个字节都不写。
// 只有设置 CLEAN_APPLY=1 才真删，且删除顺序是从最大题号往小删
// （删最大号不会让剩余题号重排；删中间的会，因为平台会“后续题目编号自动调整”）。
//
// 用法：
//   .\run_ego.ps1 -Js .\cleanup_orders.mjs -TimeoutSec 300
// 参数经 run_ego.ps1 的 $prelude 传 env：
//   CLEAN_LO / CLEAN_HI   题号区间，默认 95 / 105
//   CLEAN_APPLY=1         真删；否则只 dry-run
//
// 交互模型（2026-10-28 实测）：
//   目录编辑 → 题目节点 .tree-actions button[title="删除题目"] → 弹 ElMessageBox 确认
//   （取消/确定）→ 点「确定」只是**暂存**：节点从树里消失、应用变更变可用，服务端还没变
//   → 必须点「应用变更」才真正提交到服务端。「取消」退出编辑模式并丢弃暂存改动。
import { P } from "./config.mjs";
import { groupByOrder, countBoxes, preflightReport } from "./ordercheck.mjs";

const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, timeout, interval = 200) {
  const end = Date.now() + timeout;
  for (;;) {
    let v = null;
    try { v = await fn(); } catch (e) { v = null; }
    if (v) return v;
    if (Date.now() >= end) return null;
    await delay(interval);
  }
}

const LO = process.env.CLEAN_LO ? Number(process.env.CLEAN_LO) : 95;
const HI = process.env.CLEAN_HI ? Number(process.env.CLEAN_HI) : 105;
const APPLY = process.env.CLEAN_APPLY === "1";

const task = await taskSpace(P.taskSpace);
const page = task.page(P.page);

const posOf = (txt) =>
  page.evaluate((t) => {
    const e = [...document.querySelectorAll("button,span,div,a")]
      .filter((x) => x.getBoundingClientRect().width > 0)
      .find((x) => (x.innerText || "").replace(/\s+/g, " ").trim() === t);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  }, txt);

async function fetchRows() {
  const tok = await page.evaluate(() => JSON.parse(localStorage.getItem("user")).access_token);
  const r = await page.fetch(`/qieti/api/annotate_pic/get_manual_annotations_unified/${P.fileId}`, {
    headers: { authorization: "Bearer " + tok },
    timeout: 30000,
  });
  const j = JSON.parse(r.body);
  return j.data || [];
}

async function orderSet(rows) {
  return new Set((await rows).map((a) => String(a.order_in_level)));
}

function targetOrders(rows) {
  const by = groupByOrder(rows);
  return Object.keys(by).map(Number).filter((o) => o >= LO && o <= HI).sort((a, b) => a - b);
}

function printDryRun(rows, targets) {
  const by = groupByOrder(rows);
  console.log(`TARGETS lo=${LO} hi=${HI} count=${targets.length} orders=[${targets.join(",")}]`);
  for (const o of targets) {
    const list = by[String(o)] || [];
    const c = countBoxes(list);
    const pages = [...new Set(list.map((r) => r.page_index))];
    const dirs = [...new Set(list.map((r) => r.directory_id).filter((d) => d !== null && d !== undefined && String(d) !== ""))];
    const created = [...new Set(list.map((r) => String(r.created_at || "")))];
    console.log(`ORDER ${o} q=${c.question} w=${c.choice} a=${c.answer} other=${c.other} pages=[${pages.join(",")}] dirs=[${dirs.join(",")}] created=[${created.join("|")}]`);
    for (const r of list) {
      console.log(`  REC order=${r.order_in_level} type=${r.type} page=${r.page_index} dir=${r.directory_id} created=${r.created_at}`);
    }
  }
  console.log(`将要删除 ${targets.length} 条`);
}

// 确保在平台 origin（token 可读）
async function ensurePlatform() {
  let on = false;
  try { on = await page.evaluate(() => /^https?:/.test(location.href) && location.origin.includes("lingshubao")); } catch (e) { on = false; }
  if (!on) {
    await page.goto(P.url);
    await until(() => page.evaluate(() => /lingshubao/.test(location.href)), 30000, 250);
  }
  const tokOk = await until(() => page.evaluate(() => {
    try { const u = JSON.parse(localStorage.getItem("user")); return !!(u && u.access_token); } catch (e) { return false; }
  }), 15000, 250);
  if (!tokOk) throw new Error("读不到 localStorage token（未登录 / 不在平台 origin）");
}

// 选书 + 等目录树（APPLY 前用，保证干净、无遗留暂存改动）
async function ensureTree() {
  const origin0 = await page.evaluate(() => performance.timeOrigin).catch(() => null);
  let bookPos = null;
  if (origin0 !== null) {
    try { await Promise.race([page.evaluate(() => location.reload()).catch(() => {}), delay(3000)]); } catch (e) { /* 导航中 context destroyed 属正常 */ }
    bookPos = await until(async () => {
      const o = await page.evaluate(() => performance.timeOrigin).catch(() => null);
      if (o === null || o === origin0) return null;
      return await posOf("选择书籍");
    }, 5000, 100);
  }
  if (!bookPos) {
    try { await page.reload(); } catch (e) { if (!/timed out/i.test(String(e))) throw e; }
    bookPos = await until(() => posOf("选择书籍"), 30000, 250);
  }
  if (!bookPos) throw new Error("not found: 选择书籍");
  await page.mouse.click(bookPos.x, bookPos.y);
  const pickPos = await until(
    () => page.evaluate((fid) => {
      const row = [...document.querySelectorAll(".el-table__row")].find((e) => e.innerText.includes(fid));
      if (!row) return null;
      const b = [...row.querySelectorAll("button")].find((e) => (e.innerText || "").trim() === "选择");
      if (!b) return null;
      const r = b.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    }, P.fileId),
    30000,
    200
  );
  if (!pickPos) throw new Error("no 选择 button for fileId=" + P.fileId);
  await page.mouse.click(pickPos.x, pickPos.y);
  const treeOk = await until(() => page.evaluate(() => document.querySelectorAll(".el-tree-node").length > 0), 30000, 200);
  if (!treeOk) throw new Error("目录树未出现");
  await delay(800);
}

// 是否已在目录编辑模式
async function inEditMode() {
  return await page.evaluate(() =>
    [...document.querySelectorAll('button[title="删除题目"]')].some((e) => e.getBoundingClientRect().width > 0)
  );
}

async function ensureEditMode() {
  if (await inEditMode()) return;
  await page.evaluate(() => {
    const els = [...document.querySelectorAll("button,.el-button,a,span,div")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .filter((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "目录编辑");
    if (!els.length) throw new Error("找不到「目录编辑」按钮");
    els[0].click();
  });
  const ok = await until(() => inEditMode(), 8000, 200);
  if (!ok) throw new Error("进入目录编辑模式失败");
}

// 找题号节点（编辑模式下标签就是纯数字）
async function findNode(order) {
  return await page.evaluate((o) => {
    const nodes = [...document.querySelectorAll(".el-tree-node")].filter((n) => {
      const c = n.querySelector(":scope > .el-tree-node__content");
      return c && c.querySelector(".question-node");
    });
    return nodes.some((n) => {
      const lbl = n.querySelector(".tree-node-label-rich.question-node");
      return lbl && (lbl.textContent || "").replace(/\s+/g, " ").trim() === String(o);
    });
  }, order);
}

async function clickDelete(order) {
  await page.evaluate((o) => {
    const nodes = [...document.querySelectorAll(".el-tree-node")].filter((n) => {
      const c = n.querySelector(":scope > .el-tree-node__content");
      return c && c.querySelector(".question-node");
    });
    const target = nodes.find((n) => {
      const lbl = n.querySelector(".tree-node-label-rich.question-node");
      return lbl && (lbl.textContent || "").replace(/\s+/g, " ").trim() === String(o);
    });
    if (!target) throw new Error("找不到题号 " + o + " 的节点");
    const btn = target.querySelector('.tree-actions button[title="删除题目"]');
    if (!btn) throw new Error("题号 " + o + " 上没有删除按钮");
    btn.click();
  }, order);
}

// 失败诊断：打印当前 DOM 的编辑模式状态（删除按钮数 / 确认框 / 应用变更 / 题目节点数）
async function dumpEditState(where) {
  const s = await page.evaluate(() => {
    const delBtns = [...document.querySelectorAll('button[title="删除题目"]')].filter((e) => e.getBoundingClientRect().width > 0);
    const box = document.querySelector(".el-message-box");
    let boxInfo = null;
    if (box) {
      boxInfo = {
        btns: [...box.querySelectorAll(".el-message-box__btns .el-button")].map((b) => (b.innerText || "").replace(/\s+/g, " ").trim()),
        headerBtn: !!box.querySelector(".el-message-box__headerbtn"),
      };
    }
    const apply = [...document.querySelectorAll("button,.el-button,a,span,div")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .find((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "应用变更");
    const nodes = [...document.querySelectorAll(".el-tree-node")].filter((n) => {
      const c = n.querySelector(":scope > .el-tree-node__content");
      return c && c.querySelector(".question-node");
    });
    const labels = nodes.map((n) => (n.querySelector(".tree-node-label-rich.question-node") || {}).textContent || "").map((x) => x.replace(/\s+/g, " ").trim());
    return {
      delBtnCount: delBtns.length,
      msgBox: boxInfo,
      apply: apply ? { present: true, disabled: apply.disabled } : { present: false },
      qCount: nodes.length,
      lastLabels: labels.slice(-6),
    };
  });
  console.log(`EDIT_STATE(${where}) ${JSON.stringify(s)}`);
}

async function clickConfirmOk() {
  const ok = await until(() => page.evaluate(() => {
    const box = document.querySelector(".el-message-box");
    if (!box) return null;
    const b = [...box.querySelectorAll(".el-message-box__btns .el-button")].find((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "确定");
    return b ? true : null;
  }), 15000, 200);
  if (!ok) {
    await dumpEditState("confirm-timeout");
    throw new Error("删除确认框未出现（15s）");
  }
  await page.evaluate(() => {
    const box = document.querySelector(".el-message-box");
    const b = [...box.querySelectorAll(".el-message-box__btns .el-button")].find((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "确定");
    b.click();
  });
}

async function clickApply() {
  const ok = await until(() => page.evaluate(() => {
    const apply = [...document.querySelectorAll("button,.el-button,a,span,div")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .find((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "应用变更");
    if (!apply) return null;
    return apply.disabled === false ? true : null;
  }), 15000, 200);
  if (!ok) {
    await dumpEditState("apply-timeout");
    throw new Error("「应用变更」按钮未变为可用（15s）");
  }
  await page.evaluate(() => {
    const apply = [...document.querySelectorAll("button,.el-button,a,span,div")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .find((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "应用变更");
    apply.click();
  });
}

// 失败兜底：关掉可能残留的确认框，再点「取消」退出编辑模式（丢弃暂存改动）
async function discardEditMode() {
  await page.evaluate(() => {
    const x = document.querySelector(".el-message-box__headerbtn");
    if (x) x.click();
  });
  await delay(300);
  await page.evaluate(() => {
    const cancel = [...document.querySelectorAll("button,.el-button,a,span,div")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .find((e) => (e.innerText || "").replace(/\s+/g, " ").trim() === "取消");
    if (cancel) cancel.click();
  });
}

async function main() {
  await ensurePlatform();
  const rows0 = await fetchRows();
  const targets = targetOrders(rows0);

  if (!APPLY) {
    printDryRun(rows0, targets);
    return;
  }

  // —— 真删（CLEAN_APPLY=1）——
  await ensureTree(); // 干净起点，清掉任何历史暂存
  const targetsDesc = targets.slice().sort((a, b) => b - a);
  const deleted = [];
  console.log(`APPLY start: 将删除 [${targetsDesc.join(",")}]（从大到小）`);

  for (const o of targetsDesc) {
    try {
      const beforeSet = await orderSet(fetchRows());
      await ensureEditMode();
      const nodeOk = await until(() => findNode(o), 5000, 200);
      if (!nodeOk) throw new Error(`题号 ${o} 在树里找不到（可能已不在编辑模式或树未刷新）`);
      await clickDelete(o);
      await clickConfirmOk();
      await clickApply();
      // 等服务端该号消失
      const gone = await until(async () => {
        const s = await orderSet(fetchRows());
        return s.has(String(o)) ? null : true;
      }, 15000, 500);
      if (!gone) throw new Error(`删除 ${o} 后 15s 服务端仍存在该号`);
      const afterSet = await orderSet(fetchRows());
      if (afterSet.has(String(o))) throw new Error(`删除 ${o} 后仍存在该号`);
      // 校验：除了刚删的 o，其余号一个都不能少（删最大号不会重排，所以应是 beforeSet - {o}）
      const expected = new Set(beforeSet);
      expected.delete(String(o));
      for (const k of expected) {
        if (!afterSet.has(k)) throw new Error(`删除 ${o} 时误伤了 ${k}`);
      }
      deleted.push(o);
      console.log(`DELETED ${o}`);
    } catch (e) {
      console.log(`FAILED at ${o}: ${e.message}`);
      console.log(`已删 [${deleted.join(",") || "-"}]；剩余目标 [${targetsDesc.filter((x) => !deleted.includes(x)).join(",") || "-"}]`);
      await discardEditMode();
      return;
    }
  }

  const finalRows = await fetchRows();
  const pre = preflightReport(finalRows, { now: Date.now() });
  console.log(`FINAL orders=${pre.orderCount} max=${pre.maxOrder ?? "-"} holes=${pre.holes.length}`);
  if (pre.holes.length) console.log(`HOLES ${JSON.stringify(pre.holes.slice(-30))}`);
  for (const a of pre.anomalies) console.log(`ANOMALY ${a}`);
  console.log(`已删除 [${deleted.join(",") || "-"}]`);
}

await main();
