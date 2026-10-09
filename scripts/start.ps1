$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw "Execute scripts\setup.ps1 primeiro." }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw "Compile o frontend: cd frontend; npm run build" }
if (Test-Path -LiteralPath '.env') {
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*)=(.*)$' -and $matches[1] -like 'ANYA_*') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim(), 'Process')
        }
    }
}
Write-Host "Anya: http://127.0.0.1:8000 | Ctrl+C para encerrar"
& '.\.venv\Scripts\python.exe' -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
