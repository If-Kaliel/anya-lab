# Human vs Anya — laboratório local

Entrega 0.5: prepare → convite → coleta isolada → respostas imutáveis → revelação → métricas → Prediction Duel e exportações. Não há contas públicas ou infraestrutura multiplayer.

## Executar no Windows

1. Abra **Iniciar Anya.cmd** (porta 8000). Importe uma gravação própria/autorizada de `test` ou `validation`; declare corretamente sua origem e se é sintética. Em Dataset, registre riscos com evidências disponíveis no próprio instante e revise os intervalos de resultado. O pesquisador deve definir a perspectiva aliada/adversária para o participante.
2. Em **Human vs Anya**, escolha gravação, pseudônimo local (32 caracteres hexadecimais), modelo, início, passo e número de rodadas. Todos os cortes precisam de 15 segundos completos restantes. O padrão 0/15s evita sobreposição; passos menores geram amostras correlacionadas.
3. Selecione outras origens `train` revisadas do mesmo modo real/sintético para o baseline histórico opcional. Modelo histórico exige essa seleção. Treino nunca recebe os resultados do estudo. Clique **Preparar estudo e previsões**. A IA é executada progressivamente e suas previsões, evidências e hashes são congelados antes da coleta.
4. **Gerar convite local** e guardar o link. Encerre o servidor de pesquisa com Ctrl+C. Abra **Iniciar Avaliação Humana.cmd**, ou:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-participant.ps1
```

5. Abra o convite em `http://127.0.0.1:8001/#trial=...`, ou cole-o na tela dessa porta. Cada rodada oferece somente quadros de instantes de avaliação já autorizados dentro da memória e as observações do snapshot. Não há vídeo integral, busca por timestamp arbitrário, previsões da IA ou resultados. Distribua 100% entre as três classes ou escolha **Abster-se de prever**. **Bloquear resposta** avança para a próxima rodada. Reabrir o convite retoma a coleta; não redefine o tempo nem permite corrigir respostas anteriores.
6. Após a última resposta, encerre o servidor de participante. Abra Anya normal, selecione o estudo e **Atualizar coleta**. **Revelar comparação** exige todas as respostas bloqueadas. A revisão oferece Human/Anya, métricas e reprodução posterior do duelo.
7. JSON/CSV/SRT exportam a versão de relatório selecionada. SRT separa previsões em T de resultado anotado em T+15. A revisão visual também oculta o resultado até esse horizonte. O vídeo completo fica disponível apenas ao pesquisador após a coleta neste módulo.

Os lançadores carregam `ANYA_*` da mesma `.env`. Os servidores usam uma trava do sistema operacional na pasta de dados e recusam o outro modo nas portas oficiais. Isso impede inicialização simultânea e a exposição acidental das rotas de pesquisa durante coleta. Um processo encerrado libera a trava automaticamente; não apague o arquivo para tentar ignorá-la.

## Contratos e rastreabilidade

`StudyInput`: video_id, participant_id, model_id, training_match_ids, start, step, count, seed, memory_seconds e declaração de gravação inédita. `lab_studies` congela configuração, origem, SHA do vídeo, hashes de previsão/baseline e de PNG autorizado. Preparação interrompida pode deixar um experimento parcial preservado; nenhum estudo utilizável é publicado até a sequência terminar.

`HumanAnswer`: round_index, context_hash e exatamente uma decisão: probabilidades normalizadas ou abstain. O servidor determina T e o índice atual; não aceita avanço arbitrário. `lab_openings` preserva a primeira abertura. `lab_answers` usa transação serializada, timestamps UTC e cadeia SHA-256. UPDATE/DELETE são recusados por triggers. São pseudônimos locais, sem reconhecimento biométrico.

`lab_tokens` guarda apenas SHA-256 de um convite aleatório de 256 bits, associado a um estudo. O token é enviado no cabeçalho Authorization, não na query do servidor. O fragmento do link não aparece em logs HTTP. Trate o convite como acesso àquela coleta; não publique-o. O servidor restrito expõe apenas health, context, frame e answer, além dos assets compilados. Nenhum serviço de voz/modelos é carregado nessa instância.

`lab_reports` preserva cada revelação: respostas, modelos/versões, evidências, hashes, annotation_hash e resultados. Revisar anotações marca o último relatório como desatualizado; revelar novamente cria outra versão. Hashes são auditoria local, não assinaturas resistentes ao administrador da máquina. Backups SQLite existentes incluem essas tabelas; voz/pesos continuam exigindo cópia separada.

## Métricas e limites

Accuracy, Brier multiclasses (soma dos três erros quadráticos), Log Loss (log natural, piso 1e-15), matriz de confusão, N e calibração (a partir de 30 resultados elegíveis) ficam nos relatórios por participante e modelo. Abstenções humanas não são erros artificiais: ficam registradas e são excluídas da comparação pareada. Anya também tem métricas de todas as janelas, identificadas separadamente. Baseline indisponível é `null`, nunca fabricado. Resultados sem revisão completa/confiável são excluídos.

O tempo humano é o intervalo desde a primeira requisição de contexto até a submissão, incluindo renderização e pausas. Latência da IA mede inferência/extração; são operações distintas. Reiniciar ou recarregar não redefine a abertura. A declaração de gravação inédita não prova que o participante nunca viu o arquivo.

Humanos e IA compartilham corte temporal, quadros e evidências, mas têm capacidades semânticas diferentes: o humano interpreta imagens; os baselines atuais usam riscos manuais e estatísticas de pixels. Anya continua sem reconhecimento automático de Marvel Rivals. Não utilizar notas ou riscos produzidos com conhecimento posterior. Somente uma avaliação técnica sintética foi executada nesta entrega; não representa experimento com participantes humanos independentes nem desempenho estratégico real.

O dono da máquina ainda pode ler banco/arquivos ou usar acesso privilegiado. Durante um estudo, não ofereça terminal, filesystem ou acesso de pesquisador ao participante. O protocolo é local, contra avanço por API/interface; não é um sandbox contra o administrador nem infraestrutura para estudo remoto hostil.

## Próxima iteração

Aplicar o protocolo com gravação autorizada inédita, anotações independentes, preregistro de timestamps e participantes consentidos. Em seguida, Anya's Uncertainties deve derivar candidatos de relatórios congelados sem mover teste para treino; contratos/tarefas estão em directive-002.md.
