@echo off
cd /d "%~dp0"
if not exist ".logs\toy_bridge.pid" (
  echo toy bridge pid file not found
  pause
  exit /b 0
)
set /p PID=<".logs\toy_bridge.pid"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-Process -Id %PID% -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id %PID% -Force; Write-Output 'toy bridge process stopped' } else { Write-Output 'toy bridge process was not running' }"
del ".logs\toy_bridge.pid" 2>nul
echo toy bridge pid file cleared
pause
