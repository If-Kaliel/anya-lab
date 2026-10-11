@echo off
setlocal
chcp 65001 >nul
title ANYALAB - Servidor local
cd /d "%~dp0"

if not exist "scripts\start.ps1" (
  echo [ERRO] Este inicializador precisa estar na pasta raiz do anya-lab.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Ambiente Python nao encontrado.
  echo No PowerShell desta pasta execute:
  echo powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo [ERRO] Frontend ainda nao compilado.
  echo Execute o setup oficial: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
  pause
  exit /b 1
)

rem Se o servidor ja esta respondendo, so abre no navegador, sem iniciar outra instancia.
powershell.exe -NoProfile -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:8000' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -lt 400){exit 0}}catch{};exit 1" >nul 2>&1
if not errorlevel 1 (
  start "" "http://127.0.0.1:8000"
  exit /b 0
)

echo Iniciando Anyalab em http://127.0.0.1:8000
echo Mantenha esta janela aberta. Ctrl+C encerra o servidor.
start "" /min powershell.exe -NoProfile -WindowStyle Hidden -Command "$u='http://127.0.0.1:8000';for($i=0;$i -lt 120;$i++){try{$r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2;if($r.StatusCode -lt 400){Start-Process $u;break}}catch{};Start-Sleep -Seconds 2}"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo [ERRO] O servidor Anyalab terminou com falha. Veja a mensagem acima.
  pause
)
