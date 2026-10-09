# Decisões técnicas

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
