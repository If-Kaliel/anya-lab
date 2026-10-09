# Diretiva 002 — incrementos 0.4 e 0.5

## Plano adotado

1. Auditar Phase 1 e corrigir o enquadramento da arte aprovada, mantendo o repositório e os experimentos.
2. Entregar Anya Speaks vertical: runtime Qwen isolado, referências versionadas, seleção explícita, síntese, player e benchmark real.
3. Integrar calls conservadores ao avanço de Blind Replay, com prioridade, proveniência, cancelamento e expiração no tempo do replay.
4. Entregar memória descritiva, hipóteses sem probabilidades inventadas, abstenção e avaliação posterior.
5. Preparar expansão com contratos e tarefas de aceitação; nenhum painel decorativo para componentes inexistentes.

## Situação dos marcos

| Marco | Entrega e limite |
| --- | --- |
| A — Anya Speaks | Backend real Qwen, amostras originais, seleção persistente, clone prompt reutilizado em memória, fila, cache, player, histórico, falhas e benchmark. Amostra 43 aprovada explicitamente pelo usuário e persistida em 09/10/2026. |
| B — Oracle Comms | Fluxo de warnings sobre risco manual recente, com timestamp máximo, evidências, prioridade, silêncio por incerteza/repetição/latência e descarte obsoleto. As categorias observation/warning/prediction/strategic_suggestion/correction fazem parte do contrato, mas este incremento emite apenas warnings e registros de abstenção. Sem percepção semântica automática e sem promessa de tempo real. |
| C — Strategic Intelligence | Memória manual por pseudônimo, frequências e Wilson; hipóteses heurísticas e abstenção preservadas, evidências consultáveis e avaliação após reveal. Métricas de probabilidades continuam no relatório existente por modelo. Sem psicologia ou modelo comportamental treinado. |
| D — Research Expansion | Voice Timeline/Director JSON, CSV e SRT funcionais. Human vs Anya tem coleta local isolada, registros imutáveis, métricas pareadas, baseline independente opcional e Prediction Duel/exportações. Guia: human-lab.md. Uncertainties, KB, drift, highlights e Arena continuam contratos e tarefas futuras. |

O motor numérico existente não mudou. VoiceDesign é uma ferramenta de criação de referência; Base gera as falas cotidianas. O texto do sistema vem de templates explícitos, sem LLM. Ele não modifica probabilidades. Textos escritos pelo usuário são identificados separadamente.

## Contratos da comunicação

Um call contém `id`, `experiment_id`, `model_id/version`, `prediction_model`, `prediction_hash`, `timestamp`, `max_accessible_timestamp`, `expires_at`, `evidence`, `awareness`, `category`, `priority`, `confidence`, `text_origin`, `decision`, `reason`, `latency_ms` e, se submetido, `voice_job_id`. Categorias previstas: observation, warning, prediction, strategic_suggestion, correction. Prioridades: critical/high/normal/low.

`awareness` separa observed/inferred/uncertain/unknown. Neste incremento, inferred fica vazio; não há posição de heróis, habilidades ou intenções reconhecidas. Riscos manuais precisam de confiança >=0,7, valor >=0,6 e idade <=10s. Essas regras são heurísticas não calibradas. Uma urgência crítica vem do produto risco×confiança >=0,85 e substitui mensagens menos prioritárias do mesmo replay. O intervalo ajustável é 5–120s; padrão 10s. Calls expiram em T+5s. O relógio é monotônico e limitado ao frontier do servidor. Cadências acima de 5s podem fazer a fala expirar antes da próxima decisão.

As anotações de eliminações e resultados não são consultadas pelo motor de calls ou hipóteses. O contexto vem da previsão íntegra já registrada. Editar anotações depois não muda essas evidências. Uma hipótese registra sua previsão de origem, critérios confirm/refute e probabilidade nula. Resultados são novos registros separados, associados ao report_id revelado. Abstenção estratégica não remove nem reinterpreta as probabilidades do baseline já registrado.

## Contratos e tarefas futuras executáveis

### D1 — Human vs Anya (implementado em 0.5; extensão futura)

`Trial`: id, video_sha256, source_match_id, split, synthetic, timestamps, horizon, participant_id pseudônimo, AI model/version, context_digest, created_at. `TrialPrediction`: trial_id, T, probabilities ou abstention, decision_started_at/submitted_at, duration_ms, maximum_accessible_timestamp, previous_hash/hash. Duas respostas são seladas antes de qualquer resultado; triggers impedem update/delete. `TrialReport`: annotation snapshot/hash, janela comum, métricas por participante/modelo/baseline, taxa de abstenção e tempo de decisão.

