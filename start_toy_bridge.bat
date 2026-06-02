@echo off
cd /d "%~dp0"
if not exist ".logs" mkdir ".logs"
..\.svakom-venv\Scripts\python.exe -m xiaoke_actions.toy_bridge --poll-seconds 0.75 --pid-file ".logs\toy_bridge.pid"
pause
