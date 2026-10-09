# Protocolo do primeiro experimento

Na versão 0.3, novos experimentos registram uma janela de memória (padrão 60s, API aceita 10–600s). O risco heurístico mantém a validade de 10s. Configurações antigas sem janela preservam sua política original; previsões registradas nunca são recalculadas. Anotações humanas com conhecimento posterior continuam sendo um risco de viés, mesmo respeitando timestamps.

Use um identificador de partida de origem compartilhado entre cortes e reencodificações. A ingestão recusa splits distintos ou sobreposição da mesma origem. O baseline histórico também recusa a origem da partida avaliada como treinamento. Essa proteção depende da identidade declarada, sem identificação visual automática.

A comparação pareada exige a mesma gravação, relatórios atualizados e a mesma versão das anotações. Usa somente os pares `(timestamp,horizon)` comuns aos dois relatórios, verifica as previsões registradas e a cadeia de cada snapshot de relatório, e recalcula métricas nesse subconjunto. Janelas sobrepostas são correlacionadas; uma comparação dentro de uma gravação não oferece evidência de superioridade entre populações de partidas ou contra humanos.

Tarefa: primeira eliminação **visível** no intervalo `(T, T+15]`, perspectiva da equipe do jogador da gravação.

- Eliminação em T já pertence ao passado e não conta como resultado futuro.
- Eliminação exatamente em T+15 está incluída.
- Mesmo primeiro timestamp, ou diferença de até 100ms, em equipes opostas: resultado ambíguo, excluído.
- Eventos simultâneos da mesma equipe: a classe da equipe é preservada.
- Primeiro evento sem equipe identificável ou marcado como não confiável: janela excluída.
- Nenhum evento: `none` apenas se houver uma revisão confiável cobrindo toda a janela.
- Sem revisão completa: excluído, mesmo quando um evento foi anotado.
- Revisões confiáveis adjacentes ou sobrepostas podem cobrir toda a janela; qualquer lacuna impede a avaliação.
- Uma revisão marcada como não confiável sobreposta à janela a exclui, mesmo se houver uma revisão confiável anterior. Corrija ou retire a declaração incorreta para resolver a inconsistência.
- Não inferir equipe pelo nome de herói; registre a perspectiva e confirme HUD/kill feed manualmente.
- As revisões são declarações do anotador de que todas as eliminações visíveis foram registradas. Não provam ausência de eventos ocultos.

Observações de inferência e rótulos de resultado são canais diferentes. Prepare observações usando só evidências observáveis até cada timestamp, depois crie o experimento. Alterações posteriores nas observações não mudam esse snapshot. As anotações de resultado podem ser adicionadas após a execução; o modelo nunca as consulta.

Revisões de anotações são append-only e têm motivo obrigatório. Para usar observações corrigidas, crie outro experimento. Para usar resultados corrigidos, gere outra avaliação. O relatório antigo permanece uma evidência do conjunto de anotações usado naquele momento. O indicador de relatório desatualizado não modifica probabilidades, rótulos ou métricas históricos.

Cada previsão inclui partida, modelo/versão, configuração/seed, instante, horizonte, quadro realmente utilizado, probabilidades, observações, confiança, explicação por regras, data UTC e latência. O registro é persistente, append-only e encadeado por SHA-256. A explicação é gerada das evidências usadas, sem LLM.

Accuracy usa a classe com maior probabilidade. Empates usam a ordem fixa `[ally_first, enemy_first, none]`. Brier é a média da soma dos erros quadráticos das três classes, sem divisão adicional por três. Log Loss usa logaritmo natural e limite inferior 1e-15. Matriz: linha real, coluna prevista. Intervalos excluídos não entram no denominador.

Calibração tem cinco bins pela confiança máxima, somente a partir de 30 amostras avaliadas. Esse limiar habilita a visualização, não comprova significância. Sobreposição de janelas torna as amostras dependentes; comparações futuras devem estimar incerteza por partida. Compare baselines na mesma gravação, mesmos instantes, mesmo horizonte e mesmas anotações.

O histórico aprende contagens exclusivamente de partidas `train` distintas, com janelas de 15s a cada 5s revisadas. Registre provenance e hashes; nunca treine em gravações de teste. Checkpoints, dados sintéticos e resultados desse protótipo não justificam afirmações sobre jogadores profissionais.
