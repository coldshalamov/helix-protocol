@echo off
setlocal

REM ----------- CONFIGURE PATHS ------------
set PROJECT_DIR=%~dp0
set VENV_DIR=%PROJECT_DIR%venv
set BACKEND_DIR=%PROJECT_DIR%dashboard\backend
set FRONTEND_DIR=%PROJECT_DIR%dashboard\frontend
set REQUIREMENTS_FILE=%PROJECT_DIR%requirements.txt

cd /d "%PROJECT_DIR%"

echo.
echo [Helix GUI Launcher]
echo ----------------------
echo Project Dir: %PROJECT_DIR%
echo.

REM --------- CHECK FOR NODE ------------
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js and npm are not installed or not in PATH.
    echo Download from: https://nodejs.org/en/download
    pause
    exit /b 1
)

REM --------- CHECK FOR VENV ------------
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

REM --------- ACTIVATE VENV & INSTALL BACKEND DEPS --------
echo [INFO] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo [INFO] Installing Python backend dependencies...
pip install --upgrade pip >nul
pip install -r "%REQUIREMENTS_FILE%"

REM --------- INSTALL FRONTEND DEPS -------
echo [INFO] Installing frontend dependencies...
cd /d "%FRONTEND_DIR%"
if not exist node_modules (
    echo [INFO] node_modules not found. Installing...
    npm install axios react-router-dom
    npm install
)

REM --------- START BACKEND --------------
echo [INFO] Launching backend...
cd /d "%PROJECT_DIR%"
start cmd /k "cd /d %PROJECT_DIR% && call %VENV_DIR%\Scripts\activate.bat && uvicorn dashboard.backend.main:app --reload"

REM --------- START FRONTEND -------------
echo [INFO] Launching frontend...
start cmd /k "cd /d %FRONTEND_DIR% && npm start"

REM --------- OPEN BROWSER ----------------
timeout /t 5 >nul
start http://localhost:3000

echo [Helix GUI running...]
exit /b 0
