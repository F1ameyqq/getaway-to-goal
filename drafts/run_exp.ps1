param(
  [Parameter(Mandatory=$true)][string]$Js,
  [string]$Out = "$env:TEMP\exp_ab.txt",
  [int]$TimeoutSec = 600
)
$ErrorActionPreference = 'Stop'
$dir = Split-Path $PSScriptRoot -Parent

$cfgPath = Join-Path $dir 'config.json'
if (-not (Test-Path $cfgPath)) { throw "missing config.json at $cfgPath" }
$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json

# unique names so a concurrent production run of run_ego.ps1 is not clobbered
$dst = Join-Path $dir '_exp_run.mjs'
Copy-Item -LiteralPath $Js -Destination $dst -Force
if (-not (Test-Path $dst)) { throw "copy failed: $Js -> $dst" }
if (Test-Path $Out) { Remove-Item $Out -Force }

$ego = $cfg.paths.egoExe
if (-not $ego -or -not (Test-Path $ego)) {
  $c = Get-Command ego-browser -ErrorAction SilentlyContinue
  if ($c) { $ego = $c.Source }
}
if (-not $ego -or -not (Test-Path $ego)) { throw "ego-browser not found" }

$cmdPath = Join-Path $dir 'ego_exp.cmd'
$imp = 'file:///' + ($dir -replace '\\', '/') + '/_exp_run.mjs'
$q = "'"
$lines = @('@echo off', 'setlocal', 'set OUT=%~1')
$lines += ('cd /d "' + $dir + '"')
$lines += ('"' + $ego + '" nodejs -e "await import(' + $q + $imp + $q + ')" > "%OUT%" 2>&1')
$lines += '>>"%OUT%" echo EXIT=%ERRORLEVEL%'
$lines += 'endlocal'
Set-Content -LiteralPath $cmdPath -Value $lines -Encoding Default

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
  & cmd /c "`"$cmdPath`" `"$Out`""
} else {
  $tn = 'egoExpAB'
  $tr = $cmdPath + ' ' + $Out
  schtasks /Create /TN $tn /TR $tr /SC ONCE /ST 23:59 /RL LIMITED /F 2>$null | Out-Null
  schtasks /Run /TN $tn 2>$null | Out-Null
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path $Out) {
      $c = Get-Content $Out -Raw -ErrorAction SilentlyContinue
      if ($c -and $c -match 'EXIT=') { break }
    }
    Start-Sleep -Milliseconds 500
  }
  schtasks /Delete /TN $tn /F 2>$null | Out-Null
}

if (Test-Path $Out) { Get-Content $Out -Encoding UTF8 } else { "NO OUTPUT" }
