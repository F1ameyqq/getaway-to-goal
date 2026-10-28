// dirtree.mjs —— 课时名 → directory_id 的唯一权威来源。
//
// 平台自己在选书后调 /qieti/api/annotate_ocr/directory/get?file_id=…，返回整棵树：
//   { code:0, data:{ directory_data:[ {id,label,children:[…]} ] } }
// 题目节点带 isQuestion:true 和 order_in_level。
//
// 以前靠读 Vue 组件实例（__vue__ / __vueParentComponent）反推 id，框架一升级就读不到，
// 于是整条链路"没证据就中止"。改成读这个接口：id 和题数都由服务端给，稳定且可复核。
import { norm } from "./ordercheck.mjs";

// 扁平化：只收目录节点（isQuestion 的不收）。
export function flattenDirs(nodes, out = [], path = []) {
  for (const n of nodes || []) {
    if (!n || n.isQuestion) continue;
    const label = norm(n.label);
    const p = [...path, label];
    out.push({ id: n.id, label, path: p.join(" / "), kids: Array.isArray(n.children) ? n.children : [] });
    if (Array.isArray(n.children) && n.children.length) flattenDirs(n.children, out, p);
  }
  return out;
}

// 课时 = 叶子目录：没有子节点，或子节点全是题目。
export function lessonDirs(nodes) {
  return flattenDirs(nodes).filter((d) => d.kids.every((k) => k && k.isQuestion));
}

export function questionCount(d) {
  return d.kids.filter((k) => k && k.isQuestion).length;
}

// 按名字精确匹配课时。0 条 → 报可读的候选；>1 条 → 报歧义。绝不"差不多就行"。
export function requireLesson(nodes, label) {
  const want = norm(label);
  const all = lessonDirs(nodes);
  const hits = all.filter((d) => d.label === want);
  if (hits.length === 1) return { ...hits[0], qCount: questionCount(hits[0]) };
  if (hits.length === 0) {
    const near = all.filter((d) => d.label.includes(want) || want.includes(d.label)).slice(0, 8);
    const hint = near.length ? "；相近的有: " + near.map((d) => d.label).join(" | ") : "";
    throw new Error(`目录树里找不到课时「${want}」${hint}`);
  }
  throw new Error(`课时名有 ${hits.length} 个匹配「${want}」，无法确定落点`);
}

// 解析接口返回体（字符串或对象都吃）。
export function parseTree(body) {
  const j = typeof body === "string" ? JSON.parse(body) : body;
  if (!j || j.code !== 0) throw new Error("目录接口返回异常: " + (j && j.message));
  const data = j.data || {};
  const nodes = data.directory_data || [];
  if (!Array.isArray(nodes)) throw new Error("目录接口没有 directory_data 数组");
  return nodes;
}
