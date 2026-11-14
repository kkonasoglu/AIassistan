# Kurulum betiği: sanal ortam + paketler + HTTPS sertifikası.
# Klasörü yeni bir bilgisayara kopyaladıktan sonra bir kez çalıştırın:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Python 3.12 ara (py başlatıcısı veya PATH)
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $python = @("py", "-3.12") }
}
if (-not $python -and (Get-Command python -ErrorAction SilentlyContinue)) { $python = @("python") }
if (-not $python) { throw "Python 3.12 bulunamadi. https://www.python.org/downloads/windows/ adresinden kurun ('Add python.exe to PATH' isaretli olsun)." }

if (-not (Test-Path ".venv")) {
    Write-Host "Sanal ortam olusturuluyor..."
    & $python[0] $python[1..($python.Length)] -m venv .venv
}
Write-Host "Paketler kuruluyor (ilk seferde birkac dakika surer)..."
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

New-Item -ItemType Directory -Force data, data\models | Out-Null
Write-Host "HTTPS sertifikasi hazirlaniyor..."
& .\.venv\Scripts\python.exe -m scripts.make_cert

Write-Host ""
Write-Host "Kurulum tamam. Kontrol listesi:"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "  [!] Ollama kurulu degil: https://ollama.com/download"
} else {
    Write-Host "  - Modelleri indirin:  ollama pull qwen2.5:3b   ve   ollama pull bge-m3"
}
Write-Host "  - Sunucuyu baslatin:  start_server.bat"
Write-Host "  - Diger bilgisayarlarin erismesi icin (YONETICI PowerShell):"
Write-Host '    New-NetFirewallRule -DisplayName "Ofis Asistani" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Private'
