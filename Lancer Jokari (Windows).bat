@echo off
REM Windows : double-clic pour lancer
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe -u jokari.py %*) else (python -u jokari.py %*)
pause