Implementado: servidor dedicado de participante sem rotas de arquivo original, anotações ou relatórios; quadros autorizados até T com hashes; respostas append-only e AI preparada antes da coleta; reveal somente ao encerrar respostas; métricas nas mesmas janelas sem abstenção; duelo posterior com distinção antes/depois. São quadros dos instantes de avaliação anteriores dentro da memória, não um clipe contínuo. Servidores usam exclusão via trava do SO e portas oficiais. Testes cobrem futuro em cache, acesso ao original por Range, token, dupla submissão, contratos, abstenção, splits/origem/modo, tampering e preservação de relatórios. Próximas tarefas: aplicar protocolo real consentido e preregistrado, melhorar contexto contínuo limitado até T e modelar abstenção numérica do baseline explicitamente.

### D2 — Anya's Uncertainties

`ReviewCandidate`: id, experiment_id, prediction_hash, report_id, annotation_hash, source_match_id, split, synthetic, reason, priority, dataset_version. Razões: erro de alta confiança (limiar explícito >=0,8), janela ambígua, divergência entre distribuições (Jensen-Shannon ou distância definida), classe rara. `ReviewResolution`: candidato, nova revisão anotada, autor local, motivo, data. Nunca trocar split ou incorporar teste ao treinamento automaticamente.

Tarefas: extrair de relatórios congelados; deduplicar por previsão/versão; conectar ao editor de anotações; produzir novo manifest de dataset e treinamento com validação independente; registrar rollback para checkpoint anterior. Aceitação: revisão altera a nova versão do dataset e preserva modelo, report e versão antigos.

### D3 — Tactical Knowledge Base e Model Drift

`KnowledgeEntry`: id, entity_type (hero/ability/map/objective/composition/mode/observable_event), nome, conteúdo, source_url ou referência local, published_at, verified_at, balance_version, valid_from/to, revision/hash. Informação sem fonte ou versão explícita fica `unverified`, nunca vira fato tático. Importação exige schema validado e revisão humana. Não haverá scraping automático.

Tarefas: armazenamento append-only; formulário funcional de cadastro e importação de dataset validado; associar versão do jogo a gravações e modelos novos (sem editar registros históricos); relatórios de drift por patch, com N, mix de classes, Brier/Log Loss e intervalos. Mudança de performance não prova causalidade de um patch.

### D4 — Anya Director

Já disponível: exportações da previsão existentes e Voice Timeline. JSON/CSV incluem calls suprimidos e gerados, com estados distintos. SRT inclui somente inícios de reprodução registrados pelo navegador, usando o timestamp do replay; um arquivo sem calls ou sem playback pode ficar vazio.

Tarefas: overlay HTML sobre vídeo gravado, Prediction Reveal com timestamp de registro/reveal, Prediction Duel após D1 e highlights derivados de eventos anotados/erros; legenda sintético/medido obrigatória. Nenhum cliente de jogo, captura ao vivo ou editor de vídeo completo.

### D5 — Simulation Arena

`Environment.reset(seed) -> (Observation, info)`; `step(action) -> (Observation, reward, terminated, truncated, info)`; `Observation` contém apenas informações visíveis da equipe; estado completo fica privado no simulador. `Action`: stay/move_north/south/east/west/attack/interact. `Episode`: seed, environment_version, policy_versions, actions, rewards, terminal_reason e métricas.

Primeira tarefa: grade 8×8, duas equipes de dois agentes, cobertura estática, alcance/visibilidade limitada, objetivo central, energia finita e horizonte máximo. Baselines determinísticos stay/seek_objective/seek_cover. Testar reset reproduzível, ação inválida, terminação, consumo de recursos, ocultação de adversário e avaliação em seeds separados. Depois: coleta de demonstrações para imitation, RL CPU pequeno, self-play e avaliação multi-agent com orçamento antes de GPU. Não há simulador executável nesta versão; seus resultados futuros nunca serão evidência direta sobre Marvel Rivals.

## Limites operacionais

O Resource Coordinator mede GPU via nvidia-smi quando disponível, serializa o runtime de voz, registra latências e picos CUDA e libera o processo sob solicitação. Não arbitra processos externos, driver ou serviços futuros de visão/LLM. Research prioriza geração offline; Replay Commentary usa os calls com expiração; Lightweight libera o modelo após cada geração. Os dois primeiros preservam o modelo em memória. Só um modelo de voz fica carregado; trocar design/base descarrega o anterior.

Cancelar torna o áudio inacessível e para a reprodução na interface. Um forward de GPU já iniciado pode terminar antes de liberar o worker; ele não é retomado como call atual. Timeout máximo do worker: 15 minutos. O runtime não baixa pesos durante síntese. Não há fallback silencioso para mock, áudio gravado ou serviço pago.

O módulo humano tem testes de execução e demonstração técnica sintética em 0.5. O simulador ainda não é executável; seus testes serão adicionados quando houver implementação. Mocks comprovam contratos de software; o benchmark comprovou síntese local, não inteligência tática, calibração ou superioridade humana. Qualidade estética da amostra 43 foi aprovada pelo usuário, sem validação linguística de PT-BR.
