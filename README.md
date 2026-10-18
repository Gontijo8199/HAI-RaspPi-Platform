# HAI — Human-AI Interaction Platform

Plataforma educacional de inteligência artificial embarcada, pensada para um
Raspberry Pi 5 com tela de toque de **1024 × 600**. Ao iniciar, ela abre um
**menu de atividades**. Nesta versão há uma única atividade:

- **Conversar com a IA** — o aluno monta uma pergunta falando (Whisper local),
  escrevendo e tirando fotos com a webcam, e um LLM remoto responde em texto
  (Markdown) e em voz (Piper TTS).

As outras atividades previstas na POC (classificadores, árvores de decisão,
aprendizado por reforço, geração de imagem, agentes...) **ainda não foram
implementadas** e não aparecem no menu. A estrutura de módulos existe para
recebê-las depois (veja [Adicionar um módulo](#adicionar-um-módulo)).

O tutor por voz original, sem interface gráfica, continua disponível como
**modo terminal** (`--terminal`), útil em SSH, Docker e depuração.

## Visão geral

<pre>
                         ┌──────────── core/app.py ────────────┐
python core/main.py ───► │ janela Tk · menu · navegação · fim   │
                         └───────┬──────────────────────────────┘
                                 │ enter()/exit()
                       modules/chat (Conversar com a IA)
                       ├─ view.py     tela (layout da POC)
                       └─ session.py  lógica da conversa (sem Tk)
                                 │ usa
              core/services.py — serviços compartilhados, criados 1 vez
   ┌──────────────┬──────────────┬───────────────┬──────────────────┐
   api/ LLM       tts/ Piper     stt/ Whisper     vision/ webcam
   (streaming)    (fila+thread)  + microfone      (OpenCV, sob demanda)
</pre>

Pipeline de uma pergunta no módulo de conversa:

<pre>
segurar 🎤 → PortAudio → soltar → Whisper (local) ─┐
digitar ───────────────────────────────────────────┼─► rascunho ordenado ─► Enviar
Foto → webcam (OpenCV) → JPEG ─────────────────────┘    [texto, foto, texto…]
   ─► LLM (1 requisição multimodal, streaming) ─► balão da IA (Markdown)
                                               └─► TTS frase a frase ─► alto-falante
</pre>

## Estrutura

```
├── core/
│   ├── main.py        ponto de entrada (argumentos; interface gráfica ou --terminal)
│   ├── app.py         aplicação gráfica: janela, menu, navegação, ciclo de vida, encerramento
│   ├── services.py    configuração/credenciais e serviços compartilhados (LLM, TTS, câmera, Whisper)
│   ├── terminal.py    modo terminal legado (VAD ou PTT por teclado)
│   ├── pipeline.py    orquestração do modo terminal (fala → LLM → TTS → display)
│   ├── hotkeys.py     teclas do modo terminal
│   └── ui.py          saída colorida do modo terminal
├── modules/
│   ├── base.py        contrato de um módulo (enter / exit / close)
│   ├── __init__.py    lista de módulos do menu (build_modules)
│   └── chat/          "Conversar com a IA": module.py (ligação), session.py (lógica), view.py (tela)
├── gui/               tema (paleta da POC), widgets de toque, menu principal
├── api/               cliente LLM (google-genai) com streaming, cancelamento e erros legíveis
├── stt/               microfone (PyAudio), gravador segurar-para-falar, Whisper, VAD (só terminal)
├── tts/               síntese de voz não-bloqueante (Piper, espeak, pyttsx3) e quebra em frases
├── vision/            captura de foto pela webcam (OpenCV) e tipo da imagem
├── display/           Markdown → Tk (compartilhado) e janela de saída do modo terminal
├── config/            settings.toml (parâmetros) e secrets.toml (chave, nunca versionar)
├── tests/             pytest (dublês de serviços em tests/fakes.py)
└── POC/               prova de conceito HTML (interface.zip) — referência visual, não é usada em execução
```

### Responsabilidades e decisões

| Componente | Responsabilidade |
|---|---|
| `core/app.py` (`App`) | Cria a janela, mostra o menu, abre/fecha módulos com um lock (toques duplos não abrem duas vezes), trata fechar janela/Ctrl+C/SIGTERM e encerra tudo na ordem. |
| `core/services.py` (`Services`) | Lê a configuração sem derrubar o app (problemas viram avisos no menu) e cria **uma vez** o cliente LLM, o TTS e a câmera. O Whisper é carregado sob demanda, em thread, uma única vez por execução. |
| `modules/base.py` (`Module`) | Contrato mínimo: `enter(frame, voltar)`, `exit()`, `close()`, `unavailable_reason()`, `draw_icon()`. |
| `modules/chat/session.py` (`ChatSession`) | Rascunho ordenado (texto/foto), uma atividade por vez, envio único multimodal, streaming para tela e TTS, cancelamento, nova conversa, descarte de resultados atrasados. Não importa Tk. |
| `modules/chat/view.py` (`ChatView`) | Widgets da tela; só reflete o estado da sessão e chama seus métodos. |

- **Tecnologia de tela: Tkinter.** A POC é HTML/JS no navegador, mas o projeto
  já usava Tk para a tela e o backend (microfone, Whisper, câmera, TTS) é
  Python. Reproduzir o layout da POC em Tk evita um servidor web local, um
  navegador em modo quiosque e chaves de API no front-end, sem dependências
  novas.
- **Um único event loop.** O Tk é bombeado dentro do loop asyncio
  (`root.update()` ~50×/s). Callbacks de botão e tarefas assíncronas rodam na
  mesma thread: não há filas entre threads na interface, e trabalho pesado
  (rede, Whisper, câmera, áudio) continua nas threads de cada serviço.
- **Sem emoji na interface Tk**: o Tk 8.6 no X11 não desenha fontes de emoji
  coloridas. Os ícones são desenhados em `Canvas` ou usam símbolos Unicode básicos.

## Fluxo de inicialização e navegação

1. `python core/main.py` lê `config/settings.toml` e `config/secrets.toml`.
   Arquivo ausente/inválido ou chave vazia **não fecham o app**: o menu mostra o
   problema e o cartão afetado explica por que não abre.
2. `Services` cria LLM, TTS e câmera (nada de microfone nem Whisper ainda).
3. A janela abre em tela cheia (ou `--windowed`) com o menu.
4. Tocar em **Conversar com a IA** cria a tela do módulo, abre o microfone
   **pausado** e começa a carregar o Whisper em segundo plano.
5. **← Voltar**: o módulo cancela gravação/transcrição/resposta/fala, fecha o
   microfone, recria a sessão do LLM e apaga mensagens, rascunho e fotos; a
   tela é destruída e o menu volta. LLM, TTS e Whisper continuam carregados.
6. Fechar a janela, Ctrl+C ou SIGTERM: sai do módulo ativo, encerra os
   módulos e os serviços (TTS, stream do LLM) e destrói a janela.

Esc sai da tela cheia (útil para manutenção).

## Módulo "Conversar com a IA"

Layout de `conversar-llm.html` (POC):

```
[← Voltar]  Conversar com a IA                [Voz: ligada] [Nova conversa]
┌ conversa: aluno à direita, IA à esquerda (Markdown) ──────────────────────┐
● estado atual ou aviso
┌ pergunta em montagem: blocos de texto/foto, ＋ entre blocos, ✕ remove ────┐
[● Segurar para falar] [Foto] [Escrever]                 [■ Parar] [Enviar ➤]
```

- **Segurar para falar**: grava enquanto o botão estiver pressionado; ao soltar,
  o Whisper local transcreve e o texto vira um bloco editável. Gravações muito
  curtas (< 0,3 s) são descartadas com aviso.
- **Foto**: tira uma foto com a webcam configurada e adiciona um bloco com
  miniatura (`foto 1`, `foto 2`...).
- **Escrever** / **＋**: cria um bloco de texto no fim ou entre dois blocos.
  Enter envia; Shift+Enter quebra a linha.
- **Enviar**: manda todos os blocos **na ordem**, numa única requisição
  multimodal, para a sessão de chat atual (o LLM lembra a conversa).
- **Parar**: interrompe a transcrição, a foto, a resposta (corta o stream na
  rede) ou a fala. Uma resposta interrompida ou com erro devolve a pergunta ao
  rascunho para tentar de novo.
- **Voz: ligada/desligada**: liga ou desliga a leitura da resposta (TTS).
- **Nova conversa**: apaga o histórico (inclusive o do LLM), as mensagens e o rascunho.

Estados mostrados na linha de status: pronto · gravando · transcrevendo ·
tirando a foto · pergunta enviada/aguardando a IA · a IA está respondendo ·
lendo em voz alta · avisos (azul) e erros (vermelho), como falta de conexão,
chave recusada, limite de uso, microfone ou câmera indisponíveis.

Só uma atividade acontece por vez: não dá para enviar duas vezes, gravar
durante uma transcrição ou fotografar durante uma resposta. Começar a gravar
enquanto a IA fala interrompe a fala.

### Privacidade

- Nada da conversa é gravado em disco: histórico, rascunho e fotos ficam só na memória.
- Sair do módulo ou tocar em **Nova conversa** recria a sessão do LLM e apaga tudo.
- O microfone só captura enquanto o botão está pressionado (fica pausado no PortAudio no resto do tempo).
- Logs técnicos não contêm perguntas, transcrições, respostas nem imagens
  (só tamanhos, tipos de erro e estados).
- Não há telemetria. O único envio externo é a requisição ao LLM configurado.
- Exceção opcional: `[camera] save_dir` grava as fotos em disco para depuração (vazio por padrão).

## Hardware

- Raspberry Pi 5 com Raspberry Pi OS (64-bit) e sessão gráfica (X11 ou Wayland com XWayland)
- Tela de toque 1024 × 600 (outras resoluções funcionam; a área da conversa se ajusta)
- Webcam USB (câmera + microfone) — fotos via OpenCV/V4L2, áudio via PortAudio
- Saída de áudio: HDMI ou jack 3,5 mm

| Recurso | Precisa de |
|---|---|
| Interface gráfica | sessão gráfica (`$DISPLAY`) e `python3-tk` |
| Respostas da IA | internet + chave de API válida |
| Falar com a IA | microfone; o modelo Whisper é baixado da internet na **primeira** execução e depois funciona offline |
| Fotos | webcam acessível em `[camera] device` e OpenCV |
| Resposta em voz | saída de áudio + Piper (ou espeak-ng) |

## Instalação

### 1. Dependências do sistema

```bash
sudo apt install -y portaudio19-dev libsndfile1 espeak-ng libespeak-ng-dev python3-tk
```

Opcional, para diagnosticar a câmera: `sudo apt install v4l-utils` (`v4l2-ctl --list-devices`).

### 2. Piper TTS

```bash
mkdir -p ~/piper/voices && cd ~/piper

# Raspberry Pi 5 (arm64)
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
tar -xzf piper_linux_aarch64.tar.gz

# Voz pt-BR
wget -P voices https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
wget -P voices https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json
```

### 3. Python

```bash
python3 -m venv venv && source venv/bin/activate

# Torch CPU (importante: antes do pip install -r). Só o modo terminal (VAD) usa o torch.
pip install torch --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

Dependências principais (`requirements.txt`): `PyAudio` (microfone),
`faster-whisper` + `numpy` (STT), `torch` (Silero VAD, modo terminal),
`opencv-python-headless` (câmera e miniaturas), `google-genai` (LLM),
`pyttsx3` (TTS alternativo). A interface usa o `tkinter` da biblioteca padrão.

### 4. Configuração e credenciais

```bash
cp config/settings.example.toml config/settings.toml
# Edite settings.toml: modelo, caminhos do Piper, câmera...

# Chave de API (nunca versionar — já está no .gitignore)
cat > config/secrets.toml << 'TOML'
[api]
key = "SUA_CHAVE_AQUI"
TOML
```

`config/settings.toml` e `config/secrets.toml` estão no `.gitignore`. O
container Docker recebe a pasta `config/` por volume em tempo de execução.

### 5. Áudio via HDMI

```bash
# Define HDMI como saída padrão do ALSA
echo 'defaults.pcm.card 0
defaults.ctl.card 0' > ~/.asoundrc

# Verifica saídas e entradas disponíveis
aplay -l
arecord -l
```

O microfone usado é o dispositivo de entrada padrão do PortAudio/ALSA; a voz
sai pelo `aplay` (Piper) ou `espeak-ng`, na saída padrão.

## Uso

```bash
# Interface gráfica (padrão): menu → Conversar com a IA
python core/main.py

# Em janela, sem tela cheia (desenvolvimento)
python core/main.py --windowed

# Sem voz nas respostas
python core/main.py --no-tts

# Forçar backend de TTS
python core/main.py --tts-backend espeak
```

### Modo terminal (legado)

```bash
python core/main.py --terminal          # detecção automática de voz (VAD)
python core/main.py --ptt               # Push-to-Talk via Enter (implica --terminal)
python core/main.py --allow-barge-in    # mic aberto durante a resposta (implica --terminal)
```

O modo terminal mantém o comportamento anterior: VAD (Silero) + Whisper,
resposta em voz, janela de saída com resposta em Markdown e flash-card do
tópico (`[display]`), foto pela tecla `f` ou por voz ("tira uma foto", "olha
isso, ..."), e "resetar"/"nova sessão" por voz para apagar o histórico.

| Tecla (modo terminal) | Ação |
|---|---|
| **Espaço** | Cancela o pedido em andamento (stream do LLM + fala) e devolve o mic |
| **Enter** (PTT) | Começa/encerra a gravação |
| **Espaço** (PTT, gravando) | Descarta o áudio gravado |
| **F** | Tira uma foto para a próxima pergunta (`[ux] photo_key`) |
| **Espaço** (nada em andamento) | Descarta a foto pendente |
| **Ctrl+C** | Encerra o programa |

### Diagnóstico da câmera

```bash
python -m vision.camera --list              # índices de câmera que entregam frames
python -m vision.camera --device 0 -o t.jpg # foto de teste, sem o resto do app
```

## Configuração (`config/settings.toml`)

Veja `config/settings.example.toml` (comentado). Seções:

| Seção | Usada por | Principais chaves |
|---|---|---|
| `[api]` | ambos | `model`, `timeout_s` (espera máxima por trecho da resposta; padrão 30) |
| `[stt]` | ambos | `language`, `whisper_model` (tiny/small/medium), `whisper_device`, `whisper_compute_type` |
| `[vad]` | terminal | `threshold`, `preroll_ms`, `silence_ms`, `interim_interval_ms` |
| `[tts]` | ambos | `backend` (piper/espeak/pyttsx3), `piper_bin`, `piper_model`, `rate`, `lang` |
| `[display]` | ambos | `fullscreen`, `width`, `height`; `enabled`, `font_size`, `flashcard_width` só no terminal |
| `[camera]` | ambos | `enabled`, `device`, `width`, `height`, `max_side`, `jpeg_quality`, `warmup_frames`, `photo_ttl_s` (terminal), `save_dir` |
| `[ux]` | terminal | `mute_while_responding`, `cancel_key`, `photo_key` |

## Testes

```bash
pip install -r requirements-dev.txt
pytest tests/ -v

# Sem tela (CI/SSH): os testes da interface (tests/test_app.py) são pulados,
# a menos que haja um X virtual:
xvfb-run -a pytest tests/ -v
```

Os testes não precisam de microfone, câmera, rede nem chave de API: os
serviços são substituídos por dublês (`tests/fakes.py`, mocks do
`google-genai`). Cobrem a lógica da conversa (`test_chat_session.py`), a
aplicação gráfica com Tk real (`test_app.py`: menu, navegação repetida sem
vazamento, encerramento, layout em 1024 × 600, fluxo pela tela), o cliente LLM,
o gravador, os serviços e os módulos anteriores.

## Adicionar um módulo

1. Crie `modules/<nome>/` com uma subclasse de `modules.base.Module`:
   ```python
   class MeuModulo(Module):
       id = "meu-modulo"
       title = "Minha atividade"

       def draw_icon(self, canvas, size): ...           # ícone do cartão do menu
       def unavailable_reason(self): return None        # ou um motivo legível
       async def enter(self, parent, go_back): ...      # monta a tela em `parent` e abre recursos
       async def exit(self): ...                        # cancela tarefas e libera recursos
   ```
2. Inclua-o em `modules/__init__.py` → `build_modules()`. O menu se monta a partir dessa lista.
3. Use os serviços de `self.services` (LLM, TTS, câmera, `get_asr()`) em vez de criar novos.
   Recursos próprios do módulo (microfone, timers `after`, binds globais, tarefas)
   devem ser liberados em `exit()`. Widgets criados dentro de `parent` são
   destruídos pelo app.
4. Separe a lógica (testável sem Tk) da tela, como em `modules/chat/`.

## Docker

```bash
docker build -t hai .

# O container não tem servidor X: roda o modo terminal (CMD usa --terminal)
docker run -it --rm \
  --device /dev/snd \
  --device /dev/video0 \
  -v $(pwd)/config:/app/config \
  hai

docker buildx build --platform linux/amd64,linux/arm64 -t hai .
```

Para a interface gráfica dentro do container, repasse o X
(`-e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix`) e rode `python core/main.py`.

## Limitações conhecidas

- **Teclado na tela**: a navegação, a voz, as fotos e o envio funcionam só com
  toque, mas digitar ou corrigir texto exige teclado (físico ou virtual do
  sistema). Não há teclado virtual próprio.
- **Latência do LLM**: modelos lentos (ex.: `gemma-4-26b-a4b-it` com imagens)
  podem levar dezenas de segundos para o primeiro trecho. Estourado
  `[api] timeout_s`, a tela mostra o erro e a pergunta volta ao rascunho;
  aumente o valor se for frequente.
- **Primeira execução**: o Whisper é baixado da internet; até lá o botão de voz
  mostra "Preparando a voz…" (ou "Voz indisponível" se falhar). Texto e foto
  continuam funcionando.
- **Sem anexar arquivos**: as fotos vêm só da webcam (a POC também aceitava
  arquivo do aparelho, o que não faz sentido no Pi sem gerenciador de arquivos de toque).
- **Flash-card do tópico** existe só no modo terminal; a tela de conversa segue a POC.
- Se o LLM devolver uma resposta vazia, a pergunta pode ter ficado no histórico da sessão; reenviá-la pode repeti-la.

## Targets de latência

| Etapa | Target |
|---|---|
| STT (whisper small int8) | < 2s |
| Início da resposta falada | < 1s após o primeiro trecho do LLM |
| Ciclo completo | < 3–5s (depende do modelo remoto) |
