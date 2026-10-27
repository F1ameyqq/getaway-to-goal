# usense 教材录入工具

把教材扫描图变成平台里的题目框，把人从「翻页、拖框、点按钮」里摘出来。

**核心是一份坐标**：给定一页扫描图，产出「题目框 / 选项框 / 答案框」的源坐标 JSON，人工或 agent 看图复核后再由浏览器自动提交。

---

## 它做成过什么

**2026-10-27：一页 5 题真实提交到标注平台，order 90–94，服务端回读结构全部正确。**
单题耗时 54–68 秒（含全量重置页面）。这是唯一一次端到端实测记录，别当成规模化的保证。

---

## 两个阶段，能力边界不同

| 阶段 | 做什么 | 需要什么 | 克隆后能直接跑吗 |
|---|---|---|---|
| **离线** | 图 → 坐标 JSON → 自检 → dry run | Python + Pillow + numpy + Node | ✅ **能** |
| **在线** | 坐标 → 真在平台上画框提交 | ego lite + 平台登录态 | ❌ 见下面三步 |

在线阶段克隆后必须人工做三件事（agent 做不了）：

1. **装 ego lite**（浏览器运行时，不在本仓库里）
2. **登录标注平台**（token 存在浏览器 localStorage，不能随仓库分发）
3. **首次打开时过平台证书页**（平台证书过期，需要人点「继续前往」）

这三步只做一次。做完之后，agent 就能跑完整流程。

---

## 快速开始

### 0. 环境

```
Python 3 + pillow + numpy
Node 18+
ego lite（只有在线提交需要）
```

### 1. 配置

```powershell
Copy-Item config.example.json config.json
```

然后改 `config.json` 里这几项：

| 字段 | 说明 |
|---|---|
| `platform.fileId` | 平台上那本书的 id（页面里能看到） |
| `platform.dirNode` | 左侧目录树里要点的节点全名 |
| `paths.srcDir` | 扫描图放哪（相对本目录或绝对路径） |
| `paths.egoExe` | ego-browser 的绝对路径；留空则从 PATH 找 |

`config.json` 不入库。

### 3. 环境自检（在线提交之前必做一次）

```powershell
.\run_ego.ps1 -Js .\check_env.mjs -Out "$env:TEMP\check.txt" -TimeoutSec 240
```

它会依次验证：ego 能连上 → 登录态有效 → 能选到书 → 能选到目录 → 能翻页 → 当前页无残留框。

看到 `CHECK_ENV_OK` 就说明在线阶段的三个前提（ego、登录、证书）都过了。失败时它会直接告诉你该改哪一项。

### 4. 抓图（需要 ego）

改 `shotPages.mjs` 顶部的 `QPAGES`，然后：

```powershell
.\run_ego.ps1 -Js .\shotPages.mjs -Out "$env:TEMP\shots.txt"
```

图片落到 `paths.srcDir`。

### 4. 出坐标

```powershell
# 出栏图，看每行属于哪题（输出到 srcDir，文件名带页号）
python cols.py <图> 4.5 L 44 258
python cols.py <图> 4.5 R 262 497

# 写 spec 后生成坐标
python measure_page.py specs\p33_qspec.json out_q.json
python measure_page.py specs\p33_aspec.json out_a.json

# 合成录入用的页文件
python make_page.py out_q.json out_a.json 33 175 specs\p33_types.json pages\p33.json
```

### 5. 复核（**不许跳过**）

```powershell
python overlay.py <图> out_q.json preview.png q
```

打开 `preview.png`，**逐题说出框里是什么内容**。说不出来就是没看，就是错的。

`measure_page.py` 会顺带做几何自检（空框、退化框、跨题重叠），结果一路带进 `pages/*.json` 的 `_check` 字段。

### 6. dry run（不需要 ego）

```powershell
node -e "import('file:///<本目录>/pageRun.mjs').then(async m=>{console.log(JSON.stringify(await m.main('<本目录>/pages/p33.json',{dry:true})))})"
```

必须看到 `CHECK_CLEAN` 且逐题数量对。

### 7. 提交（不可逆）

```powershell
.\run_ego.ps1 -Js .\p33run.mjs -Out "$env:TEMP\run.txt" -TimeoutSec 560
```

`p33run.mjs` 只是三行调用 `pageRun.main(...)`，照抄改路径即可。

---

## 为什么 dry run 通过不等于可以提交

dry run 只验证**结构**：几题、几个框、什么类型、页号。它**完全不验证框在图上框住了什么**。

框整体偏移一行、框住隔壁选项、只框住「13.」没框住答案 —— dry run 一样全绿。

**框的位置只有一种验证方式：画在图上，亲眼看。** 这是本工具最容易被跳过、也最容易造成返工的一步。

---

## 故障排查

| 症状 | 原因 | 处理 |
|---|---|---|
| `ego lite closed the connection because ego-browser is running as administrator` | 终端是管理员 | `run_ego.ps1` 会自动改走计划任务降权；普通终端不受影响 |
| `not found: 选择书籍` | 浏览器停在空白新标签页 | `restorefn.mjs` 已自动导航到 `platform.url`；若仍失败，检查登录态 |
| `dir node not found` | `platform.dirNode` 与目录树文字不完全一致 | 去掉多余空格逐字比对 |
| `翻页失败` | 页码超范围或平台还没加载完 | 检查 qPage/aPage |
| `重置换后仍有残留框` | 该页已有未提交的框 | 先在平台上处理掉 |
| `识别归属错误` | 框画到了别的题上 | **这是保护机制，不是 bug**；它会中止提交，不会写脏数据 |
| `READBACK_MISMATCH` | 框数量与坐标文件不符 | 看 `got` / `want`；跨栏题本来就有多个题目框 |

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `HANDOFF.md` | **给接手的 agent 的完整规程**，含检查点、必须停下的情形、踩过的坑。先读它 |
| `config.mjs` / `config.json` | 平台常量与路径 |
| `run_ego.ps1` | 启动入口：非管理员直接跑，管理员自动降权 |
| `shotPages.mjs` / `shotAns.mjs` | 抓题目区 / 答案区截图 |
| `cols.py` | 出带行号的栏图，用于判断每行属于哪题 |
| `ans_dump.py` | 打印答案区每行的坐标范围，用于手写 `@` 矩形 |
| `probe_cols.py` | 找双栏页的中缝 |
| `measure_page.py` | **主入口**：spec + 图 → 坐标，自带几何自检 |
| `make_page.py` | 题目坐标 + 答案坐标 → 录入用页文件 |
| `overlay.py` | 把框画到图上，供目视复核 |
| `pageRun.mjs` | 逐题：重置 → 画框 → 识别 → 提交 → 回读 |
| `lib.mjs` | 单题执行器，含三道提交前校验 |
| `restorefn.mjs` | 全量重置页面 |

---

## 已知边界

- **答案区的行分割不可靠**。题号与子问 `(1)(2)(3)` 的间隙混在一起，自动切分必错，需要手工给 `@` 矩形。这是当前每页耗时的主要来源。
- **答案页不按页码对应**。教师用书一页常装多页教材的答案，必须去图里找课时标题。
- **版面会变**。已验证的启发式参数在第 4 种版面上可能失效；失效时工具给的是错框而不是报错，所以第 4 步复核不能省。
- **一页最多验证过 11 题**，更大规模未测。
- **单个平台、单个账号**。换平台要改 `restorefn.mjs` 和 `lib.mjs` 里的选择器。
