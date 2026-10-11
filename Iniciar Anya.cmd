@echo off
setlocal
chcp 65001 >nul
title Anya - laboratorio local
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Ambiente Python nao encontrado. Execute "Preparar Anya.cmd" primeiro.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo [ERRO] Dashboard ainda nao compilado. Execute "Preparar Anya.cmd" primeiro.
  pause
  exit /b 1
)

rem Se o laboratorio de pesquisa ja responde, apenas abre o navegador.
powershell.exe -NoProfile -Command "try{$h=Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if($h.mode -eq 'research'){exit 0}}catch{}; exit 1" >nul 2>&1
if not errorlevel 1 (
  start "" "http://127.0.0.1:8000"
  exit /b 0
)

echo Iniciando Anya em http://127.0.0.1:8000
echo Mantenha esta janela aberta. Ctrl+C encerra o servidor.
start "" /min powershell.exe -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++){try{$h=Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if($h.mode -eq 'research'){Start-Process 'http://127.0.0.1:8000';break}}catch{}; Start-Sleep -Seconds 2}"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo [ERRO] O servidor Anya terminou com falha. Veja a mensagem acima.
  pause
)
