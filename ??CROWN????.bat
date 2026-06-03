@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
setlocal

echo.
echo  ============================================
echo   C.R.O.W.N. // Configuration Terminal
echo  ============================================
echo.

set "PYTHON="
call :try_python "venv\Scripts\python.exe"
if not defined PYTHON call :try_python "python"
if not defined PYTHON call :try_python "py -3"
if not defined PYTHON call :try_python "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if not defined PYTHON (
    echo  [ERROR] No runnable Python found.
    echo  [HINT] Install Python 3.11+ and add it to PATH, then run: python -m venv venv
    pause
    exit /b 1
)

echo  [INFO] Using Python: %PYTHON%

%PYTHON% -c "import flask, yaml" >nul 2>&1
if errorlevel 1 (
    if exist "data\webui_python" set "PYTHONPATH=%CD%\data\webui_python;%PYTHONPATH%"
    %PYTHON% -c "import flask, yaml" >nul 2>&1
)
if errorlevel 1 (
    echo  [INFO] Installing WebUI dependencies into data\webui_python...
    if not exist "data" mkdir data
    if not exist "data\webui_python" mkdir data\webui_python
    %PYTHON% -m pip install --upgrade --target "data\webui_python" flask pyyaml -q --disable-pip-version-check
    if errorlevel 1 (
        echo  [ERROR] Failed to install Flask/PyYAML for selected Python.
        echo  [HINT] Check your network, then run: %PYTHON% -m pip install --target data\webui_python flask pyyaml
        pause
        exit /b 1
    )
    set "PYTHONPATH=%CD%\data\webui_python;%PYTHONPATH%"
    %PYTHON% -c "import flask, yaml" >nul 2>&1
    if errorlevel 1 (
        echo  [ERROR] WebUI dependencies were installed but still cannot be imported.
        pause
        exit /b 1
    )
)

echo  [INFO] Cleaning old processes...
taskkill /F /FI "WINDOWTITLE eq CROWN*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5050" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
ping 127.0.0.1 -n 2 >nul

if not exist "personas" mkdir personas
if not exist "data" mkdir data
if not exist "data\voice" mkdir data\voice
if not exist "data\stickers" mkdir data\stickers
if not exist "data\profiles" mkdir data\profiles
if not exist "data\memory" mkdir data\memory
if not exist "data\life" mkdir data\life
if not exist "data\backups" mkdir data\backups
if not exist "logs" mkdir logs

echo  [INFO] Starting WebUI on :5050...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%PYTHON%' -ArgumentList 'prts_config.py' -WorkingDirectory '%CD%' -WindowStyle Minimized"

echo  [INFO] Waiting for service...
set /a tries=0
:waitloop
ping 127.0.0.1 -n 2 >nul
set /a tries+=1
%PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/api/stats', timeout=1)" >nul 2>&1
if not errorlevel 1 goto ready
if %tries% geq 20 goto failed
goto waitloop

:failed
echo  [ERROR] WebUI did not answer on http://127.0.0.1:5050
echo  [HINT] Run this command in the project folder to see the error:
echo         %PYTHON% prts_config.py
pause
exit /b 1

:ready
echo  [OK] Opening browser...
start "" "http://127.0.0.1:5050"
echo  [OK] WebUI running on http://127.0.0.1:5050
echo.
ping 127.0.0.1 -n 4 >nul
exit /b 0

:try_python
set "CANDIDATE=%~1"
%CANDIDATE% -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON=%CANDIDATE%"
exit /b 0
