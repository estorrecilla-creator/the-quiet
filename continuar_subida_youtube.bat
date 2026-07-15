@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
echo ============================================== >> logs\subida_youtube.log
venv\Scripts\python.exe tools\continuar_subida_youtube.py >> logs\subida_youtube.log 2>&1
