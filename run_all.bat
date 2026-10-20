@echo off
rem ==============================================================================
rem run_all.bat - Windows Launch Script for NWSDB WATERGUARD (Component 2)
rem ==============================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"
title NWSDB WATERGUARD Launch Orchestrator (Component 2)

echo ==============================================================================
echo    NWSDB WATERGUARD (COMPONENT 2) -- SERVICE LAUNCH ORCHESTRATOR
echo ==============================================================================
echo.

rem 1. Verify Virtual Environment
if exist "venv\Scripts\activate.bat" (
    echo [*] Activating Python virtual environment (venv)...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [*] Activating Python virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else (
    echo [ERROR] Virtual environment not found in .\venv or .\.venv!
    echo Please create one using:
    echo   python -m venv venv
    echo   call venv\Scripts\activate.bat
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem 2. Start FastAPI Backend on Port 8000 in Background
echo [*] Starting FastAPI backend on port 8000 in the background...
start "WATERGUARD_FastAPI_Backend" /MIN cmd /c "call venv\Scripts\activate.bat && uvicorn app.main:app --port 8000"

rem Wait 2 seconds for backend initialization
timeout /t 2 /nobreak >nul

rem 3. Navigate to frontend/ and check node_modules
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo [*] node_modules missing in frontend/. Running npm install...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install encountered an error!
        goto cleanup
    )
)

rem 4. Open Default Browser
echo [*] Opening http://localhost:5173 in default browser...
start http://localhost:5173

rem 5. Print Instructions
echo.
echo ==============================================================================
echo  WATERGUARD (Component 2) SERVICES ACTIVE:
echo    - Frontend Dashboard: http://localhost:5173
echo    - FastAPI Swagger UI: http://127.0.0.1:8000/docs
echo    - Telemetry API:      http://127.0.0.1:8000/api/v1/zones
echo.
echo  Press [Ctrl+C] to gracefully stop both frontend and backend services.
echo ==============================================================================
echo.

rem 6. Launch Vite Dev Server on Port 5173 (foreground)
call npm run dev -- --port 5173

rem ==============================================================================
rem 7. Graceful Termination Cleanup
rem ==============================================================================
:cleanup
echo.
echo ==============================================================================
echo  Shutting down WATERGUARD services...
echo ==============================================================================

rem Terminate FastAPI background window
taskkill /FI "WINDOWTITLE eq WATERGUARD_FastAPI_Backend*" /F /T >nul 2>&1

rem Terminate any remaining processes listening on port 8000 (FastAPI)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%p >nul 2>&1
)

rem Terminate any remaining processes listening on port 5173 (Vite)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%p >nul 2>&1
)

echo [*] All services terminated cleanly.
exit /b 0
