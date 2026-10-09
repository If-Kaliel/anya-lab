# Treinamento supervisionado offline

O Modelo C é um classificador real de regressão logística, com padronização, semente 42 e máximo de 500 iterações. O dashboard oferece os dois baselines; o Modelo C continua no fluxo offline. Não há pesos pré-treinados de Marvel Rivals, reconhecimento de eventos ou registro automático de artefatos Python enviados por terceiros.

## Gerar os exemplos

Importe partidas diferentes nos splits train, validation e test, declarando a partida de origem. Anote observações e resultados e revise os intervalos. Em **Modelos & comparação → Dados para treinamento**, exporte gravações reais ou demonstrações sintéticas. Cada exportação mantém um único tipo de dado, evitando misturar testes de software e gameplay real.

Também é possível exportar pelo terminal:

```powershell
.\.venv\Scripts\python.exe -m research.export_dataset --data-dir data --output exports/training-dataset.json
```

Para testar o software com dados sintéticos, acrescente `--synthetic`. O vídeo sintético de 30s sozinho não fornece exemplos suficientes para treinar.

A exportação aplica janelas `(T,T+15]` a cada 5s. Somente rótulos com revisão confiável entram nos exemplos. O gerador de features recebe um snapshot imutável de observações até T; eventos, notas e resultados não entram nesse snapshot. O rótulo é calculado separadamente para aprendizado offline.

Features na ordem: `ally_risk`, `enemy_risk`, `visibility`. Cada uma usa a observação mais recente com confiança positiva e idade de até 10s, multiplicando valor × confiança. Ausência ou evidência antiga produz zero; `feature_observed` indica essa ausência, mas não entra na regressão atual. Isso limita o modelo e requer análise da qualidade dos dados.

`match_id` identifica a partida de origem; `video_id` identifica o trecho. `source_timestamp` é o timestamp do trecho somado ao início na partida. A exportação inclui hashes dos vídeos e anotações, versão das features, configurações e diagnóstico de exclusões. A identificação depende das declarações do pesquisador. O gerador recusa splits conflitantes ou sobreposição entre trechos com a mesma origem.

## Treinar

```powershell
.\.venv\Scripts\python.exe -m research.train exports/training-dataset.json --output data/models/experimento-01
```

O treinamento exige ao menos **30 amostras de treino**, as **três classes** e uma **partida de validação independente**. A validação das entradas também verifica a partida de origem para impedir que clips com IDs diferentes sejam distribuídos em splits diferentes. Exemplos test não são usados para ajustar o modelo nem para calcular as métricas de validação.

O comando produz `model.joblib` e `metadata.json` locais, com versão do scikit-learn, ordem das classes e features, partidas, contagens, hash do dataset, Accuracy, Brier, Log Loss e matriz de confusão de validação. O estado é `trained_not_independently_validated`. Dados declarados como demonstração mantêm essa identificação nos metadados.

Trinta janelas não significam trinta partidas independentes. Janelas sobrepostas são correlacionadas. Use múltiplas partidas, controle vieses de anotação e preserve um conjunto de teste independente para um protocolo futuro. Não carregue arquivos joblib de origem desconhecida: são artefatos Python executáveis. O dashboard não recebe uploads desses arquivos.
