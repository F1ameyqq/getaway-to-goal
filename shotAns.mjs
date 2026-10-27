// 截答案区图。题目页固定 QPAGE，答案页逐个翻。只读。
import fs from "node:fs";
import { P, SRC_DIR } from "./config.mjs";

const QPAGE = 31;
const APAGES = [174, 175, 176];
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
await page.waitForTimeout(3000);
log("book+dir ready");

const pos = await page.evaluate(() =>
  [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0).map((i) => {
    const r = i.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  })
);
if (pos.length < 2) throw new Error("need 2 page inputs, got " + pos.length);

async function gotoPage(p, n) {
  await page.mouse.click(p.x, p.y);
  await page.waitForTimeout(400);
  await page.keyboard.down("Control");
  await page.keyboard.press("a");
  await page.keyboard.up("Control");
  await page.waitForTimeout(200);
  await page.keyboard.type(String(n), { delay: 90 });
  await page.keyboard.press("Enter");
  await page.waitForTimeout(4500);
}

await gotoPage(pos[0], QPAGE);
log("q page " + QPAGE);

for (const ap of APAGES) {
  await gotoPage(pos[1], ap);
  const st = await page.evaluate(() => {
    const cs = [...document.querySelectorAll("canvas.pdf-canvas")].map((c) => {
      const r = c.getBoundingClientRect();
      return { ox: +r.x.toFixed(2), oy: +r.y.toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2), iw: c.width, ih: c.height };
    });
    return {
      pages: [...document.querySelectorAll("input")].filter((i) => i.getBoundingClientRect().x > 0).map((i) => i.value).slice(0, 2),
      canvases: cs,
    };
  });
  const c = (st.canvases || [])[1];
  if (!c) { log(`a${ap} NO_CANVAS`); continue; }
  const shot = await page.cdp("Page.captureScreenshot", {
    format: "jpeg", quality: 95,
    clip: { x: c.ox, y: c.oy, width: c.w, height: c.h, scale: 3 },
  });
  const buf = Buffer.from(shot.data, "base64");
  const f = SRC_DIR + "/a" + ap + "_hi.jpg";
  fs.writeFileSync(f, buf);
  log(`a${ap} pages=${JSON.stringify(st.pages)} canvas=${c.w}x${c.h} -> ${buf.length} bytes`);
}

console.log("SHOTANS_DONE");
