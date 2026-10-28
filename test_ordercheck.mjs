// 纯函数测试：只 import ordercheck.mjs（无浏览器、无网络、无 ego），用 node 直接跑：
//   node test_ordercheck.mjs
// 证明三件事：选错课时会中止、畸形记录会被预检拦住、对账不符会停。
import assert from "node:assert/strict";
import {
  norm,
  pickLessonIndex,
  requireLessonIndex,
  assertSelectedLesson,
  groupByOrder,
  countBoxes,
  classifyOrderGroup,
  parseTime,
  recentRows,
  preflightReport,
  reconcileOne,
  auditSummary,
} from "./ordercheck.mjs";

let n = 0;
function ok(name, fn) {
  n++;
  fn();
  console.log(`ok ${n} ${name}`);
}

const L2 = "第2课时 二次根式的化简及加减运算";
const L3 = "第3课时 二次根式的混合运算";
const LABELS = [L2, L3];

// ---------- 1. 选课时 ----------

ok("pickLessonIndex 精确命中", () => {
  assert.deepEqual(pickLessonIndex(LABELS, L2), { index: 0, matches: 1 });
  assert.deepEqual(pickLessonIndex(LABELS, L3), { index: 1, matches: 1 });
  // 空白归一化
  assert.deepEqual(pickLessonIndex(["  " + L2 + "  "], L2), { index: 0, matches: 1 });
});

ok("选错课时（找不到）→ requireLessonIndex 抛错中止", () => {
  assert.throws(() => requireLessonIndex(LABELS, "第1课时 不存在"), /找不到课时/);
});

ok("同名课时不唯一 → requireLessonIndex 抛错中止", () => {
  assert.throws(() => requireLessonIndex([L2, L2], L2), /同名节点/);
});

ok("点完回读文本 != lesson → assertSelectedLesson 抛错中止", () => {
  assert.equal(assertSelectedLesson(L2, L2), true);
  assert.throws(() => assertSelectedLesson(L3, L2), /课时选中自检失败/);
});

// ---------- 2. 残局预检（真实事故的 11 条记录形状） ----------

const OLD = "2026-10-28T09:00:00Z";
function row(order, type, pg, dir, at = OLD) {
  return { order_in_level: order, type, page_index: pg, directory_id: dir, created_at: at };
}

// order 95：畸形记录（2 个题目框、0 个答案框，page 35 和 36 各一个框）。
const malformed = [
  row(95, "question", 35, "d3"),
  row(95, "question", 36, "d3"),
];

// p34 的 10 题（n1..n10），每题的框数。事故里全部错落进 d3（正确应是 d2）。
const p34 = [
  { q: 1, w: 0, a: 2 }, // n1 填空
  { q: 1, w: 4, a: 1 }, // n2 选择
  { q: 1, w: 0, a: 1 }, // n3 问答
  { q: 1, w: 4, a: 1 }, // n4 选择
  { q: 1, w: 4, a: 1 }, // n5 选择
  { q: 1, w: 0, a: 1 }, // n6 问答
  { q: 1, w: 4, a: 1 }, // n7 选择
  { q: 1, w: 4, a: 1 }, // n8 选择
  { q: 1, w: 0, a: 1 }, // n9 填空
  { q: 1, w: 0, a: 1 }, // n10 问答
];

function p34Rows(dir = "d3") {
  const rows = [];
  p34.forEach((spec, i) => {
    const order = 96 + i;
    for (let k = 0; k < spec.q; k++) rows.push(row(order, "question", 34, dir));
    for (let k = 0; k < spec.w; k++) rows.push(row(order, "choice", 34, dir));
    for (let k = 0; k < spec.a; k++) rows.push(row(order, "answer", 175, dir));
  });
  return rows;
}

ok("畸形记录 order 95 被预检拦住（跨页题目框 + 0 答案框）", () => {
  const probs = classifyOrderGroup(95, malformed);
  assert.ok(probs.some((p) => p.includes("跨页")), "应有跨页重复: " + JSON.stringify(probs));
  assert.ok(probs.some((p) => p.includes("0 个答案框")), "应有 0 答案框: " + JSON.stringify(probs));
});

ok("正常记录 96–105 不误报（同页多框合法）", () => {
  for (const o of [96, 97, 98, 99, 100, 101, 102, 103, 104, 105]) {
    const rows = p34Rows().filter((r) => r.order_in_level === o);
    assert.deepEqual(classifyOrderGroup(o, rows), [], `order ${o} 不该被报畸形`);
  }
});

