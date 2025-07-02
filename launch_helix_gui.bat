@echo off
setlocal

rem Start the backend
start cmd /k "cd /d %CD% && uvicorn dashboard.backend.main:app --reload --port 8000"

rem Start the frontend
start cmd /k "cd /d %CD%\dashboard\frontend && npm start"

endlocal
