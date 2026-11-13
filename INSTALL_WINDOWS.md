# StudioNels on Windows — what to do

You install on **your** PC. The cloud agent cannot click through Windows for you.

## 0. Once on your PC

1. **Python 3.10+** — https://www.python.org/downloads/  
   On the installer, tick **Add python.exe to PATH**.
2. **Node.js 18+ LTS** — https://nodejs.org/
3. Optional: **ffmpeg** — https://www.gyan.dev/ffmpeg/builds/ (for Stitch preview)

## 1. Get the StudioNels folder

Copy the `local-film-studio` project onto your PC (zip from the agent chat, USB, or clone if you push to GitHub).

Unzip / place it somewhere simple, e.g.:

`C:\Users\YOU\StudioNels\`

## 2. Setup (one time)

1. Open the folder in File Explorer.
2. Go into `scripts`.
3. Right‑click `setup-windows.ps1` → **Run with PowerShell**.

If Windows blocks it:

```powershell
cd C:\Users\YOU\StudioNels
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

## 3. Run every time

Right‑click `scripts\run-windows.ps1` → **Run with PowerShell**  
(or the same Bypass command with `run-windows.ps1`).

Then open: **http://127.0.0.1:5173**

## 4. In the app

1. Finish the first‑run wizard (GPU / frame size).
2. **Start a project** → **Agent** (idea) → **Film night** → **Director**.
3. Upload clips in Director if you already have footage.

## AMD real generation

Preview works without a GPU torch install. For real frames you need a working PyTorch build for your GPU (ROCm on Linux is the main path today; on Windows many people use preview + NLE export, or a CUDA/DirectML torch build if you have one). See `docs/AMD_ROCM.md`.

## If something fails

| Problem | Fix |
|--------|-----|
| `python` not found | Reinstall Python with PATH ticked; reopen PowerShell |
| `npm` not found | Reinstall Node LTS; reopen PowerShell |
| Port in use | Close old StudioNels windows; or change ports in `run-windows.ps1` |
| Blank UI | Confirm API window is running on port 8787 |
