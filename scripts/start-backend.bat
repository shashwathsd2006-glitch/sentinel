@echo off
rem Start the SENTINEL-X backend (FastAPI + SQLite) on http://127.0.0.1:8010
setlocal
set "ROOT=%~dp0.."
set "PORT=%SENTINEL_PORT%"
if "%PORT%"=="" set "PORT=8010"
cd /d "%ROOT%\backend"

if not exist ".venv\Scripts\python.exe" (
  echo [start-backend] creating virtualenv...
  python -m venv .venv
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn, sqlalchemy" >nul 2>nul
if errorlevel 1 (
  echo [start-backend] installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo [start-backend] initializing database...
".venv\Scripts\python.exe" -c "from app.db import init_db; init_db(); print('database ready')"

echo [start-backend] serving on http://127.0.0.1:%PORT%
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
endlocal
