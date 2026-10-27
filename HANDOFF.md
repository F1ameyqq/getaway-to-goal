# usense 页面测量 — 交接文档

给接手的 agent 看。读完这页能省你半小时，漏读后面的「检查点」会写脏数据进库。

---

## 一、先读这段：dry run 通过 ≠ 框是对的

这是本流程最大的陷阱，所有返工都出在这。

`pageRun.mjs` 的 dry run 只验证**结构**：这页几题、每题几个框、类型、页号。
它**完全不验证框在图上框住了什么**。框整体偏移一行、框住隔壁选项、只框住「13.」没框住答案 —— dry run 一样打印 `✅`。

**框的位置只有一种验证方式：把框画在图上，亲眼看。** 就是你，agent，看图。

别指望「跑通了就对了」。跑通只说明程序没崩。

---

## 二、每页必须走的检查点（不许跳）

| # | 步骤 | 通过标准 |
|---|---|---|
| 1 | 抓图 `shotPages.mjs` / `shotAns.mjs` | 下一步会打印 `IMG_OK`（尺寸 + 墨迹占比）。**不用再单独打开原图看尺寸/空白** |
| 2 | `guide.py` 出标尺图（题目页一张、答案页一张） | **亲眼看**每行属于哪题；图上的 `L03`/`A07` 与 spec 行号完全一致 |
| 3 | 写 spec `pNN_qspec.json` | 每个 n 都对应到具体行 |
| 4 | **`prepare_page.py` 一条命令** | `IMG_OK` + `PAGE` + `CHECK_CLEAN`，并打印两张 overlay 路径 |
| 5 | **看这两张 overlay 图** | **逐题复述框内是什么内容**（见下） |
| 6 | `pageRun.mjs --dry`（用 node，不开浏览器） | `CHECK_CLEAN` 且全绿 |
| 7 | **停手，报告** | 提交要**单独授权** |

第 4 步内部依次做 measure → make → overlay，并做几何自检：退化框、空框、同题选项框互吞、**跨题重叠**。跨题重叠最有用——框整体偏了一行，几乎必然和隔壁题的框撞上。

自检结果会一路带进 `pages/pNN.json` 的 `_check` 字段，dry run 时也会打出来。**看到 `CHECK_WARN` 就别往下走。**

第 5 步是唯一能发现位置错误的一步。做的时候**逐题说出框内文字**，不是「看起来还行」。说不出来 = 没看。

### 第 5 步的自检话术（照着做）

对每题的每个框，写下「这个框里是：___」。
- 题干框里应该是完整题干（含末尾的下划线、括号、单位）
- 选项框里应该是「A. xxx」到选项内容结束
- 答案框里应该是对应题号的完整解答

**任何一框你说不清里面是什么，就是错的，回去改 spec。**

---

## 三、必须停下来问的情形（不许自己决定）

先弄清一件事，能省掉两个假问题：

> **教材题号 `n` 只是本地标签，不参与写库。** `pageRun.mjs` 写库用的是 `order: ctx.cur`（平台「当前题目」指针），`n` 只用于日志和 `from/to` 筛选。所以「题号重复」「题号不从 1 开始」本身都不是技术障碍。

真正要保证的是：**`items` 里 `n` 的排列顺序 = 版面从上到下、左栏→右栏的阅读顺序**。顺序错了 `run()` 的 order 校验会报 `识别归属错误…不要提交`，**它会中止而不是写脏数据**（`lib.mjs:183`）。这是安全网，不是灾难。

即便如此，下面这些仍要停：

1. **不确定这页在平台上是第几页 / 承接哪一页** → 别按页码推算。答案页尤其：一页装多页答案（a175 装了 p30–p33）。
2. **答案是跨页拼起来的**（本题解答有一部分在下一栏）→ 确认要框的范围，别漏下半截。
3. **同一题改了两轮还不对** → 版面类型没覆盖，报告版面长什么样，别继续硬调。
4. **答案页找不到对应答案** → 去图里找课时标题，别用页号 +1 推算。
5. **ego hard stop / 证书弹窗** → 等人，不是重试。

---

## 四、常见的静默错误（脚本不会报错，只有你的眼睛能抓）

- 题号跳了一行 → 整题框偏移一行
- 选项框吞掉页边淡竖线 → 右边界拉到栏边（看起来「框很大」，其实错）
- 下划线太浅没被检出 → 框在「=」前结束，答案区少一块
- 跨栏题只框了左栏 → 右栏那半丢了
- 答案框把两个小问合成一个 → 数量对，内容错

---

## 五、环境事实

1. **如果 shell 是管理员**，ego-browser 直接调用会被拒绝：
   `ego lite closed the connection because ego-browser is running as administrator`
