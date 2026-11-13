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

Need "python" "Install Python 3.10+ from https://www.python.org/downloads/ and tick Add python.exe to PATH."
Need "npm" "Install Node 18+ LTS from https://nodejs.org/"

$py = (Get-Command python).Source
Write-Host "Using Python: $py"

$venv = Join-Path $Root "backend\.venv"
if (-not (Test-Path $venv)) {
  Write-Host "Creating Python venv..."
  python -m venv $venv
}

$pip = Join-Path $venv "Scripts\pip.exe"

Write-Host "Installing API packages..."
& $pip install --upgrade pip
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
