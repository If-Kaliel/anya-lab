# Guia do laboratório local

## Abrir no Windows

Depois de instalar Python 3.12+, Node 24 e FFmpeg no PATH, dê dois cliques em **Preparar Anya.cmd**. O comando instala as dependências e compila a interface. Em seguida, use **Iniciar Anya.cmd** e abra http://127.0.0.1:8000. Mantenha o terminal aberto durante o uso; Ctrl+C encerra o servidor.

Na pasta já preparada deste projeto, use apenas **Iniciar Anya.cmd**. **Verificar Anya.cmd** confere Python, dependências, FFmpeg, FFprobe, Node, npm e o dashboard compilado. Os lançadores usam a política de execução do PowerShell apenas no processo que iniciam.

## Organizar as gravações

Clique em **Importar gravação**. Em **Partida de origem**, informe um identificador estável, como `rivals-2026-10-09-01`. Todos os trechos daquele mesmo jogo precisam compartilhar esse identificador e o mesmo split. Para o segundo trecho, informe o início dele na partida original; por exemplo, 300s. Trechos sobrepostos da mesma origem são recusados para evitar duplicação de amostras.

O identificador é uma declaração sua, sem reconhecimento automático do conteúdo. Deixar vazio cria uma identidade por arquivo. Gravações anteriores continuam com sua identidade por arquivo; o projeto não consegue deduzir se dois vídeos antigos vieram da mesma partida. Não distribua cortes ou reencodificações do mesmo jogo entre treino, validação e teste.

O tempo de anotação é sempre relativo ao primeiro quadro do trecho: começa em 0s. O início do trecho na partida original é um metadado separado. Na versão 0.3, novas importações calculam a duração do vídeo pelos quadros, evitando incluir deslocamentos iniciais ou áudio que continua após a imagem. Metadados de importações antigas e relatórios anteriores são preservados.

## Reproduzir e anotar

Em **Dataset & anotações**, o player usa a gravação ou uma cópia local compatível. Quando necessário, clique em **Preparar reprodução compatível**. A tarefa converte para MP4 H.264/AAC, alinha o começo do vídeo em zero e mantém o áudio alinhado. O limite é duas tarefas simultâneas e 15 minutos por conversão. Pode ser necessário dividir gravações longas; também é preciso espaço para a cópia.

A inferência extrai os quadros do arquivo original. A cópia de reprodução serve para anotação no navegador. Ela é comprimida, pode ser regenerada e não é um novo exemplo do dataset.

Pause no evento e confira o timestamp antes de salvar. Aliados e adversários são relativos à perspectiva do jogador gravado. As observações de risco e visibilidade devem registrar somente o que era visível naquele instante. A confiança reduz a influência de evidências incertas.

Registre todas as eliminações visíveis, incluindo eventos incertos ou de equipe desconhecida. Confirme intervalos apenas depois de revisar todo o trecho. O painel de qualidade mostra quantas janelas de 15s, a cada 5s, estão avaliáveis e por que outras serão excluídas. A ausência de um evento não significa `none` sem revisão confiável completa.

**Corrigir**, **Retirar** e **Histórico** mantêm a auditoria das anotações. Uma observação corrigida exige criar um novo experimento; eliminações e revisões corrigidas exigem revelar novamente para produzir outro relatório.

## Executar e comparar

No **Replay Workspace**, selecione o baseline. Configure o primeiro instante e a cadência, de 1 a 60s. O horizonte permanece em 15s e a semente em 42. Os controles configuram a próxima criação; a configuração do experimento em execução aparece separadamente e é preservada.

O heurístico usa riscos manuais recentes. O histórico exige outras partidas de treinamento com intervalos revisados. Crie, registre uma previsão ou execute a sequência. O player cego exibe apenas quadros autorizados até a última previsão; a área de dataset é uma ferramenta humana de anotação, separada da inferência.

Após anotar os resultados, use **Revelar & avaliar**. Em **Research Summary**, escolha uma **Versão do relatório** para consultar revelações anteriores. Os botões JSON/CSV/SRT exportam exatamente a versão selecionada. A SRT contém probabilidades registradas, sem inserir resultados futuros nas legendas.

Em **Modelos & comparação**, escolha dois relatórios da mesma gravação e clique em **Comparar nos mesmos instantes**. O backend usa a interseção dos timestamps e horizontes, exige anotações iguais, recusa relatórios desatualizados e verifica as cadeias. A tabela geral contém totais de cada experimento, que podem usar conjuntos diferentes; a tabela pareada controla os instantes comparados. Uma só partida e janelas sobrepostas não permitem concluir superioridade científica.

## Problemas comuns

| Sintoma | Ação |
| --- | --- |
| FFmpeg/FFprobe ausentes | Execute Verificar Anya.cmd; instale os executáveis e ajuste o PATH ou ANYA_FFMPEG/ANYA_FFPROBE. |
| Player sem vídeo ou codec incompatível | Use a reprodução compatível. Prefira Chrome/Edge com H.264/AAC. |
| Conversão ou indexação excedeu o limite | Use um trecho menor; mantenha a identidade da partida e o início correto do corte. |
| Nenhuma janela avaliada | Confirme os intervalos revisados e examine o painel de qualidade. |
| Histórico sem partidas de treino | Importe outras partidas como train e revise os resultados. |
| Relatório desatualizado | Retome o experimento e revele novamente. A revelação anterior permanece no histórico. |
| Erro de integridade | Preserve os arquivos e restaure um backup verificado em outra pasta. Não reescreva previsões ou hashes para esconder o erro. |
| Porta 8000 ocupada | Encerre uma instância anterior de Anya antes de iniciar outra. |

Para pesquisa offline, consulte [treinamento](training.md). Para proteger seus dados, consulte [backup e recuperação](operations.md).

## Anya Speaks e pesquisa estratégica

O enquadramento inicial preserva o rosto da arte aprovada. Para ativar voz local e comparar referências, siga [voice.md](voice.md). A área Anya Speaks tem controles de voz/volume/idioma, amostras, síntese, histórico e calls. No replay com uma previsão registrada, Strategic Intelligence permite consultar evidências, registrar hipóteses e anotar ações pseudonimizadas. Avaliar hipótese só fica disponível após reveal. Estes módulos são heurísticas e frequências descritivas, sem reconhecimento automático de gameplay.
