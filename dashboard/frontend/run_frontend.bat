@echo off
cd /d "%~dp0"

echo [ Installing frontend dependencies... ]
npm install
echo [ Launching Helix dashboard... ]
npm start
pause
