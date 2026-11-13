# Creates a Desktop shortcut that launches StudioNels
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bat = Join-Path $Root "scripts\StudioNels.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "StudioNels.lnk"

if (-not (Test-Path $Bat)) {
  Write-Host "Missing: $Bat" -ForegroundColor Red
  pause
  exit 1
}

$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($ShortcutPath)
$Sc.TargetPath = $Bat
$Sc.WorkingDirectory = $Root
$Sc.WindowStyle = 1
$Sc.Description = "StudioNels local film studio"
$Sc.IconLocation = "shell32.dll,137"
$Sc.Save()

Write-Host ""
Write-Host "Desktop shortcut created:" -ForegroundColor Green
Write-Host "  $ShortcutPath"
Write-Host ""
Write-Host "Double-click StudioNels on your Desktop to open the app."
Write-Host "(Finish Python 3.12 setup first if you have not already.)"
Write-Host ""
pause
