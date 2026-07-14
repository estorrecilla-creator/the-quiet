@echo off
cd /d "%~dp0"
venv\Scripts\python.exe tools\calendario_lp.py
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
