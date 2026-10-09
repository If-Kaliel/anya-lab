# Anya

**Competitive Intelligence Research Lab** · Phase 1 — The Oracle Prototype

Versão **0.3.0**: laboratório da Phase 1 com replay cego, anotações auditáveis, identificação de partidas de origem, reprodução compatível, versões de relatório, comparação pareada, exportação para treinamento e backup verificado. Dados e previsões anteriores são preservados.

![Identidade original de Anya](frontend/public/anya-hero.png)

Anya é um laboratório local para investigar previsões em gravações de jogos competitivos. O primeiro estudo foi definido para Marvel Rivals: prever a **primeira eliminação visível nos próximos 15 segundos**, nas classes `ally_first`, `enemy_first` e `none`.

Este protótipo implementa um fluxo vertical verificável: importar vídeo → anotar evidências → executar replay cego → registrar previsões → anotar resultados → revelar métricas → exportar relatório. **Ainda não reconhece heróis, equipes ou eliminações automaticamente e não foi validado em partidas reais.**

## Iniciar no Windows

Pré-requisitos: Git, **Python 3.12+**, **Node.js 24**, FFmpeg e FFprobe disponíveis no PATH. GPU, Docker e APIs pagas não são necessários.

```powershell
git clone https://github.com/If-Kaliel/anya-lab.git
cd anya-lab
.\scripts\setup.ps1
.\scripts\start.ps1
```

Abra **http://127.0.0.1:8000**. Encerre com `Ctrl+C`. Se o PowerShell bloquear scripts, execute-os com uma política temporária no processo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

O setup prefere `py -3.12`. Para outra instalação:

```powershell
.\scripts\setup.ps1 -PythonCommand 'C:\Python314\python.exe'
```

Na pasta local já preparada, basta executar `start.ps1`. Copie `.env.example` para `.env` se precisar alterar a pasta de dados, o limite de upload ou os executáveis FFmpeg. O script de início carrega apenas variáveis `ANYA_*`; nunca executa o conteúdo do arquivo.

Você também pode usar **Preparar Anya.cmd**, **Iniciar Anya.cmd** e **Verificar Anya.cmd** com dois cliques. Consulte o [guia de uso](docs/user-guide.md) e o [mapa da entrega da Phase 1](docs/phase-1.md).