2. `run_ego.ps1` 已经处理了这件事：**检测到管理员才走 `schtasks /RL LIMITED` 降权，普通终端直接跑**。
3. **不要把含 `/` 的路径当参数传给 schtasks** —— `/` 会被吃掉，路径变成 `C:UsersASUS...`（所以管理员分支要包一层 `ego.cmd`）
4. 所有 `.ps1` 必须带 **UTF-8 BOM**，否则中文注释会让 PowerShell 5.1 解析错乱（症状：变量莫名是 null）
5. 所有 `.cmd` 必须是 **CRLF** 行尾（症状：返回码 0 但什么都不执行）

## 六、跑一个 ego 脚本

在**本目录**下：

```powershell
.\run_ego.ps1 -Js .\你的脚本.mjs -Out "$env:TEMP\_out.txt" -TimeoutSec 180
```

`run_ego.ps1` 把脚本复制成 `_run.mjs`，并据 `config.json` 生成 `ego.cmd`（绕开第 3 条的坑）。
输出直接打印，末尾有 `EXIT=0`。

### 例外：dry run 不需要 ego

`{dry:true}` 只解析坐标、不碰浏览器，**直接用 node 跑就行**，别走 `run_ego.ps1`：

```powershell
node -e "import('file:///<本目录绝对路径，正斜杠>/pageRun.mjs').then(async m=>{console.log(JSON.stringify(await m.main('<本目录绝对路径>/pages/pNN.json',{dry:true})))})"
```

`prepare_page.py` 跑完会直接把这条命令打印出来，照抄即可。`main()` 收的是**文件路径**，不要传 `file://` URL。

省掉一次开浏览器，也就省掉一次 hard stop / 证书弹窗的机会。

### 想知道每题时间花在哪

```powershell
$env:RESTORE_TIMING="1"
.\run_ego.ps1 -Js .\check_env.mjs -Out "$env:TEMP\check.txt" -TimeoutSec 240
```

会多打一行 `RESTORE_TIMING {"nav":…,"reload":…,"book_open":…,…}`（单位 ms），`pageRun` 的每题行也会带 `restore=…ms`。不设这个环境变量时输出维持原样。

### 平台常量都来自 config.json

`fileId`、`dirNode`、`taskSpace`、`page`、`srcDir`、`egoExe` 全在 `config.json` 里，**脚本里不许再写死**。
缺 `config.json` 会直接报错——宁可启动就失败，也不要带着别人的书号跑。

## 七、绝对不能做的事

- **提交任何数据**：除非当次明确授权，只读不写。上一页的授权不延续到这一页。
- **ego hard stop**（浏览器被用户接管）：不能重试、不能 takeOverTaskSpace，立刻停下报告。
- **证书过期**：新 profile 要人工点「继续前往」，这属于等人，不是重试。
- **杀正在运行的 ego 进程**：日志是异步缓冲的，杀了就永久丢失。
- **跳过 overlay 看图**：见第一节。

## 八、关键换算

| | canvas CSS | 源坐标 | s | pad |
|---|---|---|---|---|
| 题目区 canvas[0] | 519.778 × 669.1 | 1220 × 1693 | 0.395216 | x=18.81, y=0 |
| 答案区 canvas[1] | 436.708 × 669.0 | 1145 × 1620 | 0.381405 | x=0, y=25.56 |

截图缩放 `S = 图片宽度 / canvas_CSS_宽度`（一般是 4.5）。
`css = src * s + pad`，`src = (css - pad) / s`。

## 九、脚本清单

| 脚本 | 用途 |
|---|---|
| `run_ego.ps1` | 降权跑 ego 脚本（入口） |
| `ego.cmd` | 计划任务包装，写死引用 `_run.mjs` |
| `shotPages.mjs` | 批量抓题目区图，改文件顶部的 `QPAGES` |
| `shotAns.mjs` | 抓答案区图，改 `QPAGE` / `APAGES` |
| `guide.py` | **一行一张图**：题目页左右栏并排 + 行号；答案页单栏 + 行号/块号 + 坐标表。替代 `cols.py` 的四张栏图 |
| `prepare_page.py` | **主入口**：图像自检 → measure → make → overlay 一条命令跑完 |
| `measure_page.py` | spec + 截图 → 坐标 JSON（自带 CHECK 自检） |
| `make_page.py` | 题目坐标 + 答案坐标 → `pages/pNN.json` |
| `overlay.py` | 把框画在图上（**第二节第 5 步，必做**）。答案图自动裁掉无关区域 |
| `cols.py` | 旧版栏图（已由 `guide.py` 取代，只在 guide 出问题时效备用） |
| `ans_dump.py` | 打印答案区每行 y 范围 + 块 x 范围（`guide.py a` 已包含同样的表） |
| `pageRun.mjs` | 逐题 restore + run + 服务端回读 |
| `probe_cols.py` | 找双栏页的中缝 |

**上表之外的都是探索期遗留脚本，别用。** 目录里还有 `q02.mjs`–`q14.mjs`、`reset.mjs`、`restore.mjs`、`measure.py`、`gen_coords.py`、`shot29.mjs`、`p3Ndry.mjs` 等 60 多个文件，是当时的临时试验，参数和当前流程不一致。拿不准就先读它的头部注释，或者直接按第十节的流程从零写。

