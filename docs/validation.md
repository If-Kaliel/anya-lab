# Validação da entrega — 9 de outubro de 2026

Ambiente local: Windows, Python 3.12.14, Node 24.14.1 e FFmpeg 9.0.2. Dependências Python congeladas em `requirements.lock` e frontend em `package-lock.json`.

- Backend: `python -m pytest -q` — **24 testes passaram**. Inclui fluxo real com FFmpeg, extração CFR/VFR, MP4/MKV, arquivos inválidos e limites, contratos, timestamps, probabilidades, persistência, hash alterado, triggers, bloqueio de futuro, snapshot congelado, treino separado, métricas e treinamento supervisionado real sobre exemplos sintéticos de teste.
- Interface: `npm test` — **3 testes passaram**: criar/registrar previsão via API, separar anotação de resultado da observação e exibir erros sem dados fictícios.
- Build: `npm run build` — **aprovado**, incluindo checagem TypeScript.
- Dependências frontend: instalação final informou **0 vulnerabilidades** no audit.
- Navegador: conferência visual, upload de `demo.mp4` com marcação sintética, criação de experimento, sequência de quatro previsões e anotações de eliminação. A revisão completa e a conferência de avaliação foram concluídas também pela API local.
- Servidor: relatório persistente com 4 previsões avaliadas e cadeia de hashes válida. A demonstração sem observações de risco usou `[0.25, 0.25, 0.50]`; com eventos sintéticos aliados/adversários, registrou 0% Accuracy, Brier 0.875 e Log Loss 1.3863. Isso é somente verificação de software e ilustra a limitação do baseline sem evidências.

Aviso da primeira entrega: Starlette sinaliza depreciação do adaptador de testes `httpx` em favor de `httpx2`. O primeiro build sinalizou um bundle de aproximadamente 605 KB (181 KB gzip); esse segundo aviso foi resolvido no incremento abaixo por divisão do módulo de gráficos.

O sandbox do agente restringiu alguns usos de temporários e realpath em OneDrive. Os testes finais e o build foram executados fora dele, sobre a mesma pasta e o mesmo código. Na aplicação, dados continuam locais e não são publicados no GitHub.

A CI está configurada para `main` e `testes`. Resultados de execução remota são independentes dos resultados locais acima. Não houve validação em gravações reais de Marvel Rivals nem comparação com humanos.

## Incremento 0.2 — mesma data

- Backend: **47 testes passaram**. Além dos anteriores, correção/retirada/restauração de anotações, migração de banco legado, conflitos concorrentes, histórico adulterado, relatórios anteriores preservados, compatibilidade com hashes de relatórios legados, previsão concorrente durante avaliação, revisões adjacentes ou incertas, bloqueio de NaN/infinitos e cache futuro, igualdade de pixels CFR/VFR, concorrência de frames, LRU, falhas/timeouts e encerramento de processos.
- Interface: **9 testes passaram**, incluindo contratos de correção/restauração, motivo obrigatório, preservação do rascunho em conflito, foco e Escape do modal, canal de revisão de intervalos e aviso de relatório desatualizado.
- Navegador: correção de uma nota na demonstração sintética e restauração da versão original; histórico exibiu as três versões, com motivos e datas, mantendo timestamp e equipe. Evidência visual local em `exports/anya-revisions-preview.png` (fora do Git).
- Build com TypeScript: aprovado. Bundle inicial **262 KB** (81 KB gzip); gráficos **354 KB** (103 KB gzip), carregados sob demanda. Sem o aviso de chunk acima de 500 KB.
- Benchmark executado em `data/demo.mp4`, vídeo sintético de 30 segundos, cortes 0/5/10/15s: referência 0,213s, incremental 0,146s, **pixels idênticos**, uma inicialização do decoder e 151 frames consumidos pelo Python. Cerca de 31% menos tempo nessa execução; resultado pontual, sem promessa para gravações reais ou outros computadores.

Os novos testes não treinam um modelo estratégico nem validam Marvel Rivals. O modelo continua recebendo apenas observações até T. Resultados adulterados recusam avaliação, enquanto o canal de inferência continua independente dos rótulos; adulteração de observações bloqueia novos snapshots.

## Incremento 0.3 — mesma data

