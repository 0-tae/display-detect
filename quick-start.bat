
@REM Run the remind.py script in a new window.

@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 remind.py
) else (
    python remind.py
)

echo.
echo Press any key to close this window...
pause >nul
