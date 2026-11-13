@echo off
setlocal EnableExtensions
title StudioNels
cd /d "%~dp0.."

REM Put common Node locations on PATH for this window (desktop shortcuts often miss them)
set "PATH=%ProgramFiles%\nodejs;%ProgramFiles(x86)%\nodejs;%LOCALAPPDATA%\Programs\node;%APPDATA%\npm;%PATH%"

if not exist "backend\.venv\Scripts\uvicorn.exe" (
  echo StudioNels is not set up yet.
  echo Run setup first, then try again.
  pause
  exit /b 1
)

set "NPM="
where npm.cmd >nul 2>&1 && for /f "delims=" %%I in ('where npm.cmd') do if not defined NPM set "NPM=%%I"
if not defined NPM if exist "%ProgramFiles%\nodejs\npm.cmd" set "NPM=%ProgramFiles%\nodejs\npm.cmd"
if not defined NPM if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" set "NPM=%ProgramFiles(x86)%\nodejs\npm.cmd"
if not defined NPM if exist "%LOCALAPPDATA%\Programs\node\npm.cmd" set "NPM=%LOCALAPPDATA%\Programs\node\npm.cmd"
if not defined NPM if exist "%LOCALAPPDATA%\Programs\nodejs\npm.cmd" set "NPM=%LOCALAPPDATA%\Programs\nodejs\npm.cmd"

if not defined NPM (
  echo Node.js / npm was not found in this window.
  echo.
  echo In PowerShell run:
  echo   where.exe npm
  echo   where.exe node
  echo Then paste those paths if you need help.
  echo.
  echo Or reinstall Node LTS from https://nodejs.org/ and reboot once.
  pause
  exit /b 1
)

echo Using npm: %NPM%

if not exist "frontend\node_modules\vite\" (
  echo Installing UI packages...
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
echo Browser: http://127.0.0.1:5173
echo Keep this window open while using StudioNels.
echo.

start "" "http://127.0.0.1:5173"

cd /d "%~dp0..\frontend"
call "%NPM%" run dev -- --host 127.0.0.1 --port 5173

echo.
echo StudioNels UI stopped.
pause
