param([string]$PythonCommand = "py", [string]$PythonVersion = "-3.12")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw "Instale FFmpeg e FFprobe e adicione-os ao PATH antes de iniciar."
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($PythonCommand -eq "py") { & $PythonCommand $PythonVersion -m venv .venv }
    else { & $PythonCommand -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente Python." }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependências Python." }
& '.\.venv\Scripts\python.exe' -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar Anya." }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar frontend." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar frontend." }
} finally { Pop-Location }
Write-Host "Anya preparada. Execute: .\scripts\start.ps1"
