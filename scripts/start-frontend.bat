@echo off
rem Start the SENTINEL-X dashboard on http://127.0.0.1:3010
setlocal
set "ROOT=%~dp0.."
set "PORT=%SENTINEL_WEB_PORT%"
if "%PORT%"=="" set "PORT=3010"
set "API=%NEXT_PUBLIC_API_URL%"
if "%API%"=="" set "API=http://127.0.0.1:8010"
cd /d "%ROOT%\frontend"

if not exist "node_modules" (
  echo [start-frontend] installing dependencies...
  call npm install
)

set "NEXT_PUBLIC_API_URL=%API%"
echo [start-frontend] dashboard on http://127.0.0.1:%PORT% -^> API %API%
call npm run dev -- --port %PORT%
endlocal
