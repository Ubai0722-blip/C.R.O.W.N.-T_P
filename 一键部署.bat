@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title C.R.O.W.N. Deployment System

echo.
echo  ============================================
echo   C.R.O.W.N. v0.0.5 Deployment System
echo  ============================================
echo.

:: ===== Step 1: Python =====
echo  [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python not found. Downloading Python 3.11.4...
    curl -L -o _python_installer.exe "https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe" 2>nul
    if not exist _python_installer.exe (
        echo  [ERROR] Download failed. Please install Python 3.11+ manually.
        echo  [INFO]  https://www.python.org/downloads/
        pause
        exit /b 1
    )
    _python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    del _python_installer.exe
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    python --version >nul 2>&1
    if errorlevel 1 (
        echo  [ERROR] Python installation failed.
        pause
        exit /b 1
    )
)
echo  [OK] Python ready.

:: ===== Step 2: Node.js (for NapCat) =====
echo.
echo  [2/6] Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Node.js not found. Downloading Node.js v20...
    curl -L -o _node_installer.msi "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi" 2>nul
    if not exist _node_installer.msi (
        echo  [WARN] Node.js download failed. NapCat may not work.
        echo  [INFO]  Please install Node.js from https://nodejs.org/
    ) else (
        msiexec /i _node_installer.msi /quiet /norestart
        del _node_installer.msi
        set "PATH=%ProgramFiles%\nodejs;%PATH%"
        node --version >nul 2>&1
        if errorlevel 1 (
            echo  [WARN] Node.js installation may need restart.
        ) else (
            echo  [OK] Node.js installed.
        )
    )
) else (
    echo  [OK] Node.js found.
)

:: ===== Step 3: FFmpeg (for TTS) =====
echo.
echo  [3/6] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    if not exist "tools\ffmpeg\ffmpeg.exe" (
        echo  [!] FFmpeg not found. Downloading...
        mkdir tools\ffmpeg 2>nul
        curl -L -o _ffmpeg.zip "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" 2>nul
        if exist _ffmpeg.zip (
            powershell -Command "Expand-Archive -Path '_ffmpeg.zip' -DestinationPath '_ffmpeg_tmp' -Force"
            for /d %%d in (_ffmpeg_tmp\ffmpeg-*) do (
                copy "%%d\bin\ffmpeg.exe" "tools\ffmpeg\" >nul
                copy "%%d\bin\ffprobe.exe" "tools\ffmpeg\" >nul
            )
            rmdir /s /q _ffmpeg_tmp 2>nul
            del _ffmpeg.zip
            echo  [OK] FFmpeg installed.
        ) else (
            echo  [WARN] FFmpeg download failed. TTS features disabled.
        )
    )
)
if exist "tools\ffmpeg\ffmpeg.exe" set "PATH=%~dp0tools\ffmpeg;%PATH%"

:: ===== Step 4: NapCat =====
echo.
echo  [4/6] Checking NapCat...
if exist "NapCat\napcat.bat" (
    echo  [OK] NapCat found.
    goto skip_napcat
)
echo  [!] NapCat not found. Downloading...
curl -L -o _napcat.zip "https://github.com/NapNeko/NapCatQQ/releases/latest/download/NapCat.Win.x64.zip" 2>nul
if not exist _napcat.zip (
    echo  [WARN] NapCat download failed (GitHub may be blocked).
    echo  [INFO] Please download manually from:
    echo  [INFO] https://github.com/NapNeko/NapCatQQ/releases
    echo  [INFO] Extract NapCat folder to: %~dp0NapCat\
    goto skip_napcat
)
mkdir _napcat_tmp 2>nul
powershell -Command "Expand-Archive -Path '_napcat.zip' -DestinationPath '_napcat_tmp' -Force"
if exist "_napcat_tmp\NapCat" (
    move "_napcat_tmp\NapCat" "NapCat" >nul 2>&1
) else (
    move "_napcat_tmp" "NapCat" >nul 2>&1
)
del _napcat.zip
rmdir /s /q _napcat_tmp 2>nul
if exist "NapCat\napcat.bat" (
    echo  [OK] NapCat installed.
) else (
    echo  [WARN] NapCat extraction may have issues.
)

:skip_napcat

:: ===== Step 5: Python venv + dependencies =====
echo.
echo  [5/6] Setting up Python environment...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    echo  [OK] venv created.
) else (
    echo  [OK] venv exists.
)
echo  [i] Installing dependencies (this may take a few minutes)...
venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    echo  [i] Retrying with default mirror...
    venv\Scripts\pip.exe install -r requirements.txt --quiet --disable-pip-version-check 2>nul
)
echo  [OK] Dependencies installed.

:: ===== Step 6: Create directories =====
echo.
echo  [6/6] Creating directories...
for %%d in (data data\voice data\stickers data\profiles data\memory data\life data\backups data\audio_groups data\tone_groups data\scene_groups personas logs) do (
    if not exist "%%d" mkdir "%%d"
)
echo  [OK] Directories ready.

:: ===== Done =====
echo.
echo  ============================================
echo   Deployment Complete!
echo  ============================================
echo.
echo  Next steps:
echo  1. Edit config.yaml with your API Key
echo  2. Run "启动CROWN配置终端.bat" for WebUI setup
echo  3. Run "重启文明（启动聊天ai）.bat" to start
echo  4. Scan QR code in NapCat window to login QQ
echo.
echo  NapCat folder: %~dp0NapCat\
echo  If NapCat was not installed, download from:
echo  https://github.com/NapNeko/NapCatQQ/releases
echo.
pause
exit /b 0
