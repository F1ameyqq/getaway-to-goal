// 环境自检。克隆后第一件事跑它。
// 会依次验证：ego 能连上 → 登录态有效 → 能选到书 → 能选到目录 → 能翻页 → 当前页无残留框。
// 全程只读，不画框、不提交。
//
// 用法（需要 ego）：
//   .\run_ego.ps1 -Js .\check_env.mjs -Out "$env:TEMP\check.txt" -TimeoutSec 240
//
// 页码可用环境变量覆盖，默认 33/175：
//   $env:CHECK_QPAGE="34"; $env:CHECK_APAGE="175"
import { restore } from "./restorefn.mjs";

const qPage = Number(process.env.CHECK_QPAGE || 33);
const aPage = Number(process.env.CHECK_APAGE || 175);

try {
  const ctx = await restore({ qPage, aPage });
  console.log("CHECK_ENV_OK " + JSON.stringify(ctx));
  console.log(`  页码      ${ctx.pages.join(" / ")}`);
  console.log(`  当前题目   ${ctx.cur}`);
  console.log(`  残留框    题目框 ${ctx.counts[0]} / 答案 ${ctx.counts[1]} / 选项 ${ctx.counts[2]}`);
  console.log("环境就绪。下一步：出坐标 → overlay 看图 → dry run。");
} catch (e) {
  console.log("CHECK_ENV_FAIL " + e.message);
  console.log("");
  console.log("对照 README 的「故障排查」：");
  console.log("  not found: 选择书籍   -> 登录态失效，或平台页面没加载出来");
  console.log("  no 选择 button        -> config.json 的 platform.fileId 不对");
  console.log("  目录节点未找到        -> config.json 的 platform.dirNode 与目录树文字不一致");
  console.log("  翻页失败              -> 页码超出范围");
  console.log("  重置后仍有残留框      -> 该页有未提交的框，先处理掉");
  process.exitCode = 1;
}
