@echo off
rem Debug launcher: keeps a console open so errors are visible.
rem Lives in dev\, so it steps up one level to the project root.
cd /d "%~dp0.."
echo Running QuickScript Studio in debug mode...
echo.
python -m quickscript
echo.
echo ==== exited, press any key to close ====
pause >nul
