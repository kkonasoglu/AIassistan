@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Once setup.ps1 calistirilmali: powershell -ExecutionPolicy Bypass -File setup.ps1
  pause
  exit /b 1
)
.venv\Scripts\python.exe run.py
pause
