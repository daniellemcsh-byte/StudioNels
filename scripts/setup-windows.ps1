# StudioNels - one-time setup for Windows (PowerShell)
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host ""
Write-Host "=== StudioNels setup (Windows) ===" -ForegroundColor Cyan
Write-Host "Folder: $Root"
Write-Host ""

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "MISSING: $cmd" -ForegroundColor Red
    Write-Host "  $hint" -ForegroundColor Yellow
    exit 1
  }
  Write-Host "OK  $cmd" -ForegroundColor Green
}

Need "npm" "Install Node 18+ LTS from https://nodejs.org/ then reopen PowerShell."

# Prefer real Python - reject the Microsoft Store stub
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
$py = $null
if ($pyCmd) { $py = $pyCmd.Source }

if (-not $py -or $py -match "WindowsApps\\python\.exe$") {
  $py3 = Get-Command py -ErrorAction SilentlyContinue
  if ($py3) {
    Write-Host "Using Python launcher: py -3" -ForegroundColor Cyan
    $createVenv = { param($path) & py -3 -m venv $path }
    $pyLabel = "py -3"
  } else {
    Write-Host "MISSING: real Python" -ForegroundColor Red
    Write-Host "Windows is using the Store shortcut, not a real install." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1) Download: https://www.python.org/downloads/"
    Write-Host "2) Run installer - tick 'Add python.exe to PATH'"
    Write-Host "3) Settings > Apps > Advanced app settings > App execution aliases"
    Write-Host "   Turn OFF 'python.exe' and 'python3.exe'"
    Write-Host "4) Close PowerShell, open a NEW window, run this script again."
    Write-Host ""
    pause
    exit 1
  }
} else {
  Write-Host "Using Python: $py"
  $createVenv = { param($path) & python -m venv $path }
  $pyLabel = "python"
}

$venv = Join-Path $Root "backend\.venv"
if (Test-Path $venv) {
  Write-Host "Removing broken/old venv..."
  Remove-Item -Recurse -Force $venv
}

Write-Host "Creating Python venv with $pyLabel ..."
& $createVenv $venv

$pip = Join-Path $venv "Scripts\pip.exe"
$venvPy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $pip)) {
  Write-Host "venv failed - pip.exe missing. Install Python from python.org with PATH ticked." -ForegroundColor Red
  pause
  exit 1
}

Write-Host "Installing API packages..."
& $venvPy -m pip install --upgrade pip
& $pip install -r (Join-Path $Root "backend\requirements.txt")

Write-Host "Installing UI packages..."
Push-Location (Join-Path $Root "frontend")
npm install
Pop-Location

Write-Host ""
Write-Host "Setup done." -ForegroundColor Green
Write-Host "Next: run  scripts\run-windows.ps1" -ForegroundColor Cyan
Write-Host "Optional GPU: see docs\AMD_ROCM.md"
Write-Host ""
pause
