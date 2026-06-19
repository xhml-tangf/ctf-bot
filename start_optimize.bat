@echo off
chcp 65001 >nul
title CTF Optimize (3v3 vs trivial)

REM Kill stale
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'main.py|optimize' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
timeout /t 1 /nobreak >nul

set "CTF_PLAYERS=tang_fuqing,wang_simu,ling_jiayou"
set "CTF_ENEMY=trivial"
set "CTF_MAP=fixed"
set "CTF_SERVER=ws://10.31.0.101:8080"
set "PYTHONUTF8=1"

echo [optimize] 3v3 vs trivial | 25 trials | server=%CTF_SERVER%
python -u "%~dp0optimize.py"
echo.
echo [optimize] done. Press any key to close.
pause >nul
