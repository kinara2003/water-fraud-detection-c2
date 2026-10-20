@echo off
setlocal enabledelayedexpansion

:: ==============================================================================
:: scripts/backup_and_restore.bat
:: NWSDB Water Fraud Platform Backup & Restore Windows Batch Script
:: Component 2: Application State Preservation & Model Integrity Validation
:: ==============================================================================

set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fi"

if "%~1"=="" (
    goto :usage
)
if "%~1"=="-h" (
    goto :usage
)
if "%~1"=="--help" (
    goto :usage
)

:: Locate Python binary (prefer project virtual environment)
if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_BIN=%PROJECT_ROOT%\venv\Scripts\python.exe"
) else if exist "%PROJECT_ROOT%\venv\bin\python" (
    set "PYTHON_BIN=%PROJECT_ROOT%\venv\bin\python"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_BIN=python"
    ) else (
        echo [ERROR] Python was not found in %PROJECT_ROOT%\venv\Scripts\python.exe or system PATH. >&2
        exit /b 1
    )
)

:: Execute core backup and restore engine
"%PYTHON_BIN%" "%SCRIPT_DIR%backup_and_restore.py" %*
exit /b %errorlevel%

:usage
echo ==============================================================================
echo   NWSDB WATERGUARD -- BACKUP AND RESTORE UTILITY (WINDOWS)
echo ==============================================================================
echo Usage:
echo   scripts\backup_and_restore.bat --backup [--dry-run]
echo   scripts\backup_and_restore.bat --restore ^<tarball^> [--dry-run]
echo.
echo Operations:
echo   --backup              Archive .env, data/, models/*.joblib, and reports/
echo                         into backups\backup_YYYYMMDD_HHMMSS.tar.gz
echo   --restore ^<tarball^>   Verify checksums, validate directory structure, restore state,
echo                         and run automated model pickle signature validations
echo   --dry-run             Perform simulation and validation without modifying target files
echo   --help, -h            Show this help dialog
echo ==============================================================================
exit /b 1
