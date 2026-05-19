@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo  ============================================
echo   C.R.O.W.N. // BLACK CROWN
echo   Restart Civilization
echo  ============================================
echo.

:: Use venv Python if available
set "PYTHON=python"
if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"

echo  [1/3] Starting NoneBot...
start "CROWN-Bot" cmd /k "cd /d "%~dp0" && set "PATH=%~dp0tools\ffmpeg;%PATH%" && echo [C.R.O.W.N] NoneBot Starting on :8081... && %PYTHON% qq_bot.py"

echo  [2/3] Waiting for NoneBot...
ping 127.0.0.1 -n 6 >nul

echo  [3/3] Starting NapCat...
start "NapCat" cmd /c "cd /d "%~dp0\NapCat" && napcat.bat"

echo  [INFO] Starting WebUI in background...
start /min "CROWN-WebUI" cmd /c "cd /d "%~dp0" && %PYTHON% prts_config.py"

ping 127.0.0.1 -n 6 >nul

echo.
echo  [OK] All started. Bot=:8081 WebUI=:5050
echo.
ping 127.0.0.1 -n 4 >nul
exit /b 0
