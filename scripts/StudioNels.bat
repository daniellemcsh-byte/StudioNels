@echo off
setlocal EnableExtensions
title StudioNels
cd /d "%~dp0.."

if not exist "backend\.venv\Scripts\uvicorn.exe" (
  echo StudioNels is not set up yet.
  echo.
  echo 1^) Install Python 3.12 from python.org ^(Add to PATH^)
  echo 2^) Install Node LTS from https://nodejs.org/
  echo 3^) Open PowerShell here and run:
  echo    powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
  echo.
  pause
  exit /b 1
)

REM Find npm (desktop shortcuts often miss PATH)
set "NPM="
where npm.cmd >nul 2>&1 && set "NPM=npm.cmd"
if not defined NPM if exist "%ProgramFiles%\nodejs\npm.cmd" set "NPM=%ProgramFiles%\nodejs\npm.cmd"
if not defined NPM if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" set "NPM=%ProgramFiles(x86)%\nodejs\npm.cmd"
if not defined NPM if exist "%LOCALAPPDATA%\Programs\node\npm.cmd" set "NPM=%LOCALAPPDATA%\Programs\node\npm.cmd"
if not defined NPM (
  echo Node.js / npm was not found.
  echo Install Node LTS from https://nodejs.org/
  echo Then close this window and try again.
  echo.
  pause
  exit /b 1
)

if not exist "frontend\node_modules\" (
  echo Installing UI packages ^(first run^)...
  pushd frontend
  call "%NPM%" install
  if errorlevel 1 (
    echo npm install failed.
    popd
    pause
    exit /b 1
  )
  popd
)

echo Starting StudioNels API...
start "StudioNels API" /min "backend\.venv\Scripts\uvicorn.exe" app.main:app --app-dir backend --host 127.0.0.1 --port 8787

timeout /t 2 /nobreak >nul

echo Starting StudioNels UI...
echo Browser will open at http://127.0.0.1:5173
echo Close this window to stop the UI. Then close the minimized API window if needed.
echo.

start "" "http://127.0.0.1:5173"

cd /d "%~dp0..\frontend"
call "%NPM%" run dev -- --host 127.0.0.1 --port 5173

echo.
echo StudioNels UI stopped.
pause
