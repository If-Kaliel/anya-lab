# Decisões técnicas

- Origem explícita de partida e início de cortes: permite impor splits e recusar duplicação temporal mesmo entre arquivos com hashes distintos. A declaração do anotador continua necessária; não há fingerprint visual que comprove a origem.
- Reprodução H.264/AAC como cópia local descartável: resolve suporte do navegador e normaliza o tempo para anotações, sem trocar o arquivo analisado. Conversão é limitada a duas tarefas e 15 minutos por tarefa.
- Memória recente de 60s nos novos experimentos: evita repetir todo o histórico visual em cada previsão. Baselines usam apenas os últimos 10s de risco ou frequências de treino. Configurações legadas e registros persistidos conservam o funcionamento original.
- Comparação pareada e exportação por versão: métricas só são comparáveis quando há controle dos instantes e rótulos. A tabela geral não é um ranking científico; histórico não é substituído por novas revelações.
- Treino offline e geração de features por capability: nenhum rótulo chega ao extrator de features; artefatos joblib permanecem locais e não são carregados por upload no dashboard.
- Backup SQLite online e restauração em destino novo: protege transações confirmadas no WAL e evita sobrescrever dados ao recuperar um snapshot. SHA-256 confere gravações e manifesto, sem substituir assinatura externa.

1. **Python 3.12 e FastAPI**: contratos tipados e testes simples. CPU é suficiente para os baselines; PyTorch foi adiado porque não existe tarefa neural treinada nesta fase.
2. **SQLite**: persistência transacional local, sem infraestrutura distribuída. Contagens, contexto e configuração são congelados por experimento.
3. **FFmpeg e timestamps de apresentação**: respeitar o último frame até T, inclusive vídeos de frame rate variável. A versão 0.2 reutiliza decodificação sequencial com cache limitado; preserva o extrator isolado como referência. Seek por estimativa foi adiado porque pode retornar um frame posterior ao corte.
4. **Percepção manual e regras explícitas**: nenhum modelo fictício ou previsão aleatória. Luminância é uma medida real, mas não possui significado estratégico demonstrado.
5. **Dataset por partida**: split imutável no upload; duplicata binária recusada por hash. Reencodagens/trechos relacionados precisam de controle humano até termos identificação de partidas de origem.
6. **Cadeia de hashes e triggers**: barreiras contra alterações acidentais e auditoria local. Não equivale a timestamp de terceiro nem assinatura resistente a administrador.
7. **React/TypeScript/Vite/Recharts**: gráficos derivados de relatórios reais e interface com estados vazios. Sem dados artificiais nas telas; modo sintético visível quando declarado no upload.
8. **Ilustração e emblema separados**: arte original gerada para apresentação; SVG próprio para tamanhos pequenos. A referência enviada pelo usuário não é copiada para o repositório.
9. **Treinamento supervisionado offline**: pipeline real preparado, sem carregamento de joblib de origem externa pelo servidor nem alegação de modelo validado. Integração de inferência dependerá de dados adequados e versionamento.
10. **Duas branches**: `main` contém o incremento verificável; `testes` começa no mesmo commit, reservada a experimentação. Não foram criadas branches auxiliares.
11. **Revisões append-only**: correção por novas versões, motivo obrigatório, restauração reversível e conflito de edição explícito. Não reescrever registros utilizados por experimentos ou avaliações.
12. **Gráficos sob demanda**: carregar Recharts em bundle separado reduz o download inicial do dashboard sem retirar gráficos ou inventar indicadores.

## Diretiva 002 — 09/10/2026

Qwen3-TTS oficial em ambiente isolado, peso local fixado por commit, SDPA sem FlashAttention obrigatório. VoiceDesign e Base não ficam carregados simultaneamente. Seleção explícita de referência com manifesto; nenhum material do jogo/atriz utilizado. Calls e hipóteses usam snapshots de previsões verificadas; interpretações vêm de templates, sem LLM. Voz lenta não suspende previsões e pode expirar. Implementação completa do primeiro incremento em directive-002.md.
