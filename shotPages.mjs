// 批量截题目区图。选书一次，之后逐页翻+截图。全程只读，不提交任何框。
// 用法：改 QPAGES 即可。
import fs from "node:fs";
import { P, SRC_DIR } from "./config.mjs";

const QPAGES = [31, 32, 33, 34, 35];
const T0 = Date.now();
const log = (m) => console.log(`[${Date.now() - T0}ms] ${m}`);
fs.mkdirSync(SRC_DIR, { recursive: true });

const task = await taskSpace(P.taskSpace);
const page = task.page(P.page);

async function clickText(txt) {
  const p = await page.evaluate((t) => {
    const e = [...document.querySelectorAll("button,span,div")]
      .filter((x) => x.getBoundingClientRect().width > 0)
      .find((x) => x.innerText.trim() === t);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  }, txt);
  if (!p) throw new Error("not found: " + txt);
  await page.mouse.click(p.x, p.y);
}

await clickText("选择书籍");
log("clicked 选择书籍");
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
log("clicked 选择");
await page.waitForTimeout(6000);

const hit = await page.evaluate((dirNode) => {
  const e = [...document.querySelectorAll(".el-tree-node__content")]
    .find((x) => x.innerText.replace(/\s+/g, " ").trim() === dirNode);
  if (!e) return null;
  e.scrollIntoView({ block: "center" });
  return true;
}, P.dirNode);
if (!hit) throw new Error("dir node not found: " + P.dirNode);
await page.waitForTimeout(900);

const node = await page.evaluate((dirNode) => {
  const e = [...document.querySelectorAll(".el-tree-node__content")]
    .find((x) => x.innerText.replace(/\s+/g, " ").trim() === dirNode);
  const r = e.getBoundingClientRect();
  return { x: Math.round(r.x + 40), y: Math.round(r.y + r.height / 2) };
}, P.dirNode);
await page.mouse.click(node.x, node.y);
log("clicked dir");
await page.waitForTimeout(3000);

async function inputPositions() {
  return page.evaluate(() =>
    [...document.querySelectorAll("input")]
      .filter((i) => i.getBoundingClientRect().x > 0)
      .map((i) => {
        const r = i.getBoundingClientRect();
        return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
      })
  );
}

async function gotoPage(pos, n) {
  await page.mouse.click(pos.x, pos.y);
  await page.waitForTimeout(400);
  await page.keyboard.down("Control");
  await page.keyboard.press("a");
  await page.keyboard.up("Control");
  await page.waitForTimeout(200);
  await page.keyboard.type(String(n), { delay: 90 });
  await page.keyboard.press("Enter");
  await page.waitForTimeout(4500);
}

const pos = await inputPositions();
if (pos.length < 1) throw new Error("no page inputs");

for (const q of QPAGES) {
  await gotoPage(pos[0], q);
  const st = await page.evaluate(() => {
    const cs = [...document.querySelectorAll("canvas.pdf-canvas")].map((c) => {
      const r = c.getBoundingClientRect();
      return { ox: +r.x.toFixed(2), oy: +r.y.toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2), iw: c.width, ih: c.height };
    });
    const t = document.body.innerText.replace(/\s+/g, " ");
    return {
      cur: (t.match(/当前题目[:：]\s*(\d+)/) || [])[1],
      pages: [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0).map((i) => i.value).slice(0, 2),
      canvases: cs,
      dpr: devicePixelRatio,
    };
  });
  const c = (st.canvases || [])[0];
  if (!c) { log(`p${q} NO_CANVAS cur=${st.cur} pages=${JSON.stringify(st.pages)}`); continue; }
  // 确认真的翻到了：题号输入框的值应为 q
  const shot = await page.cdp("Page.captureScreenshot", {
    format: "jpeg", quality: 95,
    clip: { x: c.ox, y: c.oy, width: c.w, height: c.h, scale: 3 },
  });
  const buf = Buffer.from(shot.data, "base64");
  const f = SRC_DIR + "/p" + q + "_hi.jpg";
  fs.writeFileSync(f, buf);
  log(`p${q} cur=${st.cur} pages=${JSON.stringify(st.pages)} canvas=${c.w}x${c.h} iw=${c.iw} -> ${buf.length} bytes`);
}

console.log("SHOTPAGES_DONE");
