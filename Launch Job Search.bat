@echo off
setlocal
cd /d "%~dp0"
title Job search app

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

if not exist ".venv\Scripts\python.exe" (
    echo First run: setting up. This takes a minute.
    %PY% -m venv .venv
    if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto failed

echo Starting the job search app at http://127.0.0.1:5050
echo Close this window to stop it.
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5050"
".venv\Scripts\python.exe" app.py
echo.
echo The app stopped. If there is an error above, it explains why.
pause
exit /b

:nopython
echo Python was not found. Install it from python.org and tick the box to add it to PATH, then run this again.
pause
exit /b 1

:failed
echo Setup failed. The message above says why.
pause
exit /b 1
