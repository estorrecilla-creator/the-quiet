@echo off
cd /d "%~dp0"
venv\Scripts\python.exe tools\configurar_canal_youtube.py
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
