@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute Preparar Anya.cmd primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 scripts\doctor.py
pause
