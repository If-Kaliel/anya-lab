# Validação da entrega — 9 de outubro de 2026

Ambiente local: Windows, Python 3.12.14, Node 24.14.1 e FFmpeg 9.0.2. Dependências Python congeladas em `requirements.lock` e frontend em `package-lock.json`.

- Backend: `python -m pytest -q` — **24 testes passaram**. Inclui fluxo real com FFmpeg, extração CFR/VFR, MP4/MKV, arquivos inválidos e limites, contratos, timestamps, probabilidades, persistência, hash alterado, triggers, bloqueio de futuro, snapshot congelado, treino separado, métricas e treinamento supervisionado real sobre exemplos sintéticos de teste.
- Interface: `npm test` — **3 testes passaram**: criar/registrar previsão via API, separar anotação de resultado da observação e exibir erros sem dados fictícios.
- Build: `npm run build` — **aprovado**, incluindo checagem TypeScript.
- Dependências frontend: instalação final informou **0 vulnerabilidades** no audit.
- Navegador: conferência visual, upload de `demo.mp4` com marcação sintética, criação de experimento, sequência de quatro previsões e anotações de eliminação. A revisão completa e a conferência de avaliação foram concluídas também pela API local.
- Servidor: relatório persistente com 4 previsões avaliadas e cadeia de hashes válida. A demonstração sem observações de risco usou `[0.25, 0.25, 0.50]`; com eventos sintéticos aliados/adversários, registrou 0% Accuracy, Brier 0.875 e Log Loss 1.3863. Isso é somente verificação de software e ilustra a limitação do baseline sem evidências.

Avisos restantes: Starlette sinaliza depreciação do adaptador de testes `httpx` em favor de `httpx2`. O build sinaliza um bundle de aproximadamente 605 KB (181 KB gzip); divisão do módulo de gráficos é uma otimização futura. Os avisos não foram suprimidos.

O sandbox do agente restringiu alguns usos de temporários e realpath em OneDrive. Os testes finais e o build foram executados fora dele, sobre a mesma pasta e o mesmo código. Na aplicação, dados continuam locais e não são publicados no GitHub.

A CI está configurada para `main` e `testes`. Resultados de execução remota são independentes dos resultados locais acima. Não houve validação em gravações reais de Marvel Rivals nem comparação com humanos.
