@echo off
rem Ofis Asistani'ni Docker ile baslatir (ilk seferde kurar, modelleri indirir).
rem Gerekli: Docker Desktop acik olmali.
cd /d "%~dp0"
docker version >nul 2>&1
if errorlevel 1 (
  echo Docker calismiyor. Once Docker Desktop'i acin, sonra bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)
docker compose up -d --build
if errorlevel 1 (
  echo Baslatma basarisiz. Ayrinti icin: docker compose logs
  pause
  exit /b 1
)
echo.
echo Hazir olunca su adresten acilir: https://localhost:8443
echo (Ilk kurulumda modeller indirilir; "docker compose logs -f" ile ilerleme izlenir.)
start "" https://localhost:8443
