param(
  [Parameter(Mandatory=$true)][string]$Js,
  [string]$Out = "$env:TEMP\ego_out.txt",
  [int]$TimeoutSec = 300
)
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot

$cfgPath = Join-Path $dir 'config.json'
if (-not (Test-Path $cfgPath)) { throw "缺少 config.json：先复制 config.example.json 为 config.json 并填好" }
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json

$dst = Join-Path $dir '_run.mjs'
# ego-browser 的 node 代码跑在常驻的 task space 里，继承不到调用方 shell 的环境变量
# （2026-10-28 实测：$env:CHECK_QPAGE 在脚本里是 undefined，写进 ego.cmd 也没用）。
# 所以把开关直接写进 _run.mjs 的 prelude；import 会被提升，prelude 仍是第一条语句。
$prelude = ''
foreach ($k in @('RESTORE_TIMING', 'CHECK_QPAGE', 'CHECK_APAGE', 'RUN_PAGE', 'CLEAN_APPLY', 'CLEAN_LO', 'CLEAN_HI')) {
  $v = [Environment]::GetEnvironmentVariable($k)
  if ($v) {
    $esc = $v -replace "'", "''"
    $prelude += "process.env.$k = '$esc';`n"
  }
}
if ($prelude) {
  $src = Get-Content -LiteralPath $Js -Raw -Encoding UTF8
  [System.IO.File]::WriteAllText($dst, $prelude + $src, (New-Object System.Text.UTF8Encoding($false)))
} else {
  Copy-Item -LiteralPath $Js -Destination $dst -Force
}
if (-not (Test-Path $dst)) { throw "copy failed: $Js -> $dst" }
if (Test-Path $Out) { Remove-Item $Out -Force }

# ego 可执行文件：先看 config，再看 PATH
$ego = $cfg.paths.egoExe
if (-not $ego -or -not (Test-Path $ego)) {
  $c = Get-Command ego-browser -ErrorAction SilentlyContinue
  if ($c) { $ego = $c.Source }
}
if (-not $ego -or -not (Test-Path $ego)) {
  throw "找不到 ego-browser。装好 ego lite，或在 config.json 的 paths.egoExe 填绝对路径。"
}

# 生成 ego.cmd。schtasks 的 /TR 里不能出现 / 开头的参数（会被吃掉），所以必须包一层。
# 注意：ego 的 `-e` 会把相对 import 解析到它自己的安装目录，所以必须用绝对 file:/// 路径。
# 这个文件是生成物，不入库。
$cmdPath = Join-Path $dir 'ego.cmd'
$imp = 'file:///' + ($dir -replace '\\', '/') + '/_run.mjs'
$q = "'"
$lines = @('@echo off', 'setlocal', 'set OUT=%~1')
$lines += ('cd /d "' + $dir + '"')
$lines += ('"' + $ego + '" nodejs -e "await import(' + $q + $imp + $q + ')" > "%OUT%" 2>&1')
$lines += '>>"%OUT%" echo EXIT=%ERRORLEVEL%'
$lines += 'endlocal'
Set-Content -LiteralPath $cmdPath -Value $lines -Encoding Default

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
  # 普通权限：直接跑。ego 只在被管理员启动时才拒绝连接，这里根本不需要计划任务。
  & cmd /c "`"$cmdPath`" `"$Out`""
} else {
  # 管理员：ego 会拒绝，借计划任务的 /RL LIMITED 把它降权。
  $tr = $cmdPath + ' ' + $Out
  schtasks /Create /TN "egoTmpRun" /TR $tr /SC ONCE /ST 23:59 /RL LIMITED /F 2>$null | Out-Null
  schtasks /Run /TN "egoTmpRun" 2>$null | Out-Null
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path $Out) {
      $c = Get-Content $Out -Raw -ErrorAction SilentlyContinue
      if ($c -and $c -match 'EXIT=') { break }
    }
    Start-Sleep -Milliseconds 500
  }
  schtasks /Delete /TN "egoTmpRun" /F 2>$null | Out-Null
}

if (Test-Path $Out) { Get-Content $Out -Encoding UTF8 } else { "NO OUTPUT" }
