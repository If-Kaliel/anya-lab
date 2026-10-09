# Roadmap

Concluído na versão 0.2: correção/retirada/restauração de anotações com histórico, detecção de relatórios desatualizados e extração incremental com garantia do índice temporal, verificada contra o extrator de referência.

Concluído na versão 0.3: origem e splits por partida, rejeição de cortes sobrepostos, duração normalizada nas novas importações, prévia compatível local, memória limitada nos novos experimentos, consulta/exportação de relatórios anteriores, comparação pareada, geração de exemplos de treinamento e backup/recuperação verificados. Veja a [entrega da Phase 1](phase-1.md).

Antes da Phase 2: medição de desempenho em gravações longas, coleta de partidas autorizadas, protocolo de anotação aplicado por mais de um anotador e experimentos reais. Gravações legadas conservam os metadados e a identidade por arquivo; verificar sua origem faz parte da organização do dataset.

2. **Visual Perception**: dataset anotado de HUD/kill feed, reconhecimento de eventos e equipes, qualidade e incerteza por observação.
3. **Temporal Intelligence**: classificadores de sequências, janelas sem vazamento, validação por partida e registro de modelos treinados.
4. **Strategic Reasoning**: evidências e cenários comparáveis, sem fabricar explicações incompatíveis com a previsão.
5. **Multimodal Anya**: interfaces opcionais para modelos locais, conversa e voz; privacidade explícita quando serviços externos forem escolhidos.
6. **Autonomous Agents**: simuladores próprios e controlados, reinforcement learning e self-play; sem automação de partidas públicas.
7. **Human vs Anya**: experimento preregistrado, comparação cega com participantes autorizados, mesmo contexto temporal e métricas de incerteza.

Essas fases não estão implementadas. Nenhuma afirmação de desempenho humano é sustentada pelo protótipo atual.
