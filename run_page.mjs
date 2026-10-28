// 跑整页录入（题目框 + 答案框逐题 restore+run，末尾服务端回读）
//
//   $env:RUN_PAGE="34"
//   .\run_ego.ps1 -Js .\run_page.mjs -Out "$env:TEMP\p34_run.txt" -TimeoutSec 2400
//
// RUN_PAGE 由 run_ego.ps1 写进 _run.mjs 的 prelude（task space 继承不到 shell 环境变量）。
// 提交数据必须当次单独授权：这个脚本会真的往库里写。
import { main } from "./pageRun.mjs";

const page = process.env.RUN_PAGE;
if (!page) throw new Error("没给 RUN_PAGE：要经 run_ego.ps1 启动，或自己先把 process.env.RUN_PAGE 写进 prelude");

// ego 的 node 跑在 task space 里，相对路径不可靠，用 import.meta.url 定位
// （这里指向被复制出来的 _run.mjs，仍在仓库根目录）。
const file = new URL(`pages/p${page}.json`, import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");

const r = await main(file);
console.log("DONE " + JSON.stringify({
  page,
  ok: r.done.length,
  fail: r.failed.length,
  sumMs: r.done.reduce((s, d) => s + d.ms, 0),
}));
