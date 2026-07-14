@echo off
cd /d "%~dp0"
venv\Scripts\python.exe escalar_video.py
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
