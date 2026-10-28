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

会多打一行 `RESTORE_TIMING {"nav":…,"reload":…,"book_open":…,…}`（单位 ms），`pageRun` 的每题行会带 `restore=…ms`，再跟一行 `stages {"ready":…,"boxes":…,"type":…,"ocr":…,"commit":…,"tail":…}`。不设这个环境变量时输出维持原样。

> ego 的 node 代码跑在常驻 task space 里，**继承不到调用方 shell 的环境变量**。
> `run_ego.ps1` 会把 `RESTORE_TIMING` / `CHECK_QPAGE` / `CHECK_APAGE` 写进 `_run.mjs` 的 prelude，
> 所以按上面的写法设置是生效的；直接 `ego-browser nodejs -e` 跑则不生效。

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
| `run_page.mjs` | **录入入口**：`$env:RUN_PAGE="34"` 后经 `run_ego.ps1` 跑整页（会写库，需当次授权） |
| `check_edges.py` | 边框审计：每个框外面套 1.2 CSS 的环查墨迹，抓「框切掉括号/分数线」这类 overlay 上看不出的偏差 |
| `ordercheck.mjs` | 纯函数：预检、落点回读、提交后对账。不碰浏览器，可单测 |
| `test_ordercheck.mjs` | `node test_ordercheck.mjs`，15 条断言，改 `ordercheck.mjs` 前后都跑 |
| `dirtree.mjs` | 课时名 → `directory_id` 的唯一权威来源（读平台目录接口，见第 28 条） |
| `dirlist.mjs` | **只读**：打印每个课时的 id + 已有题数，复核落点/清残局前后都用它 |
| `cleanup_orders.mjs` | **删题**：按题号区间删（默认 dry-run，`CLEAN_APPLY=1` 才真删），见第 30 条 |
| `audit_orders.mjs` | **只读**：按题号汇总/单条 dump/目录树 dump |
| `propose_spec.py` | 离线出 spec 草案 + 页面闸门（A/B/C + 硬违规），见 `drafts/run_all.py` |
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
python -I prepare_page.py specs\pNN_qspec.json specs\pNN_aspec.json <qPage> <aPage> specs\pNN_types.json pages\pNN.json --grow 1.5 --grow-a 0 --lesson "第2课时 二次根式的化简及加减运算"
#    终端会打印 VIEW_Q / VIEW_A 两个路径 —— 打开，逐题说出框里是什么
#    --grow 把题目框统一外扩 N 个 CSS 像素（默认 0）；--grow-a 单独管答案框（默认跟 --grow）。
#    答案框多是手工 @ 紧排的，外扩了会互相吞，所以答案侧一般给 0。
#    再审一遍边框（可选但便宜）：
python -I check_edges.py pages\pNN.json specs\pNN_qspec.json specs\pNN_aspec.json

# 5. dry run（照 prepare_page 打印的 NEXT 命令抄）→ 停手报告
```

注意：`guide.py` 的 `--y` 必须和 spec 里的 `y` 一致，否则 `A07` 不是 spec 里的 `A07`。题目页默认 `20-660`。

### 真跑（会写库，必须当次单独授权）

```powershell
# 开跑前：确认落点和课时里已有几题，把数字写进 pages\pNN.json 的 expectBefore
.\run_ego.ps1 -Js .\dirlist.mjs -Out "$env:TEMP\dirs.txt" -TimeoutSec 240
Select-String -Path "$env:TEMP\dirs.txt" -Pattern "二次根式"

