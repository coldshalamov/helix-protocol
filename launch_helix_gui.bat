@echo off
echo Starting Helix frontend and backend...

:: Start backend with virtualenv activated
start cmd /k "cd /d C:\Users\93rob\OneDrive\Documents\GitHub\helix-protocol && call venv\Scripts\activate && uvicorn dashboard.backend.main:app --reload"

:: Prepare frontend
cd /d C:\Users\93rob\OneDrive\Documents\GitHub\helix-protocol\dashboard\frontend
echo Installing frontend dependencies...
call npm install
echo Launching frontend...
start cmd /k "npm start"
