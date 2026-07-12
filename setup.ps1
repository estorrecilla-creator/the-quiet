# Instalación automática (una sola vez) para Windows.
# Uso, desde PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "ATENCION: no encuentro ffmpeg instalado."
    Write-Host "  Prueba:  winget install ffmpeg"
    Write-Host "  o descarga desde https://ffmpeg.org y anadelo al PATH."
    Write-Host ""
}

if (-not (Test-Path "venv")) {
    Write-Host "Creando entorno virtual..."
    python -m venv venv
}

Write-Host "Instalando dependencias..."
& .\venv\Scripts\python.exe -m pip install --upgrade pip -q
& .\venv\Scripts\pip.exe install -r requirements.txt -q

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "He creado .env a partir de .env.example."
    Write-Host "Abrelo con el Bloc de notas y pon tu ANTHROPIC_API_KEY antes de generar contenido."
} else {
    Write-Host ".env ya existe, no lo toco."
}

Write-Host ""
Write-Host "Instalacion lista. A partir de ahora, para subir un tema nuevo:"
Write-Host "  1. Copia el audio y la portada a la carpeta input\"
Write-Host "  2. Ejecuta: .\venv\Scripts\python.exe subir_tema.py"
Write-Host "  3. Responde las preguntas y revisa el resultado en output\"
