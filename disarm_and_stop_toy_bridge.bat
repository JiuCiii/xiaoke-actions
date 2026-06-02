@echo off
cd /d "%~dp0"
if not exist ".env" copy ".env.example" ".env" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$path='.env'; $text=Get-Content -Raw $path; if ($text -match '(?m)^TOY_ARMED=') { $text=[regex]::Replace($text, '(?m)^TOY_ARMED=.*$', 'TOY_ARMED=false') } else { $text=$text.TrimEnd()+\"`r`nTOY_ARMED=false`r`n\" }; Set-Content -Path $path -Value $text -NoNewline"

if exist ".logs\toy_bridge.pid" (
  set /p BRIDGE_PID=<".logs\toy_bridge.pid"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %BRIDGE_PID% -Force -ErrorAction SilentlyContinue"
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$targets=Get-CimInstance Win32_Process | Where-Object { ($_.Name -in @('cmd.exe','python.exe')) -and ($_.CommandLine -match 'xiaoke_actions\\.toy_bridge|start_toy_bridge') }; $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Output ('Stopped bridge processes: ' + $targets.Count)"
del ".logs\toy_bridge.pid" 2>nul

echo TOY_ARMED=false
echo Xiaoke Toy Bridge stopped.
pause
