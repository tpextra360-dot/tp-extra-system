@echo off
echo Stopping all services...
taskkill /F /IM cloudflared.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
echo All services stopped successfully!
pause
