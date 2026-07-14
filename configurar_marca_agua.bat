@echo off
cd /d "%~dp0"
venv\Scripts\python.exe tools\configurar_marca_agua.py
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
