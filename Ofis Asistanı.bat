@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Once kurulum gerekli: powershell -ExecutionPolicy Bypass -File setup.ps1
  pause
  exit /b 1
)

rem Sunucu zaten calisiyorsa tekrar baslatma
netstat -ano | find ":8443" | find "LISTENING" >nul
if not errorlevel 1 goto open

start "Ofis Asistani Sunucusu" /min .venv\Scripts\python.exe run.py

rem Sunucu hazir olana kadar bekle (en fazla ~60 sn)
set /a n=0
:wait
netstat -ano | find ":8443" | find "LISTENING" >nul
if not errorlevel 1 goto open
set /a n+=1
if %n% geq 60 goto open
ping -n 2 127.0.0.1 >nul
goto wait

:open
start "" https://localhost:8443