- Backend: **69 testes passaram** na suíte final. Incluem identidade de origem, remux entre splits, sobreposição, limpeza de uploads rejeitados, timestamps não finitos, duração com PTS deslocado e áudio posterior, alinhamento da prévia, range HTTP, fila e falha/retry, histórico de relatórios, exportação escolhida, comparação pareada e snapshot de relatório adulterado, features até T, grupos de origem no treino, memória limitada e política legada, backup/restore e bloqueio transitório Windows.
- Interface: **15 testes passaram**: inclui reprodução compatível, escolha de relatório arquivado, comparação pelos IDs exatos, cobertura de anotação, importação de origem e início de corte, e configuração de início/cadência.
- Build com TypeScript: aprovado. Bundle inicial cerca de **271 KB** (84 KB gzip), mantendo gráficos sob demanda.
- Diagnóstico `scripts/doctor.py --json`: todas as verificações locais aprovadas.
- Backup CLI de banco e gravação atual criado em `exports/backup-v030`, restaurado em `data/verification-v030`, sem substituir a pasta original. Testes também verificaram previsões, hash chain, relatórios e revisão/retirada de anotações após restauração.
- Exportação CLI sintética gerou quatro exemplos de teste, sem observações manuais. Esses dados não satisfazem os requisitos para treino supervisionado e não representam gameplay.
- Navegador: retomar experimento legado, criar nova revelação e selecionar a anterior (links JSON/CSV/SRT com ID correto); importar demonstração train com origem declarada; revisar 0–30s; executar baseline histórico e comparar quatro instantes com o heurístico. Ambos usaram dados sintéticos explicitamente identificados. Predições históricas `[1/7,1/7,5/7]`; Brier 1.265 e Log Loss 1.946 nesta demonstração. O resultado verifica o cálculo e não mede capacidade estratégica.
- Evidência visual local: `exports/anya-phase-one-preview.png`, fora do Git.

Um teste inicial detectou bloqueio transitório ao renomear a pasta de backup no OneDrive. A implementação passou a repetir somente erros Windows de acesso/compartilhamento, com limite de cinco tentativas, mantendo a recusa de destinos existentes. O erro não foi suprimido; há um teste específico para a recuperação desse bloqueio.

## Diretiva 002 / v0.4.0 — 09/10/2026

- Suíte final: `.venv/Scripts/python.exe -m pytest -q --basetemp=data/directive-verification` — **80 passed**, 30,92s. Aviso de depreciação Starlette/httpx herdado da base; nenhum erro de execução.
- Interface: `npm test` — **18 passed** em quatro arquivos. `npm run build` — TypeScript e Vite aprovados; JS inicial 285,74KB (87,60KB gzip), chart carregado separadamente.
- Diagnóstico: doctor --json, todos os checks aprovados. Ambiente opcional de voz: pip check sem conflitos.
- Benchmark real Qwen3-TTS: VoiceDesign 1.7B, seeds 42/43, e Base 0.6B com três frases; `prompt_count=1` nas três sínteses Base. CUDA real detectada; 40,36/20,52s no design, 13,80/12,23/10,01s no Base. Picos alocados pelo PyTorch ~4,04/2,27GiB. Valores, revisões de pesos e limites em voice.md e exports/voice-benchmark.json (local, ignorado pelo Git).
- Browser: rosto visível no banner, painel com duas referências e seleção não automática; amostra seed 42 decodificada em WAV 24kHz, 6s, playback ativo e sem erro. Screenshot local exports/anya-v040-home.png. Isso verifica mídia/interface, não aprova qualidade vocal.
- Dados existentes: 2 experimentos, 3 relatórios preservados; todas as cadeias de previsões válidas. Nenhuma gravação, rótulo, peso ou relatório original alterado pela migração aditiva.
- Novos testes: falha de modelo explícita, identidade persistente/integridade/reuso/cache, histórico após reinício, prioridade crítica e ordem da fila, expiração/cancelamento em replay, playback/exportações Director, futura memória recusada, hipóteses sem probabilidades e avaliação posterior, abstenção, triggers/tamper e perfil Lightweight.
- Correção de operação: um teste revelou lock temporário do Windows/OneDrive durante publicação atômica de JSON. Retry é limitado a cinco tentativas e erros 5/32/33; falhas permanentes continuam explícitas e são testadas. Leituras não recebem JSON parcialmente escrito.
- CPU de Qwen, qualidade PT-BR, calls em gameplay real e superioridade estratégica não foram validados. Human vs Anya, Arena, Uncertainties e KB/drift continuam tarefas futuras detalhadas; não há testes de execução de componentes inexistentes. Tempo real não foi demonstrado; previsões continuam mesmo quando voz é lenta ou indisponível.
- Commits locais na branch testes; este incremento não foi enviado ao remoto. CI remota 0.3 permanece histórica, não é apresentada como validação da 0.4.
