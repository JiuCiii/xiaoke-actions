@echo off
cd /d "%~dp0"
if not exist ".logs\toy_bridge.pid" (
  echo toy bridge pid file not found
  pause
  exit /b 0
)
set /p PID=<".logs\toy_bridge.pid"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %PID% -Force -ErrorAction SilentlyContinue"
del ".logs\toy_bridge.pid" 2>nul
echo toy bridge stopped
pause
