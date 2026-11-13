@echo off
title StudioNels
cd /d "%~dp0.."

if not exist "backend\.venv\Scripts\uvicorn.exe" (
  echo StudioNels is not set up yet.
  echo.
  echo 1^) Install Python 3.12 from python.org ^(Add to PATH^)
  echo 2^) Open PowerShell in this folder and run:
  echo    powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
  echo.
  pause
  exit /b 1
)

echo Starting StudioNels API...
start "StudioNels API" /min "backend\.venv\Scripts\uvicorn.exe" app.main:app --app-dir backend --host 127.0.0.1 --port 8787

timeout /t 2 /nobreak >nul

echo Starting StudioNels UI...
echo Browser will open at http://127.0.0.1:5173
echo Close this window to stop the UI. Then close the minimized API window if needed.
echo.

start "" "http://127.0.0.1:5173"

cd frontend
call npm.cmd run dev -- --host 127.0.0.1 --port 5173

echo.
echo StudioNels UI stopped.
pause
