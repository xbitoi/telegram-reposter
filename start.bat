@echo off
setlocal enableextensions
chcp 65001 >nul

REM -- If launched as the browser watcher, jump straight to that routine --
if /i "%~1"=="--watch-browser" goto watch_browser

title Telegram Reposter - Server
color 0B

echo.
echo  ==================================================
echo    TELEGRAM REPOSTER - Auto-Repost Dashboard
echo  ==================================================
echo.

cd /d "%~dp0"

REM -- Browser choice: Brave first, then the default browser -------------
set "BRAVE=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
if not exist "%BRAVE%" set "BRAVE=%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"
if not exist "%BRAVE%" set "BRAVE=%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"

REM -- Pick the Python interpreter (prefer a local virtualenv) ----------
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

REM -- Install dependencies only when something is actually missing -----
"%PY%" -c "import fastapi, uvicorn, telethon, aiosqlite" >nul 2>nul
if errorlevel 1 (
    echo  [SETUP] Installing dependencies for the first time...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo  [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)
echo  [OK] Dependencies ready.

REM -- Configuration must exist (copy the example on first run) ---------
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        copy /y "backend\.env.example" "backend\.env" >nul
        echo  [NEW] Created backend\.env from the example.
        echo        Open it and fill in your API ID, API Hash and Bot Token.
    ) else (
        echo  [WARN] backend\.env is missing. Create it before starting.
    )
)

REM -- If the port is already taken, just open the dashboard -------------
netstat -ano | findstr /r /c:"LISTENING" | findstr /c:":8000 " >nul 2>nul
if not errorlevel 1 (
    echo  [WARN] Port 8000 is already in use - the dashboard is probably running.
    call :open_browser
    exit /b 0
)

echo  [OK] Starting server on http://localhost:8000
echo.
echo  The dashboard opens in your browser automatically once the server is up.
echo  Press CTRL+C in this window to stop the server.
echo.

REM -- Launch a tiny watcher that opens the browser when port 8000 answers
start "" /b cmd /c ""%~f0" --watch-browser"

REM -- Run the server in this window (foreground) -----------------------
"%PY%" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --log-level info

echo.
echo  Server stopped.
pause
exit /b 0

REM =====================================================================
REM  Watcher mode: poll the port, then open the browser, then exit.
REM =====================================================================
:watch_browser
setlocal enableextensions
set "BRAVE=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
if not exist "%BRAVE%" set "BRAVE=%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"
if not exist "%BRAVE%" set "BRAVE=%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"
set /a tries=0
:wait_loop
set /a tries+=1
netstat -ano | findstr /r /c:"LISTENING" | findstr /c:":8000 " >nul 2>nul
if not errorlevel 1 goto :ready
if %tries% geq 60 goto :ready
ping -n 2 127.0.0.1 >nul 2>nul
goto :wait_loop

:ready
if exist "%BRAVE%" (
    start "" "%BRAVE%" "http://localhost:8000"
) else (
    start "" "http://localhost:8000"
)
endlocal
exit /b 0

:open_browser
if exist "%BRAVE%" (
    start "" "%BRAVE%" "http://localhost:8000"
    echo  [OK] Dashboard opened in Brave.
) else (
    start "" "http://localhost:8000"
    echo  [OK] Dashboard opened in your default browser.
)
exit /b 0
