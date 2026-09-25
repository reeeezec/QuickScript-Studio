@echo off
rem ============================================================
rem  Launch QuickScript Studio (normal privileges).
rem  Lives in dev\, so it steps up one level to the project root.
rem  Keep this file ASCII-only.
rem ============================================================
cd /d "%~dp0.."

where pythonw >nul 2>nul && (start "" pythonw -m quickscript & exit /b)

where python >nul 2>nul && (python -m quickscript & exit /b)
where py >nul 2>nul && (py -3 -m quickscript & exit /b)

echo.
echo   Python not found. Install Python 3.8+, or just run
echo   QuickScriptStudio.exe from the project root.
echo.
pause
exit /b 1
