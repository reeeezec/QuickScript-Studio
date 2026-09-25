@echo off
rem ============================================================
rem  Launch QuickScript Studio (normal privileges).
rem
rem  Self-contained: this file sits at the top level and must not
rem  depend on anything inside dev\.
rem
rem  Keep this file ASCII-only. cmd parses .bat files with the OEM
rem  code page, so non-ASCII text can be executed as a bogus command.
rem ============================================================
cd /d "%~dp0"

set "PYW="
where pythonw >nul 2>nul && set "PYW=pythonw"
if not defined PYW where py >nul 2>nul && set "PYW=py -3"

if not defined PYW (
    echo.
    echo   Python not found.
    echo   Double-click QuickScriptStudio.exe instead - it needs no Python.
    echo.
    pause
    exit /b 1
)

start "" %PYW% -m quickscript
exit /b 0
