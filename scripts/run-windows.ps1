# StudioNels — start API + UI on Windows
# Run after setup-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$venvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
$uvicorn = Join-Path $Root "backend\.venv\Scripts\uvicorn.exe"

if (-not (Test-Path $uvicorn)) {
  Write-Host "Not set up yet. Run scripts\setup-windows.ps1 first." -ForegroundColor Red
  pause
  exit 1
}

Write-Host "Starting StudioNels API on http://127.0.0.1:8787 ..." -ForegroundColor Cyan
$api = Start-Process -FilePath $uvicorn -ArgumentList @(
  "app.main:app",
  "--app-dir", (Join-Path $Root "backend"),
  "--host", "127.0.0.1",
  "--port", "8787"
) -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 2

Write-Host "Starting UI on http://127.0.0.1:5173 ..." -ForegroundColor Cyan
Write-Host "Open that URL in your browser. Close this window to stop the UI;"
Write-Host "then close the minimized API window if it is still running."
Write-Host ""

try {
  Set-Location (Join-Path $Root "frontend")
  npm run dev -- --host 127.0.0.1 --port 5173
}
finally {
  if ($api -and -not $api.HasExited) {
    Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
  }
}
