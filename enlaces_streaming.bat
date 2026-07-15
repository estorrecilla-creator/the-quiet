@echo off
cd /d "%~dp0"
venv\Scripts\python.exe tools\enlaces_streaming.py
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
