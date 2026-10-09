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
