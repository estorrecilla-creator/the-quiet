@echo off
cd /d "%~dp0"
venv\Scripts\python.exe tools\procesar_lp.py %*
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
