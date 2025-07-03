@echo off
echo Starting Helix frontend and backend...

:: Backend server
start cmd /k "cd /d C:\Users\93rob\OneDrive\Documents\GitHub\helix-protocol && uvicorn dashboard.backend.main:app --reload"

:: Frontend client
cd /d C:\Users\93rob\OneDrive\Documents\GitHub\helix-protocol\dashboard\frontend
echo Installing frontend dependencies...
call npm install
echo Launching frontend...
start cmd /k "npm start"
