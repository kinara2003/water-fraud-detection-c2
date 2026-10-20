@echo off
setlocal enabledelayedexpansion

:: ==============================================================================
:: run_live_system.bat
:: NWSDB Water Fraud Platform — Automated Full-System Launcher (Windows)
:: Component 2: Hydraulic Loss Pinpointing & Real-Time Edge Analytics
:: ==============================================================================

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

title NWSDB Water Fraud Platform — Live System Launcher

echo ==============================================================================
echo   NWSDB KADUWELA EAST — WATER FRAUD DETECTION PLATFORM LAUNCHER (WINDOWS)
echo ==============================================================================

:: ------------------------------------------------------------------------------
:: Step 1: Pre-flight cleanup of stale port listeners from prior sessions
:: ------------------------------------------------------------------------------
echo [Pre-Flight] Checking port status...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8000 ^| findstr LISTENING') do (
    if %%a gtr 0 (
        echo  - Reclaiming port 8000 (terminating stale PID %%a)...
        taskkill /F /PID %%a >nul 2>nul
    )
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :5173 ^| findstr LISTENING') do (
    if %%a gtr 0 (
        echo  - Reclaiming port 5173 (terminating stale PID %%a)...
        taskkill /F /PID %%a >nul 2>nul
    )
)

:: ------------------------------------------------------------------------------
:: Step 2: Activate Python Environment
:: ------------------------------------------------------------------------------
echo [1/4] Activating Python virtual environment...
set "PYTHON_CMD=python"
if exist "%PROJECT_ROOT%venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%venv\Scripts\activate.bat"
    set "PYTHON_CMD=%PROJECT_ROOT%venv\Scripts\python.exe"
) else if exist "%PROJECT_ROOT%.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%.venv\Scripts\activate.bat"
    set "PYTHON_CMD=%PROJECT_ROOT%.venv\Scripts\python.exe"
)

:: ------------------------------------------------------------------------------
:: Step 3: Launch FastAPI Backend
:: ------------------------------------------------------------------------------
echo [2/4] Starting FastAPI backend on http://localhost:8000...
start "KADUWELA_BACKEND_PORT_8000" /min cmd /c "cd /d "%PROJECT_ROOT%" && if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat && uvicorn app.main:app --reload --port 8000"

:: ------------------------------------------------------------------------------
:: Step 4: Launch React Frontend
:: ------------------------------------------------------------------------------
echo [3/4] Starting React frontend dev server on http://localhost:5173...
start "KADUWELA_FRONTEND_PORT_5173" /min cmd /c "cd /d "%PROJECT_ROOT%frontend" && npm run dev"

:: ------------------------------------------------------------------------------
:: Step 5: Wait 4 seconds for servers to initialize
:: ------------------------------------------------------------------------------
echo [4/4] Waiting 4 seconds for backend and frontend to initialize...
timeout /t 4 /nobreak >nul 2>nul || ping 127.0.0.1 -n 5 >nul

:: ------------------------------------------------------------------------------
:: Step 6: Open Default Web Browser directly to http://localhost:5173
:: ------------------------------------------------------------------------------
echo Opening default web browser to http://localhost:5173...
start http://localhost:5173

:: ------------------------------------------------------------------------------
:: Step 7: Launch Telemetry Streamer in Automated Demo Mode
:: ------------------------------------------------------------------------------
echo.
echo ==============================================================================
echo  Launching Telemetry Streamer in Automated Mode (--mode auto)
echo  Active URL: http://localhost:8000/api/v1/sensors/telemetry
echo  Controls  : [n] Normal | [f] Bypass J_100 | [r] Refill Surge | [a] Auto | [q] Quit
echo  Press Ctrl+C at any time to shut down all 3 sub-processes simultaneously.
echo ==============================================================================
echo.

"%PYTHON_CMD%" "%PROJECT_ROOT%src\live_streamer.py" --mode auto

:: ------------------------------------------------------------------------------
:: Step 8: Clean Shutdown Handler
:: Terminates FastAPI backend, React frontend, and streamer simultaneously
:: ------------------------------------------------------------------------------
:cleanup
echo.
echo ==============================================================================
echo  [SHUTDOWN] Terminating all sub-processes (Backend, Frontend, Streamer)...
echo ==============================================================================

:: Terminate by assigned window titles
taskkill /F /FI "WINDOWTITLE eq KADUWELA_BACKEND_PORT_8000*" /T >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq KADUWELA_FRONTEND_PORT_5173*" /T >nul 2>nul

:: Terminate any lingering port listeners on 8000 and 5173
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :8000 ^| findstr LISTENING') do (
    if %%a gtr 0 taskkill /F /PID %%a /T >nul 2>nul
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :5173 ^| findstr LISTENING') do (
    if %%a gtr 0 taskkill /F /PID %%a /T >nul 2>nul
)

:: PowerShell fallback sweep for clean socket release
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Get-NetTCPConnection -LocalPort 8000,5173 -ErrorAction SilentlyContinue | Where-Object OwningProcess -gt 0 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>nul

echo [OK] All sub-processes terminated cleanly. Ports 8000 and 5173 released.
exit /b 0
