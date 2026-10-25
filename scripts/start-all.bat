@echo off
rem Start backend and frontend together (Windows).
setlocal
set "ROOT=%~dp0.."

echo [start-all] launching backend on :8010
start "SENTINEL-X backend" cmd /c "%ROOT%\scripts\start-backend.bat"

timeout /t 5 /nobreak >nul
echo [start-all] launching dashboard on :3010
start "SENTINEL-X dashboard" cmd /c "%ROOT%\scripts\start-frontend.bat"

echo [start-all] backend  : http://127.0.0.1:8010/health
echo [start-all] dashboard: http://127.0.0.1:3010
endlocal
