@echo off
title TP EXTRA SYSTEM - AUTO RUNNER
color 0A

echo ===================================================
echo   Starting All TP Extra Services...
echo ===================================================

start /min "FastAPI Backend" "D:\TP_EXTRA_SYSTEM\backend\.venv\Scripts\python.exe" -m uvicorn main:app --app-dir D:\TP_EXTRA_SYSTEM\backend --port 8000

start /min "Frontend Server" "D:\TP_EXTRA_SYSTEM\backend\.venv\Scripts\python.exe" -m http.server 5500 --directory D:\TP_EXTRA_SYSTEM\frontend

start "Cloudflare Tunnel (Backend)" "D:\TP_EXTRA_SYSTEM\backend\cloudflared.exe" tunnel --url http://127.0.0.1:8000

start "Cloudflare Tunnel (Frontend)" "D:\TP_EXTRA_SYSTEM\backend\cloudflared.exe" tunnel --url http://127.0.0.1:5500

echo All services started!
pause