ok("preflightReport 聚合出畸形记录 + maxOrder=105", () => {
  const rep = preflightReport([...malformed, ...p34Rows()], { now: null });
  assert.equal(rep.maxOrder, 105);
  assert.ok(rep.anomalies.some((p) => p.includes("order 95")), "应包含 order 95 的异常");
});

ok("preflightReport 拦近期新建记录", () => {
  const now = new Date("2026-10-28T12:00:00Z").getTime();
  const fresh = row(106, "question", 34, "d2", "2026-10-28T11:59:30Z");
  const rep = preflightReport([fresh], { now });
  assert.ok(rep.anomalies.some((p) => p.includes("近 10 分钟")), "应报近期新记录");
  // 老记录不报
  const repOld = preflightReport([row(96, "question", 34, "d2", OLD)], { now });
  assert.ok(!repOld.anomalies.some((p) => p.includes("近 10 分钟")));
});

ok("recentRows / parseTime 解析", () => {
  const now = new Date("2026-10-28T12:00:00Z").getTime();
  assert.equal(recentRows([row(1, "question", 34, "d2", "2026-10-28T11:50:00Z")], now, 10 * 60 * 1000).length, 1);
  assert.equal(recentRows([row(1, "question", 34, "d2", "2026-10-28T11:40:00Z")], now, 10 * 60 * 1000).length, 0);
  assert.equal(parseTime(1600000000), 1600000000000); // epoch 秒
  assert.equal(parseTime("2026-10-28T09:00:00Z"), new Date("2026-10-28T09:00:00Z").getTime());
});

// ---------- 3. 提交后对账 ----------

function orderRows(order, spec, { dir = "d2", qPage = 34, aPage = 175 } = {}) {
  const rows = [];
  for (let k = 0; k < spec.q; k++) rows.push(row(order, "question", qPage, dir));
  for (let k = 0; k < spec.w; k++) rows.push(row(order, "choice", qPage, dir));
  for (let k = 0; k < spec.a; k++) rows.push(row(order, "answer", aPage, dir));
  return rows;
}
const n1 = { q: 1, w: 0, a: 2 };

ok("对账通过：order/课时/页/框数全部一致", () => {
  const probs = reconcileOne(96, orderRows(96, n1), { directoryId: "d2", qPage: 34, aPage: 175, q: 1, w: 0, a: 2 });
  assert.deepEqual(probs, []);
});

ok("对账不符：落进错误课时（d3 而非 d2）→ 停", () => {
  const probs = reconcileOne(96, orderRows(96, n1, { dir: "d3" }), { directoryId: "d2", qPage: 34, aPage: 175, q: 1, w: 0, a: 2 });
  assert.ok(probs.some((p) => p.includes("directory_id 期望 d2 实际 d3")), JSON.stringify(probs));
});

ok("对账不符：框数不一致 → 停", () => {
  const probs = reconcileOne(96, orderRows(96, n1).slice(0, 2), { directoryId: "d2", qPage: 34, aPage: 175, q: 1, w: 0, a: 2 });
  assert.ok(probs.some((p) => p.includes("答案框 期望 2 实际 1")), JSON.stringify(probs));
});

ok("对账不符：page_index 不一致 → 停", () => {
  const probs = reconcileOne(96, orderRows(96, n1, { aPage: 174 }), { directoryId: "d2", qPage: 34, aPage: 175, q: 1, w: 0, a: 2 });
  assert.ok(probs.some((p) => p.includes("page_index 期望 175 实际 174")), JSON.stringify(probs));
});

ok("对账不符：缺 directory_id → 停（没证据不放行）", () => {
  const probs = reconcileOne(96, orderRows(96, n1), { directoryId: null, qPage: 34, aPage: 175, q: 1, w: 0, a: 2 });
  assert.ok(probs.some((p) => p.includes("directory_id")), JSON.stringify(probs));
});

// ---------- 4. 审计汇总（audit_orders.mjs 的纯部分） ----------

ok("auditSummary 分组正确", () => {
  const s = auditSummary([...malformed, ...p34Rows()], {});
  assert.equal(s.total, 2 + p34Rows().length);
  assert.equal(s.min, 95);
  assert.equal(s.max, 105);
  const o95 = s.lines.find((l) => l.order === 95);
  assert.deepEqual([o95.q, o95.w, o95.a], [2, 0, 0]);
});

console.log(`\nALL ${n} PASS`);
