@echo off
chcp 65001 >nul
rem ============================================================
rem  Build QuickScriptStudio.exe
rem  Lives in dev\, so it steps up one level to the project root
rem  and points PyInstaller at dev\QuickScriptStudio.spec.
rem ============================================================
cd /d "%~dp0.."
echo ============================================================
echo  Build QuickScriptStudio.exe
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   Python not found. Please install Python 3.8+.
    pause
    exit /b 1
)

echo [1/3] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo   PyInstaller not found, installing...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo.
        echo   Failed to install PyInstaller. Check your network / proxy.
        pause
        exit /b 1
    )
)

echo [2/3] Building...
python -m PyInstaller --noconfirm --clean "dev\QuickScriptStudio.spec"
if errorlevel 1 (
    echo.
    echo   Build FAILED. See the output above.
    pause
    exit /b 1
)

echo [3/3] Done.
echo.
if exist "QuickScriptStudio.exe" (
    for %%F in ("QuickScriptStudio.exe") do (
        echo   Output: %%F
        echo   Size:   %%~zF bytes
    )
    echo.
    echo   Copy QuickScriptStudio.exe anywhere and run it.
    echo   Runtime data ^(scripts, templates^) is stored next to the exe
    echo   in a data\ folder; if that location is read-only it falls back
    echo   to %%APPDATA%%\QuickScriptStudio.
) else (
    echo   Expected QuickScriptStudio.exe in the project root but it is missing.
)
echo.
pause
