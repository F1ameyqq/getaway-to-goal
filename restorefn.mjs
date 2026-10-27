// 全量重置：导航到平台 → reload → 选书 → 选目录 → 翻到 题目页/答案页
// 返回 { cur, counts, pages }，cur 即平台给的「当前题目」号
// 页码默认 28/174（p28 那批的老约定），录别的页时显式传 restore({ qPage: 33, aPage: 175 })
import { P } from "./config.mjs";

export async function restore({ qPage = 28, aPage = 174 } = {}) {
  const task = await taskSpace(P.taskSpace);
  const page = task.page(P.page);

  // 新开的 task space 会停在 chrome://new-tab-page，reload 救不回来，必须先导航。
  // 这是 2026-10-27 第一次真实提交时踩到的：restore 一直报「not found: 选择书籍」。
  let url0 = "";
  try { url0 = await page.evaluate(() => location.href); } catch (e) { url0 = ""; }
  if (!/^https?:/.test(url0)) {
    await page.goto(P.url);
    await page.waitForTimeout(8000);
  }

  // page.reload() 默认只等 15s，平台偶尔要 20–40s 才 complete。
  // 超时不代表失败（reload 已经发起了），所以吞掉超时，改为轮询 readyState。
  try {
    await page.reload();
  } catch (e) {
    if (!/timed out/i.test(String(e))) throw e;
  }
  await page.waitForTimeout(2000);
  for (let i = 0; i < 45; i++) {
    let rs = "";
    try { rs = await page.evaluate(() => document.readyState); } catch (e) { rs = ""; }
    if (rs === "complete") break;
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(3000);

  async function clickText(txt) {
    const p = await page.evaluate((t) => {
      const e = [...document.querySelectorAll("button,span,div")].filter((x) => x.getBoundingClientRect().width > 0).find((x) => x.innerText.trim() === t);
      if (!e) return null;
      const r = e.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    }, txt);
    if (!p) throw new Error("not found: " + txt);
    await page.mouse.click(p.x, p.y);
  }

  await clickText("选择书籍");
  await page.waitForTimeout(2500);
  const btn = await page.evaluate((fid) => {
    const row = [...document.querySelectorAll(".el-table__row")].find((e) => e.innerText.includes(fid));
    if (!row) return null;
    const b = [...row.querySelectorAll("button")].find((e) => e.innerText.trim() === "选择");
    if (!b) return null;
    const r = b.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  }, P.fileId);
  if (!btn) throw new Error("no 选择 button for fileId=" + P.fileId);
  await page.mouse.click(btn.x, btn.y);
  await page.waitForTimeout(6000);

  const hit = await page.evaluate((node) => {
    const e = [...document.querySelectorAll(".el-tree-node__content")].find((x) => x.innerText.replace(/\s+/g, " ").trim() === node);
    if (!e) return null;
    e.scrollIntoView({ block: "center" });
    return true;
  }, P.dirNode);
  if (!hit) throw new Error("目录节点未找到: " + P.dirNode);
  await page.waitForTimeout(900);
  const node = await page.evaluate((dirNode) => {
    const e = [...document.querySelectorAll(".el-tree-node__content")].find((x) => x.innerText.replace(/\s+/g, " ").trim() === dirNode);
    const r = e.getBoundingClientRect();
    return { x: Math.round(r.x + 40), y: Math.round(r.y + r.height / 2) };
  }, P.dirNode);
  await page.mouse.click(node.x, node.y);
  await page.waitForTimeout(3000);

  const pageInputs = await page.evaluate(() =>
    [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0).map((i) => ({ x: Math.round(i.getBoundingClientRect().x + i.getBoundingClientRect().width / 2), y: Math.round(i.getBoundingClientRect().y + i.getBoundingClientRect().height / 2) }))
  );
  async function gotoPage(x, y, n) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(400);
    await page.keyboard.down("Control");
    await page.keyboard.press("a");
    await page.keyboard.up("Control");
    await page.waitForTimeout(200);
    await page.keyboard.type(String(n), { delay: 90 });
    await page.keyboard.press("Enter");
    await page.waitForTimeout(4000);
  }
  await gotoPage(pageInputs[0].x, pageInputs[0].y, qPage);
  await gotoPage(pageInputs[1].x, pageInputs[1].y, aPage);

  const st = await page.evaluate(() => {
    const t = document.body.innerText.replace(/\s+/g, " ");
    return {
      counts: (t.match(/题目框\s*(\d+)\s答案\s*(\d+)\s选项\s*(\d+)/) || []).slice(1),
      cur: (t.match(/当前题目[:：]\s*(\d+)/) || [])[1],
      pages: [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0).map((i) => i.value).slice(0, 2),
    };
  });
  if (st.pages[0] !== String(qPage) || st.pages[1] !== String(aPage)) throw new Error("翻页失败: " + JSON.stringify(st.pages));
  if (st.counts.some((v) => v !== "0")) throw new Error("重置后仍有残留框: " + JSON.stringify(st.counts));
  if (!st.cur) throw new Error("读不到当前题目");
  return st;
}
