@echo off
setlocal
echo Starting Helix Backend...
start cmd /k "cd /d %CD% && uvicorn dashboard.backend.main:app --reload --port 8000"
echo Starting Helix Frontend...
start cmd /k "cd /d %CD%\dashboard\frontend && npm start"
exit
