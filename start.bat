@echo off
REM Quality Claim System - Dev server launcher
REM Requires: conda env "dl_tf" OR python on PATH

cd /d "%~dp0"

set PYTHON=%USERPROFILE%\anaconda3\envs\dl_tf\python.exe
if not exist "%PYTHON%" set PYTHON=%USERPROFILE%\miniconda3\envs\dl_tf\python.exe
if not exist "%PYTHON%" set PYTHON=python

set HOST=0.0.0.0
set PORT=8000

echo ============================================================
echo   Quality Claim System
echo ============================================================
echo   Python:  %PYTHON%
echo   Local:   http://127.0.0.1:%PORT%
echo   Network IPv4:
ipconfig | findstr /C:"IPv4"
echo.
echo   Login: admin / 1234   (or qa01 / 1234, qa02 / 1234)
echo   Stop:  Ctrl+C in this window
echo ============================================================
echo.

REM -- Open browser after 4s in background --
start "" /min cmd /c "ping -n 5 127.0.0.1 >nul & start http://127.0.0.1:%PORT%"

"%PYTHON%" -m uvicorn backend.main:app --host %HOST% --port %PORT%

echo.
echo [Server stopped. Press any key to close]
pause >nul