## 十、工作流

```powershell
# 1. 抓图（需要 ego）
.\run_ego.ps1 -Js .\shotPages.mjs -Out "$env:TEMP\shots.txt"

# 2. 出标尺图：题目页一张（左右栏并排）、答案页一张
python -I guide.py <pNN_hi.jpg> <pNN_guide.png> q --cols L:44-258,R:262-497
python -I guide.py <aNNN_hi.jpg> <aNNN_guide.png> a --x 8-218 --y 460-550
#    答案页不确定 y 区间时，先出整页坐标尺：
python -I guide.py <aNNN_hi.jpg> <aNNN_full.png> a --full

# 3. 写 spec（每页一个 pNN_qspec.json / pNN_aspec.json）

# 4. 一条命令：自检 → 出坐标 → 合成 → overlay
python -I prepare_page.py specs\pNN_qspec.json specs\pNN_aspec.json <qPage> <aPage> specs\pNN_types.json pages\pNN.json
#    终端会打印 VIEW_Q / VIEW_A 两个路径 —— 打开，逐题说出框里是什么

# 5. dry run（照 prepare_page 打印的 NEXT 命令抄）→ 停手报告
```

注意：`guide.py` 的 `--y` 必须和 spec 里的 `y` 一致，否则 `A07` 不是 spec 里的 `A07`。题目页默认 `20-660`。

## 十一、spec 格式

```json
{
 "src": "C:/.../p31_hi.jpg",
 "kind": "q",
 "cols": {"L": [44, 258], "R": [262, 497]},
 "items": [
  {"n": 3, "stem": ["L08"], "opt": ["L09x4"]},
  {"n": 7, "stem": ["L23-L25", "R00-R01"]}
 ]
}
```

- `kind: "q"` 题目页（要写 `cols`）；`"a"` 答案页（写 `x` 和 `y`）
- `stem` 每个 span 一个框；`opt` 展开成选项框
- `L09x4` = 该行横排切 4 个；`L11-L14` = 每行一个
- 答案页：`A4:0-5` = 第 4 行块 0..5；`A7-8:0` = 行 7..8 合并
- `@20,91,214,119` = 直接给 CSS 矩形（整块用，绕过行分割）

**完整示例**（格式照抄，内容必须自己看图定，别抄行号）：
- 纯自动切分：`srcpages/p31_qspec.json`、`srcpages/p32_qspec.json`
- 混合手工 `@`：`srcpages/p33_qspec.json`（题目区）、`srcpages/p33_aspec.json`（答案区）
- 反例（故意写错的，用来验证自检）：`p28run/_selftest_neg.json`

## 十二、已知的坑

1. 管理员 → 必须走 `run_ego.ps1`
2. schtasks 吃 `/` → 路径不能当参数
3. PS 5.1 无 BOM → 中文注释坏
4. `.cmd` 用 LF → 静默不执行
5. canvas 是 1:1 无超采样，本地 OCR 基本不可用（纯数字还行）
6. **特殊版面**：上双栏 + 下通栏的页，列投影找不到中缝，要手工给 `@` 框
7. 行分割参数：题目页 `th=200 min_ink=20`（MIN_INK 才是闸门，不是 TH）；答案页 `th=225 min_ink=2`
8. 页面上的 `▶知识点1`、`A 基础题《`、页码会被测成独立行，写 spec 时跳过
9. **左右栏 X0 不是固定的**：p33 左栏内容比 p29 靠左，`X0=44` 会把「A.」切掉。症状是选项框左边界贴着字母。改用 `X0=36` 或直接给 `@` 矩形。
10. **选项分组按最大间隙切，不按块数均分**（已修进 `opt_boxes`）。块数会随噪声块变化，均分点会跑到选项内部。
11. **答案区行分割不可靠**：题号与子问 `(1)(2)(3)` 的间隙混在一起，TH=200/180/160 三档全失败。**手工 `@` 矩形是正解，不是 fallback。**
12. **续表**：`p33` 是 `p32` 的续表。教材上题号从 12 起排，这个数字不影响写库（见第三节开头），但**阅读顺序**要接在上一页之后。
13. **答案页一页装多页答案**：p29→a174；p30/p31/p32/p33 全在 **a175**。别按页号推算。
14. **一题可以有多个框**：跨栏题（左栏末 + 右栏首）提交后平台记 **2 条 question**。回读校验必须按实际框数比，别假设「题干有就 1」（`pageRun.mjs` 曾因此误报，已修）。
15. **回读接口不返回 OCR 文本**（`get_manual_annotations_unified` 的 `ocr_result` 是空的）。框内内容对不对，靠 `run()` 里的 OCR 归属校验（`lib.mjs:183`）保证——归属错了会中止不提交，不会静默写错。
16. **首次提交实测（2026-10-27）**：p33 五题落库 order 90–94，结构全部正确，单题约 54–68 秒。
