# Backup e recuperação local

O banco guarda partidas, anotações, revisões, experimentos, previsões e relatórios. Os vídeos originais ficam em `data/videos`. Antes de experimentar mudanças importantes, crie um backup:

```powershell
.\.venv\Scripts\python.exe scripts/backup.py create --data-dir data --output exports/backup-2026-10-09
```

O destino precisa ser uma pasta nova fora da pasta de dados. A cópia do banco usa o backup online do SQLite, incluindo transações já confirmadas no WAL. Pode ser feita com Anya aberta. Os vídeos são copiados a partir da lista no snapshot e conferidos contra seus hashes registrados. Um manifesto registra tamanho e SHA-256 de cada arquivo. Reserve espaço para outra cópia dos vídeos.

O escopo é **banco e gravações originais**. Guarde separadamente os artefatos de treinamento em `data/models`, a configuração `.env` e as exportações que quiser preservar. As prévias de reprodução podem ser regeneradas. Nada é enviado ao GitHub pelo backup; `exports` permanece ignorada pelo Git. A pasta de backup contém seus dados locais: escolha conscientemente onde guardar uma cópia externa.

## Restaurar sem substituir dados

```powershell
.\.venv\Scripts\python.exe scripts/backup.py restore --backup exports/backup-2026-10-09 --target data-restored
```

O destino deve ser uma pasta nova. A restauração verifica o manifesto, os hashes, o banco SQLite e a correspondência dos vídeos antes de publicar a pasta. Não aceita caminhos externos, travessia `..` ou links nos arquivos do manifesto. Backups corrompidos são recusados; dados existentes não são sobrescritos.

Encerre Anya. Para usar a cópia restaurada, configure `ANYA_DATA_DIR=./data-restored` no `.env` e execute **Iniciar Anya.cmd**. Confira as partidas, o histórico e os relatórios. Mantenha a pasta antiga até validar a recuperação.

Bloqueios transitórios de arquivos pelo Windows/OneDrive recebem até cinco tentativas curtas ao publicar a pasta. Se o bloqueio persistir, a operação informa a falha; tente uma pasta local fora da sincronização. Evite compartilhar ou editar simultaneamente o mesmo banco por diferentes computadores via OneDrive: sincronização de arquivos não substitui coordenação do SQLite.

## Verificar o ambiente

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/doctor.py
.\.venv\Scripts\python.exe -X utf8 scripts/doctor.py --json
.\scripts\test.ps1
```

O diagnóstico é somente leitura e não instala ferramentas. Os testes utilizam dados sintéticos próprios e não avaliam gameplay real.

## Dados de voz

O backup existente preserva banco e vídeos. Voz usa a pasta data/voice: feche o serviço e copie a pasta inteira separadamente para preservar áudio, transcrição, manifestos e seleções. Pesos em data/models são opcionais e recuperáveis pelo script de download fixado por commit. Nunca publique essas pastas no Git.
