@echo off
cd /d "%~dp0"
venv\Scripts\python.exe tools\arreglar_genero.py %*
echo.
echo Pulsa una tecla para cerrar esta ventana...
pause >nul
