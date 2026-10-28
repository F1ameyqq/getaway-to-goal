// ordercheck.mjs —— 纯函数集合：选课时、异常记录判定、提交后对账、审计汇总。
// 不 import 任何会碰浏览器 / 网络 / ego 的东西，只做纯计算，可离线用 node 直接测试
// （见 test_ordercheck.mjs）。供 restorefn.mjs（选课时）、pageRun.mjs（预检 + 对账）、
// audit_orders.mjs（审计）共用。
//
// 这里所有判断都是「可证伪的硬判断」：给定同样输入结论确定，不依赖“没报错”。

// 与左侧树显示文本一致的归一化：折叠所有空白、去首尾空格。
export const norm = (s) => (s === null || s === undefined ? "" : String(s)).replace(/\s+/g, " ").trim();

// 从左侧树叶子目录（课时）里按名字精确挑一个。
// labels: string[]，顺序与 DOM 中叶子目录一致；lesson: 传入的课时名（须与树里文本完全一致）。
// 返回 { index, matches }：matches=0 找不到；matches>1 同名不唯一；matches=1 命中。
export function pickLessonIndex(labels, lesson) {
  const want = norm(lesson);
  const hit = [];
  (labels || []).forEach((label, i) => {
    if (norm(label) === want) hit.push(i);
  });
  return { index: hit.length === 1 ? hit[0] : -1, matches: hit.length };
}

// 选课时的硬判断：找不到或同名不唯一都抛错（调用方靠抛错中止，绝不猜）。
export function requireLessonIndex(labels, lesson) {
  const pick = pickLessonIndex(labels, lesson);
  if (pick.matches === 0)
    throw new Error(`找不到课时「${lesson}」——左侧树里的课时: ${(labels || []).join(" | ") || "（空）"}`);
  if (pick.matches > 1)
    throw new Error(`课时「${lesson}」在左侧树里有 ${pick.matches} 个同名节点，落点不唯一——中止`);
  return pick.index;
}

// 点完课时后的回读硬判断：实际选中的节点文本必须 === 传入 lesson。
export function assertSelectedLesson(actualLabel, lesson) {
  if (norm(actualLabel) !== norm(lesson))
    throw new Error(`课时选中自检失败：期望「${lesson}」，实际选中「${actualLabel}」`);
  return true;
}

// 把标注行按 order_in_level 分组。
export function groupByOrder(rows) {
  const by = {};
  for (const r of rows || []) {
    const k = String(r.order_in_level);
    (by[k] = by[k] || []).push(r);
  }
  return by;
}

// 数一个 order 下各类框的数量。
export function countBoxes(rows) {
  const c = { question: 0, choice: 0, answer: 0, other: 0 };
  for (const r of rows || []) {
    const t = String(r.type || "");
    if (t === "question") c.question++;
    else if (t === "choice") c.choice++;
    else if (t === "answer") c.answer++;
    else c.other++;
  }
  return c;
}

// 判一条 order 的标注集合是否畸形。返回异常描述数组（空 = 正常）。
//   同号重复：题目框散在多个 page_index（跨页重复），或散在多个 directory_id（同号跨课时）。
//     注意：同一页上的多个题目框是合法的（跨栏题），不报。
//   0 答案框：有题目框但没有任何答案框。
export function classifyOrderGroup(order, rows) {
  const probs = [];
  const list = rows || [];
  const qrows = list.filter((r) => String(r.type) === "question");
  const pages = [...new Set(qrows.map((r) => r.page_index))];
  if (qrows.length && pages.length > 1)
    probs.push(`同号重复：order ${order} 的题目框跨页 (page_index ${pages.join(",")})`);
  const dirs = [...new Set(list.map((r) => r.directory_id).filter((d) => d !== null && d !== undefined && String(d) !== ""))];
  if (dirs.length > 1)
    probs.push(`同号跨课时：order ${order} 同时归属多个 directory_id (${dirs.join(",")})`);
  const c = countBoxes(list);
  if (c.question > 0 && c.answer === 0)
    probs.push(`0 个答案框：order ${order} 有 ${c.question} 个题目框、0 个答案框`);
  return probs;
}

