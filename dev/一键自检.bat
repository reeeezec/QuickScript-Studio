@echo off
chcp 65001 >nul
rem ============================================================
rem  Run all self-checks.
rem  Lives in dev\, so it steps up one level to the project root.
rem ============================================================
cd /d "%~dp0.."
echo ============================================================
echo  QuickScript Studio - self test
echo ============================================================
echo.

if not exist "tests\run_all.py" (
    echo   tests\run_all.py is missing. Keep the folder structure intact.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo   Python not found. Please install Python 3.8+.
    echo   Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)

python "tests\run_all.py"
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo ============================================================
    echo  All checks passed.
    echo ============================================================
) else if %RC%==2 (
    echo ============================================================
    echo  Passed, but some suites were skipped due to environment
    echo  limits - see the summary above.
    echo ============================================================
) else (
    echo ============================================================
    echo  Some checks FAILED - see the output above.
    echo ============================================================
)
pause
exit /b %RC%
