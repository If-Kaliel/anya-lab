# Entrega da Phase 1 — Oracle Prototype

O fluxo vertical da primeira fase está implementado. “Completo” aqui significa um laboratório operacional para experimentos com observações manuais e baselines mensuráveis. As fases de percepção semântica, inteligência temporal treinada e comparação com profissionais dependem de dados e pesquisa futuros.

| Requisito | Implementação disponível |
| --- | --- |
| Execução local Windows, CPU e APIs opcionais | Lançadores CMD, scripts PowerShell, ambiente Python, dashboard compilado, diagnóstico. |
| Identidade original | Emblema SVG, favicon, arte ilustrativa aprovada, paleta e documentação de marca. |
| Importação MP4/MKV e timestamps | Validação real FFmpeg/FFprobe, limites, hash de duplicação e duração a partir dos quadros nas novas importações. |
| Reprodução e anotação | Player, cópia MP4 com tempo zero quando necessária, observações, eliminações, revisão de intervalos e qualidade de cobertura. |
| Dataset por partida | Identificador de origem e início do trecho, mesmo split entre cortes, rejeição de sobreposição, schema e histórico de revisão. |
| Blind Replay | Avanço autorizado, snapshot imutável sem rótulos futuros, memória limitada nos novos experimentos e quadro autorizado. |
| Persistência e auditoria | Previsões e relatórios append-only, hashes encadeados, snapshots congelados, revisão e restauração de anotações. |
| Baseline estatístico | Contagens de janelas revisadas de outras partidas train, suavização e proveniência congelada. |
| Baseline heurístico | Regra implementada sobre risco manual recente e confiança; ausência identificada como desconhecida. |
| Arquitetura supervisionada | Exportação de features temporais e rótulos separados, treino offline real, validação por origem e metadados do modelo. |
| Métricas e comparação | Accuracy, Brier, Log Loss, matriz de confusão, exclusões, latência, desconhecidas, calibração e comparação pareada. |
| Relatórios e conteúdo | Histórico consultável, JSON/CSV/SRT da versão selecionada, tabela de acertos/erros e tempos de registro/revelação. |
| Operação e recuperação | Backup online verificado do banco e dos vídeos, restauração em pasta nova, guia e diagnóstico. |
| Qualidade | Testes de integração com vídeo real sintético, violações de isolamento, dados, interface e CI nas branches main/testes. |

## Aceitação reproduzível

1. Siga o [guia de uso](user-guide.md) para iniciar o laboratório.
2. Gere `data/demo.mp4` com `scripts/make_demo.py`, importe como demonstração sintética e identifique a partida como `demo-01`.
3. Crie um experimento heurístico com início 0s e cadência 5s. Execute quatro previsões em 0/5/10/15s.
4. Anote eliminações fictícias em 8s (aliado) e 22s (adversário), e revise 0–30s. Revele a avaliação.
5. Consulte as métricas e exporte JSON/CSV/SRT. Corrija uma anotação e revele novamente; selecione a revelação anterior para confirmar sua preservação.
6. Crie outro experimento na mesma gravação, revele e faça a comparação pareada. Confira que as janelas usadas são comuns aos dois experimentos.
7. Crie e restaure um backup em outra pasta. Configure a cópia restaurada e confira o histórico.

Esse vídeo contém formas e texto, não gameplay; os eventos anotados são deliberadamente fictícios. O procedimento verifica software e integridade, sem validar capacidade de prever Marvel Rivals. Testes automatizados cobrem esse fluxo com pastas isoladas, sem modificar seus dados de pesquisa.

## Trabalho que depende de pesquisa

Reconhecimento automático de heróis/equipes/HUD, dataset real, pesos treinados em gameplay, validação independente e desempenho contra humanos continuam fora desta primeira fase. O Modelo C não está integrado à inferência do dashboard. Os dados sintéticos não substituem partidas autorizadas ou participantes humanos. O [roadmap](roadmap.md) preserva essa sequência.
