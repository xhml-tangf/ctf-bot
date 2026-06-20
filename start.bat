@echo off
chcp 65001 >nul
title Minecraft-CTF Bot (3 players)

REM Kill any stale ctf_bot/main python processes (avoid duplicate-login conflict)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'ctf_bot|\\\\main.py' -or $_.CommandLine -match 'main.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
timeout /t 1 /nobreak >nul

REM ====== Match params (edit these) ======
REM Player names (comma-separated, controls all of them)
set "CTF_PLAYERS=tang_fuqing,wang_simu,ling_jiayou"
set "CTF_ENEMY=trivial"
set "CTF_MAP=fixed"
REM Players count is auto = number of names above
REM ==========================================
REM Server address (use ws://127.0.0.1:8080 for local test)
set "CTF_SERVER=ws://10.31.0.101:8080"

set "PYTHONUTF8=1"
echo [start] players=%CTF_PLAYERS% enemy=%CTF_ENEMY% map=%CTF_MAP% server=%CTF_SERVER%
python -u "%~dp0main.py"
echo.
echo [start] bot exited. Press any key to close.
pause >nul
