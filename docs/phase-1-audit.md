# Auditoria do primeiro prompt — 09/10/2026

Referência: Master Engineering Prompt — Phase 1: The Oracle Prototype, recebido em anexo. Base auditada: v0.3.0, commit `32b2348`. A nova diretiva expande essa base; não redefine retroativamente capacidades entregues.

**Confirmação:** o MVP vertical obrigatório da Phase 1 está implementado e foi exercitado: importar gravação, avançar inferência sem acesso ao futuro, preservar previsões, anotar resultados, revelar métricas e consultar/exportar relatório persistente. O próprio prompt manda manter as Phases 2–7 futuras. Os baselines não foram cientificamente validados em gameplay.

| Seção original | Evidência / estado |
| --- | --- |
| 1. Visão | Nome/repo anya-lab, estudo de Marvel Rivals e roadmap preservados; compreensão estratégica continua objetivo de pesquisa. |
| 2. Marca | Arte original aprovada, emblema SVG separado, favicon, paleta e docs/branding.md. O ajuste atual preserva o rosto no banner. |
| 3. Operação | Apenas gravações; nenhuma leitura de cliente, bot, input automatizado, anticheat ou assistência pública. |
| 4. Stack | Python 3.12/FastAPI/OpenCV/FFmpeg/NumPy/SQLite, React/TS/Vite/Recharts e execução CPU com scripts Windows. |
| 5. Arquitetura | Contratos e módulos video/frames/temporal/models/experiments/evaluation/export/storage separados. |
| 6. Experimento | Três classes, horizonte 15s, regras de simultaneidade/ambiguidade/revisão e proveniência da previsão. |
| 7. Blind Replay | Snapshots imutáveis, quadro até cutoff, inferência sem rótulos, hash chain e testes contra vazamento futuro. |
| 8. Modelos | A train-only e B heurístico funcionais. Treino offline C exige dados suficientes; nenhum modelo C registrado no dashboard ou peso fictício. |
| 9. Dataset | Schema versionado, editor sincronizado, histórico, split por origem, rejeição de duplicação/sobreposição. Reencodes dependem de origem declarada. |
| 10. Métricas | Accuracy, matriz, Brier, Log Loss, latência, desconhecidas, N, calibração com N>=30 e comparação pareada. N mínimo não garante validade científica. |
| 11. Interface | Replay, timeline, modelos, experimentos, dataset e resumo. Marca escura/acessível; Anya Presence agora reutilizável. |
| 12. Explicação | Probabilidades, evidências e template separados; nenhum texto altera previsão. Sem LLM inventando fatos. |
| 13. Conteúdo | JSON/CSV/SRT de relatório versionado, erros/acertos e timestamps de registro/revelação. Sem editor completo. |
| 14. Privacidade | Dados locais, origem/host restritos, arquivos/paths validados; nenhum envio de gravação a APIs. |
| 15. Repositório | Estrutura, README/AGENTS/gitignore/env exemplo/CI/docs/scripts; repo público com main/testes. Dados, pesos e segredos fora do Git. |
| 16. Aceite | Exercitado em browser/API com vídeo sintético; docs/phase-1.md explica reprodução. |
| 17. Qualidade | Base: 69 testes backend, 15 UI e build; CI aprovada nas duas branches no commit auditado. Novos testes são separados. |
| 18. Roadmap | Phases 2–7 futuras documentadas, conforme instruído. |
| 19–20. Execução | Decisões, validação e limitações documentadas, código inglês e guias PT-BR. |

## Condições ainda não demonstradas

Não há reconhecimento automático de HUD/heróis/eliminações, dataset real autorizado suficiente, acurácia validada de modelos de gameplay ou comparação com profissionais. A percepção mede pixels e usa observações manuais; semantic_state fica desconhecido. Essas pesquisas não eram condição para concluir o MVP de baselines.

A confirmação refere-se aos requisitos executáveis da Phase 1 com seus limites explícitos. A voz foi pedida apenas como extensão futura no primeiro prompt e ganha implementação real pela Diretiva 002. A auditoria não transforma ambições em capacidades prontas.
