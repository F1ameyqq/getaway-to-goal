# 从 ego 的 .crx3 安装包离线安装 ego lite（不跑官方安装器）。
#
# 背景：官方 egoliteSetup.exe 在部分机器上会卡住不返回，所以这里绕开它，
# 直接把安装包里的文件树铺到标准位置，再补上安装器本来会做的三件事：
#   1. 建 junction  ~/.local/share/ego/active_version_dir -> Application/<版本>
#   2. 建 junction  ~/.local/share/ego/ego-skills -> active_version_dir/ego-skills/ego-browser
#   3. 把 active_version_dir 加进用户 PATH
#
# 已在本机验证（2026-10-27）：解包产物与官方安装目录逐文件一致
# （仅少一个安装器自己的 Installer\setup.exe），且解出的 ego-browser.exe 可直接运行。
#
# 用法:
#   .\install_ego.ps1                      # 自动在下载/桌面/临时目录/C:\ego-pkg 里找 ego*.crx3
#   .\install_ego.ps1 -Crx D:\ego-0.6.1.13-x64.crx3
#   .\install_ego.ps1 -Crx ... -Force       # 已装也重装
param(
  [string]$Crx = "",
  [switch]$Force
)
$ErrorActionPreference = 'Stop'

function Find-CrxPackage {
  # 客户通常是「浏览器下载 → 双击/直接放着」，所以先去那些地方找，而不是要求他报路径。
  $dirs = @(
    (Join-Path $env:USERPROFILE 'Downloads'),
    (Join-Path $env:USERPROFILE 'Desktop'),
    (Join-Path $env:USERPROFILE 'OneDrive\Desktop'),
    $env:TEMP,
    'C:\ego-pkg'
  )
  $hits = @()
  foreach ($d in $dirs) {
    if ($d -and (Test-Path $d)) {
      $hits += @(Get-ChildItem $d -Filter 'ego*.crx3' -File -ErrorAction SilentlyContinue)
    }
  }
  return $hits
}

# ---------- 0. 前置检查 ----------
if (-not $Crx) {
  $hits = @(Find-CrxPackage)
  if ($hits.Count -eq 1) {
    $Crx = $hits[0].FullName
    Write-Host "自动找到安装包: $Crx" -ForegroundColor Cyan
  } elseif ($hits.Count -gt 1) {
    Write-Host "找到多个 crx3，请用 -Crx 指定其中一个：" -ForegroundColor Yellow
    $hits | ForEach-Object { Write-Host ("  " + $_.FullName) }
    throw "安装包不唯一"
  } else {
    throw @"
没找到 ego 的 crx3 安装包。

找过这些位置：
  $env:USERPROFILE\Downloads
  $env:USERPROFILE\Desktop
  $env:TEMP
  C:\ego-pkg

两种解决办法（选一种）：
  1. 下载到一个固定位置，然后自动重跑：
       curl.exe -L -o "C:\ego-pkg\ego-0.6.1.13-x64.crx3" "<下载链接>"
  2. 直接告诉脚本文件在哪：
       .\install\install_ego.ps1 -Crx "D:\你放的地方\ego-0.6.1.13-x64.crx3"
"@
  }
}
if (-not (Test-Path $Crx)) { throw "找不到安装包: $Crx" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "需要 python（离线阶段本来就要用）" }
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { throw "需要 Windows 自带的 tar.exe（Win10 1803+ 都有）" }

$appRoot = Join-Path $env:LOCALAPPDATA 'Citro Labs\ego lite\Application'
$shareRoot = Join-Path $env:USERPROFILE '.local\share\ego'
$linkMain = Join-Path $shareRoot 'active_version_dir'
$linkSkills = Join-Path $shareRoot 'ego-skills'

