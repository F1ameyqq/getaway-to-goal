# 任务：在一台干净的 Windows 机器上装好 usense 教材录入环境

> 这是**任务说明**，不是背景资料。按顺序执行。
> 看到 `[等人]` 就停下来，把要做的事说清楚，等人做完再继续。

---

## 你的目标

让 `check_env.mjs` 打印 `CHECK_ENV_OK`。

**不是**开始录入题目。录入是下一阶段的事，需要单独授权（见最后一节）。

---

## 人工已经准备好的东西

如果下面任何一项缺失，**先问，不要猜**：

- DSH 已安装并运行
- ego lite 安装包的**下载链接**，或客户已经下载好的文件（约 286 MB）
- 客户在标注平台上有账号
- 客户知道要录哪本书（`fileId`）和哪个目录节点（`dirNode`）

---

## 第 1 步：确认三个工具在位

```powershell
python --version
tar --version
git --version
```

- `python` 缺 → 装 Python 3.9+，勾选 "Add to PATH"
- `tar` 缺 → Windows 10 1803 以下；正常机器都有
- `git` 缺 → 装 Git for Windows

---

## 第 2 步：装 ego lite（**不要跑官方安装器**）

官方 `egoliteSetup.exe` 在部分机器上会卡住不返回，所以仓库自带离线解包安装脚本。

### 2.1 把安装包取到本机

**首选：自己下载**（不要问客户"安装包在哪"，问他**链接**）

```powershell
New-Item -ItemType Directory -Force C:\ego-pkg | Out-Null
curl.exe -L -o "C:\ego-pkg\ego-0.6.1.13-x64.crx3" "<客户给的下载链接>"
```

用 `curl.exe` 而不是 `curl` —— PowerShell 里 `curl` 是 `Invoke-WebRequest` 的别名，参数不通用。

下完核对大小，应该是 **286,365,034 字节**：

```powershell
(Get-Item C:\ego-pkg\*.crx3).Length
```

对不上就是文件被截断或链接给错了，**别硬装**，重新下。

> 如果客户说"文件我已经下好了"，**不要问路径** —— 直接进 2.2，脚本会自己去
> `Downloads` / `Desktop` / `%TEMP%` / `C:\ego-pkg` 里找。

### 2.2 安装

```powershell
.\install\install_ego.ps1
```

或者明确指定文件：

```powershell
.\install\install_ego.ps1 -Crx "C:\ego-pkg\ego-0.6.1.13-x64.crx3"
```

正常输出结尾是：

```
验证:
ego-browser 0.6.1.13
  chromium 156.0.8078.48
  node v24.22.1
OK 安装完成。
```

**这一步的原理**（出错时用得上）：
crx3 里装的是一个迷你安装器；迷你安装器尾部是 7z 载荷；7z 里才是完整文件树。
脚本依次做三件事：取出文件树 → 铺到 `%LOCALAPPDATA%\Citro Labs\ego lite\Application\<版本>\`
→ 补上安装器本来会做的两个 junction 和一条 PATH。

装完**新开一个终端**，PATH 才会生效。当前窗口执行脚本会提示你加哪一行。

> 若脚本报「已安装，没有覆盖」：说明这台机器上已经有 ego lite。
> 不要加 `-Force`，先跑第 6 步看现有安装能不能用。

---

## 第 3 步：拉仓库

```powershell
git clone https://github.com/F1ameyqq/getaway-to-goal.git
cd getaway-to-goal
```

---

## 第 4 步：填 `config.json`

```powershell
Copy-Item config.example.json config.json
```

然后改这四项，**只能问客户要，不能猜**：

| 字段 | 从哪来 |
|---|---|
| `platform.fileId` | 客户说哪本书；平台地址栏或页面里能看到 |
| `platform.dirNode` | 左侧目录树里要点的节点**全名**，逐字一致 |
| `paths.srcDir` | 扫描图放哪，默认 `srcpages` |
| `paths.egoExe` | 留空即可（第 2 步已经进了 PATH） |

`config.json` 不入库。

---

## 第 5 步：`[等人]` 登录 + 过证书

这两件事 agent 做不了，必须人说清楚再等：

1. **让客户打开 ego lite**（开始菜单里找 `ego lite`）
2. **让客户访问** `https://qt.lingshubao.cn/qieti/annotateUnified`
3. **让客户登录**（token 存在浏览器 localStorage，不随仓库走）
4. **平台证书过期**，浏览器会警告 —— 让客户点「继续前往」

做完之后**不要自己重试**。先跑第 6 步，看它怎么说。

> 如果第 6 步报 `not found: 选择书籍`：多半是登录或页面没加载完。
> **停下来问客户**，不要反复重试，也不要自己去点登录页。

---

## 第 6 步：环境自检

页码用客户那本书的真实页，默认 33/175 只是示例：

```powershell
$env:CHECK_QPAGE="1"; $env:CHECK_APAGE="1"
.\run_ego.ps1 -Js .\check_env.mjs -Out "$env:TEMP\check.txt" -TimeoutSec 240
```

它依次验证：ego 能连上 → 登录态有效 → 能选到书 → 能选到目录 → 能翻页 → 当前页无残留框。**全程只读，不画框不提交。**

成功输出：

```
CHECK_ENV_OK {"counts":["0","0","0"],"cur":"…","pages":["1","1"]}
```

失败时会直接给出对照：

| 报错 | 含义 | 谁来解决 |
|---|---|---|
| `not found: 选择书籍` | 登录失效或页面没加载 | 客户重新登录 |
| `no 选择 button` | `fileId` 不对 | 问客户 |
| `目录节点未找到` | `dirNode` 与目录树文字不一致 | 问客户 |
| `翻页失败` | 页码超出这本书的范围 | 换页码重试 |
| `重置后仍有残留框` | 该页有未提交的框 | **停下来问**，别自己清 |
| `ego lite closed the connection because ego-browser is running as administrator` | 终端是管理员 | `run_ego.ps1` 会自动降权，重跑一次 |

---

## 第 7 步：报告

只报这三件事：

1. `check_env.mjs` 的原始输出
2. 装的是哪个版本（`ego-browser --version`）
3. 还缺什么（比如客户没给 `fileId`）

**然后停。** 下一阶段（出坐标 → 看图复核 → 提交）要读 `HANDOFF.md`，并且需要新的授权。

---

## 绝对不要做的事

- **提交任何数据到平台**：除非当次明确授权。上一页的授权不延续到这一页。
- **跳过 `overlay.py` 看图**：dry run 通过 ≠ 框是对的，这是本项目最大的返工来源。
- **ego hard stop / 证书弹窗时重试**：这是等人，不是重试。
- **杀正在运行的 ego 进程**：日志是异步缓冲的，杀了就永久丢失。
- **猜 `fileId` / `dirNode`**：宁可停下来问。
- **把 `config.json`、`srcpages/`、`pages/` 提交进 git**：`.gitignore` 已经挡了，别用 `-f` 绕过。

---

## 下一阶段（本次不做）

真正开始录入前，先完整读 `HANDOFF.md`，特别是：

- 第一节：**dry run 通过 ≠ 框是对的**
- 第二节：每页必须走的 8 个检查点
- 第三节：必须停下来问的情形

一页的流程是：抓图 → `guide.py` 出标尺图 → 写 spec → `prepare_page.py`（自检 + 出坐标 + 合成 + 两张 overlay）→ **看图复核** → dry run → 停手报告 → 等授权 → 提交。
