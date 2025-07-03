@echo off
cd /d %~dp0

REM Activate Python venv and start backend
if exist venv\Scripts\activate.bat (
    start cmd /k "cd /d %~dp0 && call venv\Scripts\activate.bat && uvicorn dashboard.backend.main:app --reload"
) else (
    echo [!] Python virtual environment not found. Please run setup manually.
)

REM Start frontend
cd dashboard\frontend
if not exist node_modules (
    echo Installing missing Node packages...
    npm install axios react-router-dom
    npm install
)
start cmd /k "cd /d %cd% && npm start"
