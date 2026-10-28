// dirlist.mjs —— 只读：打印目录树上每个课时的 id 和已有题数（服务端口径）。
// 用途：确认落点、确认某课时是否还有残留、删完之后复核。
//   .\run_ego.ps1 -Js .\dirlist.mjs -TimeoutSec 180
import { P } from "./config.mjs";
import { parseTree, lessonDirs, questionCount } from "./dirtree.mjs";

const task = await taskSpace(P.taskSpace);
const page = task.page(P.page);

const onPlat = await page.evaluate(() => /^https?:/.test(location.href) && location.origin.includes("lingshubao")).catch(() => false);
if (!onPlat) {
  await page.goto(P.url);
  for (let i = 0; i < 120; i++) {
    const ok = await page.evaluate(() => /lingshubao/.test(location.href)).catch(() => false);
    if (ok) break;
    await new Promise((r) => setTimeout(r, 250));
  }
}

const tok = await page.evaluate(() => JSON.parse(localStorage.getItem("user")).access_token);
const r = await page.fetch(`/qieti/api/annotate_ocr/directory/get?file_id=${P.fileId}`, {
  headers: { authorization: "Bearer " + tok },
  timeout: 30000,
});
const nodes = parseTree(r.body);
const lessons = lessonDirs(nodes);
let total = 0;
for (const d of lessons) {
  const n = questionCount(d);
  total += n;
  console.log(`LESSON q=${String(n).padStart(3)} id=${d.id}  ${d.path}`);
}
console.log(`TOTAL lessons=${lessons.length} questions=${total}`);
