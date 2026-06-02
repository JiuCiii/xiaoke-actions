@echo off
cd /d "%~dp0"
if not exist ".logs" mkdir ".logs"
"%~dp0..\.svakom-venv\Scripts\python.exe" -m xiaoke_actions.toy_bridge --poll-seconds 0.75 --pid-file ".logs\toy_bridge.pid" >> ".logs\toy_bridge.out.log" 2>> ".logs\toy_bridge.err.log"
