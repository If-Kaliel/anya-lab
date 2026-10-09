# Dataset versionado

Novas gravações incluem `source_match_id`, `source_offset` e `source_identity`. A origem declarada é normalizada (espaços externos removidos e casefold) e impõe o mesmo split para todos os cortes. Cortes sobrepostos são recusados. A identidade não é inferida do conteúdo: o pesquisador precisa usar o mesmo identificador mesmo após reencodificar o jogo. O fallback de arquivos novos sem origem e de gravações legadas é uma identidade única por arquivo.

`timebase_version=video-zero-1` identifica novas importações cuja duração termina no fim do último quadro, relativa ao primeiro quadro em zero; `first_frame_pts` guarda a posição inicial no relógio do arquivo. `requires_preview` informa a necessidade de uma cópia de reprodução compatível. Gravações antigas mantêm os metadados originais. O schema 1.1 recebe esses metadados adicionais na seção `match`, mantendo o formato de anotações e revisões.

O dataset de treinamento offline continua separado do dataset de anotação: schema 1.0 com `feature_version`, `feature_order`, `provenance` e diagnóstico. Ele usa a partida de origem como `match_id`, registra o `video_id` do corte e calcula `source_timestamp`. Consulte [treinamento](training.md) para a regra de features e o tratamento de dados sintéticos.

`GET /api/videos/{id}/dataset` exporta `schema_version: "1.1"`, `match`, `annotations` e `annotation_history`. Uma partida possui ID, nome, duração, dimensões, hash SHA-256, split, indicação sintética e data de importação. Arquivos de mídia e banco não fazem parte do Git. O formato de features para treinamento offline permanece separado, na versão 1.0.

`annotations.observations`: timestamp, kind (`ally_risk`, `enemy_risk`, `visibility`), value e confidence em [0,1], note opcional. Os riscos são julgamentos manuais, não reconhecimento automático. Confiança zero significa desconhecido. Valores antigos (>10s) não influenciam a heurística.

`annotations.events`: timestamp, team (`ally`, `enemy`, `unknown`), reliable e note. Representa eliminações observáveis para avaliação. `annotations.reviews`: start, end, reliable e note; comprova somente que o anotador declara ter revisado todo o intervalo.

Rótulos finais são derivados pelo Evaluation Engine, não inseridos em observações. Referência de equipes sempre relativa ao jogador do POV; documente mudanças de perspectiva nas notas e exclua janelas em que a identificação não é confiável.

Cada anotação atual possui `id` estável e `revision`. Registros novos também armazenam `recorded_at`. O histórico inclui a anotação original, motivo e timestamp das revisões, hashes, retiradas e restaurações. Registros de bancos antigos aparecem como revisão zero sem reescrever o conteúdo original.

Contratos de revisão: `POST /api/videos/{video_id}/annotations/{kind}/{id}/revise` recebe `expected_revision`, `reason` e `annotation`. `kind` é `observations`, `events` ou `reviews`, com o contrato correspondente. `/retract` recebe versão esperada e motivo; `/restore` acrescenta `target_revision`. HTTP 409 indica edição concorrente; não repita a gravação com outra versão sem conferir os dados atuais.

Observações corrigidas não alteram snapshots anteriores. Corrigir eventos/revisões muda somente avaliações produzidas **depois** da correção. Relatórios históricos conservam seus rótulos e métricas. A retirada é reversível e não apaga evidências já utilizadas.

Nunca coloque trechos da mesma partida em splits diferentes. A checagem automática detecta o mesmo arquivo sob nomes diferentes, mas não versões recortadas ou reencodadas. Estabeleça IDs de partida de origem na organização de pesquisa e faça revisão manual das divisões.

## Entrada para treinamento offline

```json
{
  "schema_version": "1.0",
  "samples": [
    {"match_id": "match-001", "split": "train", "timestamp": 10,
     "features": [0.2, 0.6, 0.8], "label": "enemy_first"}
  ]
}
```

Ordem das features: risco aliado, risco adversário, visibilidade. Cada feature deve ser calculada somente com informações disponíveis até o timestamp. O script valida valores, classes e separação por partida; ele não prova a procedência temporal dos features fornecidos pelo pesquisador.

```powershell
.\.venv\Scripts\python.exe research/train.py data/labeled-features.json --output data/models/supervised-v1
```

Mínimos operacionais: 30 amostras train, três classes e uma partida validation independente. São mínimos de funcionamento, não adequação científica. O script gera pesos reais e metadados locais, mede validation Accuracy/Log Loss, preserva o conjunto test e registra `trained_not_independently_validated`. Não acompanha pesos de demonstração nem usa esse modelo no dashboard.