Para desenvolvimento, use dois terminais:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd frontend
npm run dev
```

Dashboard de desenvolvimento: http://127.0.0.1:5173. Contratos OpenAPI: http://127.0.0.1:8000/docs.

## Primeiro experimento

1. Clique em **Importar gravação** e escolha MP4 ou MKV próprio ou autorizado. Informe a **Partida de origem** e o início do trecho na partida; todos os cortes do mesmo jogo precisam compartilhar a origem e o split. Trechos sobrepostos e mistura entre treino, validação e teste são recusados. O arquivo será validado e armazenado em `data/videos/`. Limites: 2 GB, 6 horas e até 4K. Use **Preparar reprodução compatível** quando solicitado para criar uma cópia MP4 local.
2. Em **Dataset & anotações**, reproduza ou pause o vídeo. Registre riscos aliados/adversários e confiança usando somente evidências visíveis no timestamp. Não use conhecimento posterior. As equipes são relativas à perspectiva do jogador gravado.
3. Volte ao **Replay Workspace**, escolha **Baseline B · Heurístico**, configure início e cadência (padrão 0s / 5s) e clique em **Criar experimento**. As observações manuais são congeladas nessa criação. Novos experimentos usam memória recente de 60s; o risco heurístico mantém validade de 10s. Anotações posteriores exigem um novo experimento para influenciar inferência.
4. Clique em **Registrar previsão** para avançar 5 segundos ou em **Executar sequência**. Cada registro cobre os próximos 15 segundos. O workspace cego exibe somente quadros autorizados. A sequência termina quando não há horizonte completo; pode ser interrompida após a previsão em processamento.
5. Em **Dataset & anotações**, anote **todas** as eliminações visíveis e confirme a revisão de cada intervalo completo. Uma janela sem eliminação só recebe `none` se o intervalo completo tiver revisão confiável. Resultados desconhecidos, pouco confiáveis e simultaneidade entre equipes são excluídos da avaliação.
6. Retome o experimento salvo e clique em **Revelar & avaliar**. Consulte Accuracy, Brier, Log Loss, matriz de confusão, latência e observações desconhecidas. Escolha a **Versão do relatório** e exporte JSON, CSV ou SRT daquela versão. A revelação produz outra revisão do relatório, preservando a previsão original. Em **Modelos & comparação**, a comparação pareada usa somente os mesmos instantes e horizontes na mesma gravação.

**Regra temporal:** o intervalo de resultado é `(T, T+15]`. Eventos de equipes opostas com diferença de até 100 ms são considerados simultâneos e excluídos. Leia [o protocolo](docs/experiment-protocol.md).

## Corrigir anotações

Em **Dataset & anotações → Registros do dataset**, clique em **Corrigir**, ajuste os campos e informe o motivo. O registro original permanece no **Histórico**. **Retirar** remove a anotação apenas da versão atual do dataset; **Restaurar** copia uma versão anterior para uma nova revisão. Não existe exclusão permanente por esses controles.

Correções de observações entram somente em **novos experimentos**. Experimentos já criados mantêm seu snapshot de inferência. Correções de eliminações ou intervalos marcam o relatório como desatualizado; use **Revelar & avaliar** novamente. Os relatórios anteriores continuam persistidos, e `GET /api/experiments/{id}/reports` permite consultá-los. Duas edições concorrentes não se sobrepõem silenciosamente: a segunda recebe um conflito e precisa carregar o histórico atual.

A exportação de dataset agora usa schema **1.1**, com valores atuais e histórico completo. Revisões têm motivo, timestamp UTC e hashes encadeados. As tabelas originais e o histórico recusam UPDATE/DELETE. Isso protege a auditoria local, mas não substitui assinaturas externas.

## Demonstração técnica determinística

Não acompanha vídeo de terceiros nem dataset privado. Gere uma gravação sintética local:

```powershell
.\.venv\Scripts\python.exe scripts/make_demo.py
```

Importe `data/demo.mp4` e marque **Gravação sintética para demonstração técnica**. Para verificar o fluxo, registre eliminações fictícias em 8s (aliado) e 22s (adversário) e revisão de 0 a 30s. São anotações de teste deliberadas; o vídeo contém formas e texto de demonstração, não gameplay. A sequência produz quatro previsões em 0, 5, 10 e 15s. Essa demonstração testa o software, **não a capacidade de prever Marvel Rivals**.

## Modelos

| Modelo | Implementação | Limitação |
| --- | --- | --- |
| Baseline B — `heuristic-v1` | Pesos `[1+3×risco_aliado, 1+3×risco_adversário, 2]`, normalizados. Risco multiplicado pela confiança; validade de 10s. | Regra não calibrada. Sem observações de risco: `[0,25; 0,25; 0,50]`. Não é uma estimativa aprendida. |
| Baseline A — `historical-v1` | Frequências em janelas revisadas a cada 5s de outras partidas `train`, com suavização de Laplace. Contagens e hashes congelados no experimento. | Precisa de partidas de treinamento anotadas; não usa o split de teste. |
| Modelo C — offline | Exportação temporal dos dados anotados, padronização e regressão logística em `research/train.py`, seed 42 e validação por partida de origem. | Sem pesos reais e sem integração de inferência no dashboard. Consulte [treinamento](docs/training.md). |

O módulo visual mede luminância e registra o estado semântico como **desconhecido**. A luminância não é usada para inventar risco ou reconhecer eliminações. Modelos recebem apenas contratos imutáveis de observações, sem caminhos de vídeo, conexões de banco ou rótulos de resultado.

## Testes

```powershell
.\scripts\test.ps1
```

A suíte cobre o fluxo real de importação com FFmpeg, MP4/MKV, timestamps, contratos, arquivos inválidos, probabilidades, persistência, hashes, tentativas de acesso ao futuro, snapshots congelados, separação de treinamento, métricas e ações da interface. A CI usa as branches **main** e **testes**. Veja [o registro de validação](docs/validation.md) para os resultados executados nesta entrega.

## Organização

- `backend/`: contratos, ingestão, percepção básica, memória, modelos, experimentos, métricas e exportação.
- `frontend/`: React, TypeScript, Vite e Recharts, com identidade Gothic Intelligence Laboratory.
- `tests/`: testes de integração e invariantes científicos.
- `research/`: treinamento supervisionado opcional e contratos de pesquisa.
- `scripts/`: setup, execução, teste e geração de demo.
- `docs/`: [arquitetura](docs/architecture.md), [decisões](docs/decisions.md), [dataset](docs/dataset.md), [protocolo](docs/experiment-protocol.md), [marca](docs/branding.md) e [roadmap](docs/roadmap.md).
- `data/` e `exports/`: arquivos locais ignorados pelo Git.
- `assets/branding/`: documentação dos recursos de marca; arquivos servidos em `frontend/public/`.

## Backup e diagnóstico

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/doctor.py
.\.venv\Scripts\python.exe scripts/backup.py create --data-dir data --output exports/backup-01
.\.venv\Scripts\python.exe scripts/backup.py restore --backup exports/backup-01 --target data-restored
```

O backup inclui banco e vídeos originais, verifica os hashes e usa snapshot online do SQLite. A restauração exige uma pasta nova. Veja [recuperação](docs/operations.md) para configurar `ANYA_DATA_DIR` e proteger os artefatos de treinamento separadamente.

## Limitações e próximas prioridades

Percepção semântica manual, ausência de dataset real e modelos não validados. A extração usa um decodificador contínuo por vídeo, com até duas sessões e cache LRU de 64 quadros solicitados. Avanços sequenciais reutilizam o trabalho; voltar a um quadro já descartado do cache pode reiniciar a decodificação. Saltos muito longos e a indexação inicial ainda podem exceder os timeouts. A cópia compatível precisa de espaço em disco e pode exigir trechos menores para concluir em 15 minutos.

Para medir os métodos em um vídeo local, execute `.\.venv\Scripts\python.exe scripts/benchmark_frames.py data/demo.mp4`. O script compara os pixels dos quadros e os tempos nessa execução. O resultado não mede inteligência, não garante aceleração em todo vídeo e não avalia hardware de outros usuários.

O isolamento controla as interfaces dos modelos internos confiáveis; **não é sandbox para código Python malicioso**, nem impede um anotador humano de introduzir viés. A cadeia de hashes detecta alterações usuais, mas um administrador com acesso ao banco pode reescrever toda a cadeia; não é assinatura externa. A origem das gravações depende da declaração do pesquisador: renomear o mesmo arquivo é detectado por hash, e uma origem compartilhada impõe o mesmo split, mas o conteúdo reencodificado não é reconhecido automaticamente. Gravações antigas conservam a identidade por arquivo e os metadados temporais de importação.

Não há bots, automação de gameplay, leitura de memória, assistência ao vivo, reconhecimento de HUD, LLM ou serviços externos. Próximas prioridades: reunir gravações autorizadas, avaliar desempenho em vídeos longos e construir percepção de eventos baseada em dataset anotado, antes de qualquer comparação com humanos.
