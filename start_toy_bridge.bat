@echo off
cd /d "%~dp0"
..\.svakom-venv\Scripts\python.exe -m xiaoke_actions.toy_bridge --poll-seconds 0.75
pause
