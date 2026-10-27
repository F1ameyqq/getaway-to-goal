// 读取同目录 config.json。平台相关的常量一律从这里来，脚本里不许再写死。
// 缺 config.json 直接报错——宁可启动就失败，也不要带着别人的书号跑。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const HERE = path.dirname(fileURLToPath(import.meta.url));

const cfgPath = path.join(HERE, "config.json");
if (!fs.existsSync(cfgPath)) {
  throw new Error(
    "缺少 config.json。先复制 config.example.json 为 config.json，填好 fileId / dirNode / paths。"
  );
}

export const CONFIG = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
export const P = CONFIG.platform || {};
export const SRC_DIR = path.resolve(HERE, (CONFIG.paths && CONFIG.paths.srcDir) || "srcpages");

for (const k of ["url", "fileId", "dirNode"]) {
  if (!P[k]) throw new Error("config.json 缺少 platform." + k);
}
