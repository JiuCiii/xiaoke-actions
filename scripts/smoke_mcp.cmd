@echo off
setlocal
pushd "%~dp0.."
python scripts\smoke_mcp.py
popd
endlocal