# ---------- 1. 已经装过就别动 ----------
$existing = @()
if (Test-Path $appRoot) {
  # Application\ 下除了版本目录还有 Dictionaries 之类，只认纯版本号
  $existing = @(Get-ChildItem $appRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+' } | ForEach-Object { $_.Name })
}
if ($existing.Count -gt 0 -and -not $Force) {
  Write-Host "已安装的版本: $($existing -join ', ')" -ForegroundColor Yellow
  Write-Host "没有覆盖。确认要重装请加 -Force。" -ForegroundColor Yellow
  $probe = Join-Path $linkMain 'ego-browser.exe'
  if (Test-Path $probe) {
    Write-Host "现有安装自检: " -NoNewline
    # ego-browser 把版本打到 stderr；PS 5.1 里直接 2>&1 会抛 NativeCommandError，所以过一层 cmd
    & cmd /c "`"$probe`" --version 2>&1" | Select-Object -First 1
  } else {
    Write-Host "但 $linkMain 不是一个可用的 junction，需要 -Force 修复。"
  }
  exit 0
}

$tmp = Join-Path $env:TEMP ("ego_install_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $tmp | Out-Null
Write-Host "临时目录: $tmp" -ForegroundColor DarkGray

try {
  # ---------- 2. crx3 -> 7z ----------
  $sevenZ = Join-Path $tmp 'payload.7z'
  Write-Host "[1/5] 从 crx3 取出 7z 载荷 ..."
  & python -I (Join-Path $PSScriptRoot 'extract_crx.py') $Crx $sevenZ
  if ($LASTEXITCODE -ne 0) { throw "extract_crx.py 失败（退出码 $LASTEXITCODE）" }

  # ---------- 3. 7z -> 文件树 ----------
  Write-Host "[2/5] 解压 7z ..."
  $unpacked = Join-Path $tmp 'unpacked'
  New-Item -ItemType Directory -Force $unpacked | Out-Null
  & tar -xf $sevenZ -C $unpacked
  if ($LASTEXITCODE -ne 0) { throw "tar 解压失败（退出码 $LASTEXITCODE）" }

  $binRoot = Join-Path $unpacked 'Chrome-bin'
  if (-not (Test-Path $binRoot)) { throw "解压结果里没有 Chrome-bin 目录，安装包格式可能变了" }
  $srcDir = @(Get-ChildItem $binRoot -Directory)[0].FullName
  $ver = Split-Path $srcDir -Leaf
  Write-Host "      版本 $ver，$((Get-ChildItem $srcDir -Recurse -File).Count) 个文件"

  # ---------- 4. 拷到标准位置 ----------
  Write-Host "[3/5] 复制到 Application\$ver ..."
  $dest = Join-Path $appRoot $ver
  New-Item -ItemType Directory -Force $appRoot | Out-Null
  if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
  # robocopy 比 Copy-Item 快很多，退出码 1 表示「有文件被复制」是正常的
  & robocopy $srcDir $dest /E /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy 失败（退出码 $LASTEXITCODE）" }

  # ---------- 5. 补安装器的 junction ----------
  Write-Host "[4/5] 建 junction ..."
  New-Item -ItemType Directory -Force $shareRoot | Out-Null
  foreach ($pair in @(@($linkMain, $dest), @($linkSkills, (Join-Path $dest 'ego-skills\ego-browser')))) {
    $p = $pair[0]
    if (Test-Path $p) {
      # 只删 junction 本身，不碰它指向的内容
      $it = Get-Item $p -Force
      if ($it.LinkType -eq 'Junction') { [System.IO.Directory]::Delete($p, $false) }
      else { throw "$p 已存在但不是 junction，停手检查" }
    }
    New-Item -ItemType Junction -Path $p -Target $pair[1] | Out-Null
  }

  # ---------- 6. PATH ----------
  Write-Host "[5/5] 写入用户 PATH ..."
  $cur = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not $cur) { $cur = '' }
  # 比完整路径，不比子串 —— 否则换用户/换盘符时会把别人的条目当成自己的
  $hasIt = ($cur -replace '/', '\').ToLower().IndexOf(($linkMain -replace '/', '\').ToLower()) -ge 0
  if (-not $hasIt) {
    $newPath = ($cur.TrimEnd(';') + ';' + $linkMain)
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Write-Host "      已追加: $linkMain"
  } else {
    Write-Host "      已存在，跳过"
  }

  # ---------- 7. 验证 ----------
  Write-Host ""
  Write-Host "验证:" -ForegroundColor Cyan
  $v = & cmd /c "`"$(Join-Path $linkMain 'ego-browser.exe')`" --version 2>&1"
  $v | Select-Object -First 3
  if ($LASTEXITCODE -ne 0) { throw "ego-browser --version 失败，安装不可用" }

  Write-Host ""
  Write-Host "OK 安装完成。新开的终端才会有 PATH；当前 PowerShell 先执行：" -ForegroundColor Green
  Write-Host "  `$env:PATH += `";$linkMain`""
  Write-Host ""
  Write-Host "下一步（这些只有人能做）：" -ForegroundColor Yellow
  Write-Host "  1. 打开 ego lite，登录标注平台"
  Write-Host "  2. 平台证书过期，首次会弹警告 —— 点「继续前往」"
}
finally {
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
