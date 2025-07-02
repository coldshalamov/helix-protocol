@echo off
set PYTHONPATH=%CD%

echo [ Helix Backend Launching... ]
start cmd /k "cd /d %CD% && uvicorn dashboard.backend.main:app --reload || %APPDATA%\Python\Python313\Scripts\uvicorn.exe dashboard.backend.main:app --reload"

echo [ Helix Frontend Launching... ]
start cmd /k "cd /d %CD%\dashboard\frontend && npm install && npm start"

exit
