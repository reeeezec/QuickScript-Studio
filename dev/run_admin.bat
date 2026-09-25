@echo off
rem ============================================================
rem  Launch QuickScript Studio as Administrator.
rem  Lives in dev\, so it steps up one level to the project root.
rem  Keep this file ASCII-only.
rem ============================================================
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"

if not defined PY (
    echo.
    echo   Python not found. Please install Python 3.8+.
    echo.
    pause
    exit /b 1
)

%PY% "run_admin.py"
if errorlevel 1 pause
exit /b