$env:RUN_PAGE="34"
.\run_ego.ps1 -Js .\run_page.mjs -Out "$env:TEMP\p34.txt" -TimeoutSec 900
```

跑完先看 `RESULT` 那行的 `ok / fail / readbackBad / orders`，再跑一次 `dirlist.mjs` 确认目标课时题数正好加上本页题数、别处没多出来。

### 跑砸了要清残局

```powershell
$env:CLEAN_LO="95"; $env:CLEAN_HI="104"        # 先只列，不写
.\run_ego.ps1 -Js .\cleanup_orders.mjs -TimeoutSec 300
$env:CLEAN_APPLY="1"                            # 确认列出来的对，才真删
.\run_ego.ps1 -Js .\cleanup_orders.mjs -TimeoutSec 420
```

**区间是全文件的，不是按课时。** 删之前务必看 dry-run 列出的每一条（题号 / 页 / 课时 id / 框数）对不对，别扫到别的课时。

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
17. **restore 提速（2026-10-28）**：reload 改走 `location.reload` + 新文档信号，翻页改用画布像素哈希。`check_env` 实测 restore 从 24s（稳定态）降到 **7.8–8.2s**；单题总耗时尚未重新做端到端实测。
18. **标注模式门禁（2026-10-28 才查明）**：平台只在**选中最子级目录（课时）**之后才允许画框。否则点 `题目(Q)` 只弹「请先选择左侧的目录！」就返回，画布照样收到 mousedown/mousemove，但**一个框都不登记**（counts 恒为 0）。这是「画了没反应」的真正原因，不是坐标或时序问题。
19. **目录树点击的箭头陷阱**：点 `.el-tree-node__content` 的 `x+40` 常常正落在展开箭头 `<i class="el-tree-node__expand">` 上，箭头自带 `click.stop`，节点根本不会被选中。必须点标签文字本体（`x + min(w/2, 30)`）。
20. **插题落点 = 选中课时目录的末尾，与 `cur`、与 OCR 的 `question_order` 都无关。**
    - 2026-10-28 事故一：restore 取「DOM 顺序第一个课时」（第1课时），而 cur=95，结果那一题被插到第1课时末尾 order 23，树 215→216，后续题号全部 +1，已删除复原。
    - 事故二（同日，更隐蔽）：改成「某课时末尾题号 = cur-1」的算术挑选法，p34 那 10 题整批落到**第3课时**而不是第2课时，而运行报告 `readbackBad: 0` —— 因为它只检查「写进去了」，不检查「写去了哪」。
    - **现在**：课时名由 `pages/pNN.json` 的 `lesson` 字段显式给出，`restore()` 缺这个字段直接抛错；选完回读 `.el-tree-node.is-current` 的文本，必须与 `lesson` 逐字相等；`dirId` 从目录接口取（第 28 条）；每题提交后 `reconcileOne` 比对 `order / directory_id / page_index / 框数`，任一不符整轮停止。
    - **算术推断课时一律不许用。** 相邻页常常同属一个课时，靠题号推只是碰巧对。
21. **提交后的两个事实（2026-10-28 受控实测）**：①画框**不会**自动清空（本地 counts 仍是提交前的值，直到 reload）；②`cur` 指针**会**推进（95→96）。所以「每页只 restore 一次、连续录」这条省时路线还差一步：必须先找到一个「清空框」的动作，否则会把上一题的框一起提交。
22. **拖框 `steps`**：`steps:16` 在本页约 15s/帧（大量 mousemove 被丢弃），`steps:2` 正常。鼠标单操作约 0.6–0.9s，别指望靠加等待提速。
23. **目录编辑 / 删除题目（2026-10-28 查明）**：左侧「目录编辑」→ 题目节点上的「删除题目」→ 确认框 →「应用变更」。删除按钮常被浮动的 `.collapse-btn` 盖住，鼠标点会静默 miss（`elementFromPoint` 不是按钮），要改用 DOM `el.click()`。删除后**后续题号自动重排，已有标注的 `order_in_level` 也会一起回退**（实测删 3 条框 + 一个节点后，树 216→215、标注 284→281、max order 95→94，完全复原）。
24. **reload 后的假就绪**：刚 reload 时两个页码输入框是空的，此时「输入框存在」≠「目录数据已拉」，翻页不生效（画布停在第一页）。就绪判据必须带「页码非空」。
25. **行框只贴墨迹主体**：分数（上下叠）、根号横线、上下标都比行框高/矮，行框会切掉它们。`--grow 1.5~2` 能盖住大部分；一屏里分数特别多的地方（如「特例1 √(1+1/3)=」那一列）直接给 `@` 矩形，别指望行框。
26. **`guide.py` 现在对题目页也打印行表**（`L00 y=36.2-44.7 blocks=…`），写 `@` 矩形时直接抄 y 范围，不用再靠眼看标尺图。
27. **`check_edges.py` 会报邻接误报**：答案区排得紧时，上一个框的墨迹会落进下一个框的外环（比如 11–14 的单字答案正好压在 15 题答案框的上沿）。环内墨迹只是提示，判读要回到坐标和 overlay。
28. **课时 id 只从目录接口取，不从 DOM / Vue 内部结构反推（2026-10-28 改）**：平台选书后会调
    `/qieti/api/annotate_ocr/directory/get?file_id=<fileId>`，返回整棵树 `{id,label,children}`，题目节点带 `isQuestion:true` 和 `order_in_level`。
    以前读 `__vue__` / `__vueParentComponent` 拿 `directory_id`，框架一变就读不到，整轮"没证据就中止"。现在 `dirtree.mjs` 负责解析、`restore()` 用它解析 `dirId` 和 `dirQ`，DOM 那条只作兜底。
    **课时 = 叶子目录**：没有子节点，或子节点全是题目。空课时（0 题）是合法的，旧代码 `if (!kids.length) continue` 会把它排除掉——这正是第2课时选不中的原因。
29. **`expectBefore`：页面 json 要声明"开跑前这个课时应该已有几题"**。一课多页时（p34 10 题 + p35 8 题都进第2课时），p34 写 `expectBefore: 0`，p35 写 `10`。
    多了 = 上一轮半途死掉留下残局，先跑 `cleanup_orders.mjs`；少了 = 前一页没跑完或跑错了课时。**两种都停，不猜。**
30. **删题 `cleanup_orders.mjs`**：按 `order_in_level` 区间删（**全文件范围，不是按课时**），从大号往小号删——删最大号不会让剩余题号重排。每条：进编辑模式 → 点删除 → 确定（只是暂存）→ 应用变更（才提交）→ 轮询服务端确认该号消失 → 校验其余号一个不少。任一步不符就停并点「取消」丢弃暂存。
    默认 dry-run，只有 `CLEAN_APPLY=1` 才写；`CLEAN_LO` / `CLEAN_HI` 给区间。**跑完必须看 `FINAL orders=… max=… holes=…`，再跑 `dirlist.mjs` 确认目标课时题数。**
    实测：删 10 条时在第 9 条（order 96）报过一次「删除确认框未出现」，重跑补掉——不是幂等，失败后重跑是正常操作。
31. **预检的边界（2026-10-28 重划）**：以前的预检把「近 10 分钟有新记录」和「每题框数畸形」都当阻断，结果一天内三次误拦：①把别的课时早先录的缺答案框记录（order 54–62/89）当成自己的残局；②把自己上一页刚提交的记录当成外人在写。
    现在的判据：
    - **阻断**：跑前观察 2.5 秒，题数 / 最大号在窗口内变化 → 确实有人在写；`cur != maxOrder+1`；目标课时题数 ≠ `expectBefore`。
    - **只告警**：每题框数畸形、题号空洞。它们不影响"接着追加"这件事，属于别的课时的数据质量。
    原则：**停下来的理由必须直接对应一个可执行动作**（跑 cleanup / 改 expectBefore / 等别人写完），否则就是噪音。
32. **端到端实测（2026-10-28，真写库）**：
    | 页 | 题数 | 落库题号 | 总耗时 | 其中 restore |
    |---|---|---|---|---|
    | p34 | 10 | 95–104 | 459.7 s | 11.3–13.6 s/题 |
    | p35 | 8 | 105–112 | 343.2 s | 11.0–13.7 s/题 |
    单题 31–61 s，restore 稳定在 11–14 s（约 25–30%），剩下是逐题画框+提交。**ego 的鼠标输入是串行的，只并行 restore 最多省 25–30%。**
