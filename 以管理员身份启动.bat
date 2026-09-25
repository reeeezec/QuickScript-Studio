@echo off
rem ============================================================
rem  Launch QuickScript Studio as Administrator.  (recommended)
rem
rem  Some target programs run elevated; Windows UIPI then silently
rem  drops simulated input from a lower-privilege process. Running
rem  as Administrator avoids that.
rem
rem  Elevation is handled by Python (dev\run_admin.py): passing a
rem  Chinese path from cmd to powershell mangles it, so powershell
rem  reports "file not found" and the window just flashes.
rem
rem  Keep this file ASCII-only (cmd parses .bat with the OEM code page).
rem ============================================================
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"

if not defined PY (
    echo.
    echo   Python not found.
    echo   Right-click QuickScriptStudio.exe and choose
    echo   "Run as administrator" instead - it needs no Python.
    echo.
    pause
    exit /b 1
)

if not exist "dev\run_admin.py" (
    echo.
    echo   dev\run_admin.py is missing - keep the folder structure intact.
    echo.
    pause
    exit /b 1
)

%PY% "dev\run_admin.py"
if errorlevel 1 pause
exit /b
