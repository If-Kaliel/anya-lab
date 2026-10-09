# Voz local no Windows

## Instalar

O laboratório principal continua na `.venv`. Qwen usa `.venv-voice`, com Python 3.12 e dependências próprias. Sem serviço pago, ElevenLabs ou FlashAttention obrigatório. RTX 4060 8GB foi testada com PyTorch 2.11.0+cu128, driver 610.88 e atenção SDPA.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-voice.ps1
.venv-voice/Scripts/python.exe scripts/prepare_voice.py --download
```

Os pesos oficiais somam cerca de 7GB. Reserve 15–20GB com runtime CUDA e temporários. O primeiro comando instala bibliotecas; só o segundo baixa os pesos, de Hugging Face. Nenhum vídeo, áudio pessoal ou experimento é enviado. Os commits oficiais ficam em `data/models/{design,clone}/anya-source.json`.

Para reproduzir as bibliotecas medidas, instale primeiro torch/torchaudio do índice CUDA acima e depois `pip install -r requirements-voice.lock`. O lock foi gerado no Windows; em outra plataforma, use o script/versões do Qwen e confira disponibilidade de wheels. Não misture o lock de voz com `requirements.lock` do backend.

## Criar e aprovar identidade

1. Abra Anya pelo lançador normal e a área **Anya Speaks**.
2. Escreva uma frase em inglês de cerca de 6–10 segundos e clique **Gerar amostra original**. Mude a seed para comparar variantes.
3. Ouça cada referência. A direção é uma mulher adulta jovem, britânica suave, serena e levemente aérea; nenhuma gravação de atriz/personagem foi utilizada.
4. Clique **Selecionar identidade** na amostra aprovada. Essa é uma decisão explícita; gerar novas amostras não muda a seleção.
5. Ative voz, escreva outra frase e clique **Sintetizar com voz selecionada**. Use Ouvir caso o navegador bloqueie autoplay. Ajuste volume, consulte latência e repita mensagens pelo histórico.

Duas candidatas originais foram geradas no benchmark de desenvolvimento, seeds 42 e 43. Nenhuma está aprovada ou selecionada automaticamente. Áudio WAV, transcrição, descrição, seed, modelo/commit e hashes ficam em `data/voice`. Seleções têm histórico local. O clone prompt é construído uma vez por identidade no worker e reutilizado até descarregar/trocar o modelo. Falas recorrentes idênticas usam cache explícito em memória, identificado no registro.

Idiomas: a interface libera apenas inglês experimental. A família Qwen suporta português, mas qualidade e sotaque brasileiro ainda precisam de testes e aprovação antes de uma versão estável. Não confunda suporte declarado pelo fornecedor com qualidade verificada para Anya.

## Usar Oracle Comms

Selecione um experimento no Replay Workspace, registre uma previsão inicial e abra Anya Speaks. Ative voz e **Gerar calls ao avançar novas previsões**. Volte ao replay e avance uma previsão por vez. Comms usa somente o snapshot registrado naquele T. Não lê eliminações ou resultados. Risco aliado/adversário manual recente, confiança >=0,7 e valor >=0,6 pode gerar warning; sem evidências, fica em silêncio com motivo registrado.

O texto é um template auditável, sem LLM. Nunca confirma uma eliminação futura. Calls críticos substituem pendentes menos importantes. Ao avançar o replay além de T+5s, o áudio anterior é recusado ou interrompido. Falas lentas não devem ser tratadas como informação atual; a previsão numérica continua registrada normalmente.

Research Mode mantém o modelo para geração offline. Replay Commentary mantém o modelo e aplica calls temporais. Lightweight descarrega o runtime depois de gerar. **Liberar modelo da GPU** fecha o worker quando não houver geração ativa.

## Benchmark nesta máquina

Data: 09/10/2026. Windows 11, RTX 4060 (8188MiB), driver 610.88, torch 2.11.0+cu128, qwen-tts 0.1.1, SDPA. Comando: `.venv/Scripts/python.exe scripts/benchmark_voice.py`. Resultados locais completos: `exports/voice-benchmark.json`.

| Operação | Áudio | Tempo total | Pico CUDA alocado pelo PyTorch |
| --- | --- | --- | --- |
| VoiceDesign, seed 42, primeira carga | 6,00s | 40,36s | 4,02GiB |
| VoiceDesign, seed 43, modelo residente | 6,80s | 20,52s | 4,04GiB |
| Base, primeira carga + prompt | 3,20s | 13,80s | 2,25GiB |
| Base, prompt reutilizado | 4,08s | 12,23s | 2,27GiB |
| Base, prompt reutilizado, frase repetida sem cache de áudio | 3,20s | 10,01s | 2,25GiB |

Os tempos incluem carga quando indicada; não medem streaming ou tempo até primeiro token. O pico não é todo o consumo do driver/desktop. É uma pequena medição de funcionamento, sem intervalo estatístico ou garantia em vídeos longos. As latências superam a duração dos áudios; **tempo real ainda não foi demonstrado**. O benchmark não usa cache de WAV para os clones, e `prompt_count=1` confirma reuso das features da referência nas três frases. A qualidade vocal precisa de escuta humana.

## Problemas comuns

- Pesos ausentes: rode prepare_voice com --download; a API mostra erro, sem mock automático.
- Falha de CUDA/VRAM: feche outros consumidores de GPU, libere o modelo e tente novamente. CPU é selecionada quando CUDA não existe, mas não foi benchmarkada e pode ser muito lenta. Não há fallback automático após OOM.
- FlashAttention ausente: aviso esperado; usamos SDPA. Não instale builds incertos para mascarar falhas.
- SoX ausente: o pacote oficial emite aviso no Windows. O fluxo medido usa arrays SoundFile e funcionou sem executável SoX; outras operações opcionais do fornecedor podem precisar dele.
- Áudio bloqueado: use Ouvir, confira Ativar voz e o volume. Modelos não substituem áudio por uma gravação silenciosamente.
- Geração travada: consulte `data/voice/worker.log`; limite de 15min, falha registrada. Cancelar invalida playback; kernel GPU já iniciado pode continuar até terminar.
- Referência alterada: hash/manifesto inválido é recusado. Não edite áudio/transcrição de uma identidade existente; gere outra.

Backup atual do laboratório inclui banco e gravações, não pesos nem `data/voice`. Feche o serviço e copie a pasta inteira `data/voice` separadamente para preservar referências, seleção e histórico. Não misture apenas WAV de outra instalação com o manifesto existente.
