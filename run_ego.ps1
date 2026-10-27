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
Copy-Item -LiteralPath $Js -Destination $dst -Force
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
$lines = @(
  '@echo off',
  'setlocal',
  'set OUT=%~1',
  ('cd /d "' + $dir + '"'),
  ('"' + $ego + '" nodejs -e "await import(' + $q + $imp + $q + ')" > "%OUT%" 2>&1'),
  '>>"%OUT%" echo EXIT=%ERRORLEVEL%',
  'endlocal'
)
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
