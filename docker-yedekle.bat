@echo off
rem Veritabani + bilgi bankasi + sertifika yedeklenir (indirilen modeller haric: yeniden indirilir, yedegi kucuk tutar).
rem Yedek: yedek\ofis-data-TARIH.tar.gz   Geri yuklemek icin: docker-geri-yukle.bat yedek\DOSYA.tar.gz
cd /d "%~dp0"
if not exist yedek mkdir yedek
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set T=%%i
docker run --rm -v ofisasistan_ofis-data:/data -v "%cd%\yedek":/yedek alpine tar czf /yedek/ofis-data-%T%.tar.gz --exclude=./models -C /data .
if errorlevel 1 (echo Yedekleme basarisiz. & pause & exit /b 1)
echo Yedek alindi: yedek\ofis-data-%T%.tar.gz