// 时间解析：容忍 epoch 秒/毫秒、ISO、'YYYY-MM-DD HH:mm:ss'。返回毫秒或 null。
export function parseTime(v) {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return v < 1e12 ? v * 1000 : v;
  const s = String(v).trim();
  if (/^\d+(\.\d+)?$/.test(s)) {
    const n = Number(s);
    return n < 1e12 ? n * 1000 : n;
  }
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

// 最近 recentMs 内新建的记录。预检在第一次提交之前跑，所以这些都不是“这次建的”。
export function recentRows(rows, now, recentMs = 10 * 60 * 1000) {
  if (now === null || now === undefined) return [];
  const out = [];
  for (const r of rows || []) {
    const t = parseTime(r.created_at);
    if (t !== null && now - t >= 0 && now - t <= recentMs) out.push(r);
  }
  return out;
}

// 残局预检报告：orderCount / maxOrder / 空号 / 畸形记录 / 近期新记录。
// 预检分两类，边界是「这次追加能不能安全做」：
//   blocking —— 会让"接着追加"本身不安全：近期有别人写的记录（并发）、题号空洞。
//   warnings —— 其他课时的数据质量问题（如 0 个答案框）。它们不影响我们追加，
//               只打出来备查；以前把这类当阻断，结果工具一碰到别人早先的历史数据就停死。
// anomalies 是两类并集（老调用方的兼容字段）。
export function preflightReport(rows, { now = null, recentMs = 10 * 60 * 1000 } = {}) {
  const byOrder = groupByOrder(rows);
  const orders = Object.keys(byOrder).map(Number).sort((a, b) => a - b);
  const maxOrder = orders.length ? orders[orders.length - 1] : null;
  const warnings = [];
  for (const o of orders) for (const p of classifyOrderGroup(o, byOrder[o])) warnings.push(p);
  const blocking = [];
  const rec = recentRows(rows, now, recentMs);
  if (rec.length) {
    const sample = rec.slice(0, 6).map((r) => `order ${r.order_in_level}/${r.type}@${r.created_at}`).join(", ");
    blocking.push(`近 ${Math.round(recentMs / 60000)} 分钟内有 ${rec.length} 条新记录(非本次运行): ${sample}`);
  }
  const holes = [];
  if (orders.length) {
    for (let k = orders[0]; k < orders[orders.length - 1]; k++) if (!byOrder[k]) holes.push(k);
  }
  const anomalies = [...blocking, ...warnings];
  return { orderCount: orders.length, maxOrder, holes, blocking, warnings, anomalies, byOrder };
}

// 提交后对账：一条 order 的标注行是否与预期一致。返回问题描述数组（空 = 通过）。
// expected: { directoryId, qPage, aPage, q, w, a }
//   directoryId 必须给（null 表示没读到课时 id），否则直接判失败——没有证据不许放行。
//   page_index 按框类型分页：question/choice 落在题目页(qPage)，answer 落在答案页(aPage)。
export function reconcileOne(order, rows, expected) {
  const problems = [];
  const list = rows || [];
  if (!list.length) {
    problems.push(`order ${order} 在库里查无记录`);
    return problems;
  }
  for (const r of list) {
    if (String(r.order_in_level) !== String(order))
      problems.push(`order_in_level 期望 ${order} 实际 ${r.order_in_level}`);
  }
  if (expected.directoryId === null || expected.directoryId === undefined) {
    problems.push(`没读到选中课时的 directory_id，无法证明归属`);
  } else {
    for (const r of list) {
      if (String(r.directory_id).trim() !== String(expected.directoryId).trim())
        problems.push(`归属课时 directory_id 期望 ${expected.directoryId} 实际 ${r.directory_id}`);
    }
  }
  const c = countBoxes(list);
  if (c.question !== expected.q) problems.push(`题目框 期望 ${expected.q} 实际 ${c.question}`);
  if (c.choice !== expected.w) problems.push(`选项框 期望 ${expected.w} 实际 ${c.choice}`);
  if (c.answer !== expected.a) problems.push(`答案框 期望 ${expected.a} 实际 ${c.answer}`);
  for (const r of list) {
    const want = String(r.type) === "answer" ? expected.aPage : expected.qPage;
    if (String(r.page_index).trim() !== String(want).trim())
      problems.push(`page_index 期望 ${want} 实际 ${r.page_index} (${r.type})`);
  }
  return problems;
}

// 审计汇总：按题号给各类框数，附总数 / 空号区间（供 audit_orders.mjs 打印）。
export function auditSummary(rows, { lo = null, hi = null } = {}) {
  const by = groupByOrder(rows);
  const orders = Object.keys(by).map(Number).sort((a, b) => a - b);
  const lines = [];
  for (const o of orders) {
    if (lo !== null && o < lo) continue;
    if (hi !== null && o > hi) continue;
    const c = countBoxes(by[o]);
    lines.push({ order: o, q: c.question, w: c.choice, a: c.answer, other: c.other });
  }
  return {
    total: (rows || []).length,
    orders: orders.length,
    min: orders.length ? orders[0] : null,
    max: orders.length ? orders[orders.length - 1] : null,
    lines,
  };
}
