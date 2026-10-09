$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.venv-voice/Scripts/python.exe')) { py -3.12 -m venv .venv-voice }
& .venv-voice/Scripts/python.exe -m pip install --upgrade pip
if ($LASTEXITCODE) { throw 'Falha ao preparar pip' }
& .venv-voice/Scripts/python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE) { throw 'Falha ao instalar PyTorch/CUDA' }
& .venv-voice/Scripts/python.exe -m pip install 'qwen-tts==0.1.1'
if ($LASTEXITCODE) { throw 'Falha ao instalar Qwen3-TTS' }
Write-Host 'Pesos não foram baixados. Cerca de 7 GB; reserve 15–20 GB para todo o ambiente.'
Write-Host 'Baixar: .venv-voice/Scripts/python.exe scripts/prepare_voice.py --download'
