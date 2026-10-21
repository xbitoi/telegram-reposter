@echo off
setlocal enableextensions
chcp 65001 >nul
title Telegram Reposter - Install dependencies
color 0E

echo.
echo  ==================================================
echo    TELEGRAM REPOSTER - First-time setup
echo  ==================================================
echo.

cd /d "%~dp0"

REM -- Pick the Python interpreter (create a venv if asked) -------------
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe"  set "PY=venv\Scripts\python.exe"

"%PY%" --version >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    echo          https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  [1/4] Using interpreter:
"%PY%" --version
echo.

REM -- Upgrade pip ------------------------------------------------------
echo  [2/4] Upgrading pip...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo  [WARN] Could not upgrade pip; continuing with the current one.
)
echo.

REM -- Install the runtime requirements ---------------------------------
echo  [3/4] Installing dependencies from requirements.txt...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed.
    echo          Check the messages above, then run this file again.
    pause
    exit /b 1
)
echo.

REM -- Create backend\.env from the example when missing ---------------
echo  [4/4] Checking configuration...
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy /y "backend\.env.example" "backend\.env" >nul
        echo  [NEW] Created backend\.env from the example.
        echo        Open backend\.env and fill in:
        echo          - API_ID and API_HASH   ^(from https://my.telegram.org^)
        echo          - BOT_TOKEN             ^(from @BotFather^)
        echo          - SOURCE_CHANNEL and DESTINATION_CHANNEL
    ) else (
        echo  [WARN] backend\.env.example is missing - create backend\.env by hand.
    )
) else (
    echo  [OK] backend\.env already exists - left untouched.
)

echo.
echo  ==================================================
echo    Setup finished.
echo    Start the dashboard with:  start.bat
echo  ==================================================
echo.
pause
