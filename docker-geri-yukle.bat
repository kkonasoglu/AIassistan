@echo off
rem Kullanim: docker-geri-yukle.bat yedek\ofis-data-TARIH.tar.gz   (mevcut veriyi DEGISTIRIR)
cd /d "%~dp0"
if "%~1"=="" (echo Kullanim: docker-geri-yukle.bat yedek\DOSYA.tar.gz & exit /b 1)
if not exist "%~1" (echo Dosya yok: %~1 & exit /b 1)
set /p OK="Mevcut veri bu yedekle DEGISTIRILECEK. Devam? (evet/hayir): "
if /i not "%OK%"=="evet" exit /b 1
docker compose stop app
docker run --rm -v ofisasistan_ofis-data:/data -v "%~dp1.":/yedek alpine sh -c "find /data -mindepth 1 -maxdepth 1 ! -name models -exec rm -rf {} + && tar xzf /yedek/%~nx1 -C /data && chown -R 1000:1000 /data"
if errorlevel 1 (echo Geri yukleme BASARISIZ. Verinizi kontrol edin. & docker compose start app & exit /b 1)
docker compose start app
echo Geri yuklendi.
