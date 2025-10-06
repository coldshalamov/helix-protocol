@echo off
setlocal

echo Starting Helix frontend and backend...

:: Resolve paths relative to the repo root (current directory)
set "REPO_DIR=%CD%"
set "FRONTEND_DIR=%REPO_DIR%\dashboard\frontend"
set "VENV_ACTIVATOR=%REPO_DIR%\venv\Scripts\activate.bat"

:: --- Backend ---
if exist "%VENV_ACTIVATOR%" (
  echo Detected virtualenv. Launching backend with venv...
  start cmd /k "cd /d %REPO_DIR% && call venv\Scripts\activate && uvicorn dashboard.backend.main:app --reload --port 8000"
) else (
  echo No virtualenv detected. Launching backend with system Python...
  start cmd /k "cd /d %REPO_DIR% && uvicorn dashboard.backend.main:app --reload --port 8000"
)

:: --- Frontend ---
if exist "%FRONTEND_DIR%" (
  echo Preparing frontend in: %FRONTEND_DIR%
  pushd "%FRONTEND_DIR%"
  if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
  )
  echo Launching frontend...
  start cmd /k "cd /d %FRONTEND_DIR% && npm start"
  popd
) else (
  echo Frontend directory not found: %FRONTEND_DIR%
)

endlocal
