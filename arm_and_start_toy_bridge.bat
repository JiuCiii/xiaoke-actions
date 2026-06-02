@echo off
cd /d "%~dp0"
if not exist ".logs" mkdir ".logs"
if not exist ".env" copy ".env.example" ".env" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$path='.env'; $text=Get-Content -Raw $path; if ($text -match '(?m)^TOY_ARMED=') { $text=[regex]::Replace($text, '(?m)^TOY_ARMED=.*$', 'TOY_ARMED=true') } else { $text=$text.TrimEnd()+\"`r`nTOY_ARMED=true`r`n\" }; Set-Content -Path $path -Value $text -NoNewline"

if exist ".logs\toy_bridge.pid" (
  set /p BRIDGE_PID=<".logs\toy_bridge.pid"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %BRIDGE_PID% -Force -ErrorAction SilentlyContinue"
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$targets=Get-CimInstance Win32_Process | Where-Object { ($_.Name -in @('cmd.exe','python.exe')) -and ($_.CommandLine -match 'xiaoke_actions\\.toy_bridge|start_toy_bridge') }; $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
del ".logs\toy_bridge.pid" 2>nul

start "Xiaoke Toy Bridge" cmd /k start_toy_bridge.bat
echo TOY_ARMED=true
echo Started Xiaoke Toy Bridge in a new window.
timeout /t 3 >nul
