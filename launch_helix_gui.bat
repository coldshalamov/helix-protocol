@echo off
echo Starting Helix Backend...
start cmd /k "cd /d C:\Users\Robin\helix && uvicorn dashboard.backend.main:app --reload --port 8000"

echo Starting Helix Frontend...
start cmd /k "cd /d C:\Users\Robin\helix\dashboard\frontend && npm start"

exit
