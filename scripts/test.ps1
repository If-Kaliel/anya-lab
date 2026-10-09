$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
& '.\.venv\Scripts\python.exe' -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Testes do backend falharam." }
Push-Location frontend
try {
    npm test
    if ($LASTEXITCODE -ne 0) { throw "Testes da interface falharam." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Build falhou." }
} finally { Pop-Location }
