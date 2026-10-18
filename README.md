# HAI — Human-AI Interaction Platform

Tutor virtual de apoio escolar embarcado: capta a voz do aluno, transcreve localmente com Whisper e consulta um LLM remoto, respondendo em voz natural via Piper TTS. Projetado para rodar em Raspberry Pi 5 sem depender de conexão contínua para o STT.

## Pipeline

<pre>
voz -> VAD (Silero) -> STT (Whisper) -> LLM API (streaming) -> TTS (Piper) -> speaker
                                   ▲          └>  Display (Tkinter) -> Tela
webcam -> foto (OpenCV, opcional) -──┘
</pre>

Cada etapa é assíncrona e não-bloqueante:
- O microfone continua ouvindo enquanto o Whisper transcreve.
- O TTS começa a falar antes da resposta do LLM terminar (streaming).
- Transcrição parcial é enviada ao LLM enquanto o aluno ainda fala (streaming STT).
- A foto da webcam (mesma que capta o áudio) segue junto com a pergunta ao LLM.

## Hardware

- Raspberry Pi 5
- Raspberry Pi OS Lite (64-bit)
- Saída de áudio: HDMI ou jack 3.5mm
- Webcam USB (microfone + câmera; fotos via OpenCV/V4L2)

## Estrutura

```
├── stt/        captura de áudio, VAD e transcrição Whisper
├── api/        cliente LLM com streaming assíncrono
├── tts/        síntese de voz não-bloqueante (Piper, espeak, pyttsx3)
├── vision/     captura de foto pela webcam (OpenCV) e tipo da imagem
├── display/    driver do display físico
├── core/       orquestração do pipeline (main + pipeline)
└── config/     configurações e segredos
```

## Instalação

### 1. Dependências do sistema

```bash
+sudo apt install -y portaudio19-dev libsndfile1 espeak-ng libespeak-ng-dev python3-tk
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
# Torch CPU (importante: antes do pip install -r)
pip install torch --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

### 4. Configuração

```bash
cp config/settings.example.toml config/settings.toml
# Edite settings.toml com os caminhos do Piper e preferências

# Crie secrets.toml com sua chave de API (nunca versionar)
cat > config/secrets.toml << 'TOML'
[api]
key = "SUA_CHAVE_AQUI"
TOML
```

### 5. Áudio via HDMI

```bash
# Define HDMI como saída padrão do ALSA
echo 'defaults.pcm.card 0
defaults.ctl.card 0' > ~/.asoundrc

# Verifica saídas disponíveis
aplay -l
```

## Uso

```bash
# Detecção automática de voz (VAD)
python core/main.py

# Push-to-Talk via Enter
python core/main.py --ptt

# Sem TTS (só texto no terminal — útil para desenvolvimento)
python core/main.py --no-tts

# Forçar backend de TTS
python core/main.py --tts-backend espeak

# Manter o mic capturando enquanto o tutor responde (barge-in por voz)
python core/main.py --allow-barge-in
```

## Fotos (webcam → LLM)

A mesma webcam que capta a voz tira fotos que seguem **junto com a próxima
pergunta** ao LLM (multimodal). Duas formas de tirar a foto:

- **Tecla de foto** (`f` por padrão, `[ux] photo_key`): captura na hora e deixa a
  foto pendente; a próxima pergunta já vai com ela.
- **Voz**: dizer `"tira uma foto"` ou `"olha isso"` na própria pergunta, por exemplo
  *"olha isso, que planta é essa?"*. Se disser só o gatilho (*"tira uma foto"*), o tutor
  tira a foto, avisa por voz e espera a pergunta.

A foto só é consumida quando a resposta chega (cancelar ou erro de API mantêm a foto),
expira em `photo_ttl_s` segundos e pode ser descartada com a tecla de cancelamento
quando não há nada em andamento. A imagem é reduzida (lado maior `max_side`) e enviada
em JPEG; o flash-card do tópico também recebe a foto. Nada é gravado em disco, a menos
que `[camera] save_dir` seja preenchido.

```bash
python -m vision.camera --list              # índices de câmera que entregam frames
python -m vision.camera --device 0 -o t.jpg # foto de teste, sem o resto do pipeline
```

> A foto continua no histórico da sessão (o LLM pode se referir a ela depois) e é
> reenviada a cada turno: dizer **"resetar"** limpa o histórico e alivia o payload.

## Controles

| Tecla | Ação |
|---|---|
| **Espaço** | Cancela o pedido em andamento: interrompe o stream do LLM, corta a fala do TTS na hora e devolve o mic |
| **Enter** (PTT) | Começa/encerra a gravação; durante a resposta é ignorado (mic mutado) |
| **Espaço** (PTT, gravando) | Descarta o áudio gravado sem enviar |
| **F** (foto) | Tira uma foto para a próxima pergunta (se `[camera]` estiver ativa; configurável em `[ux] photo_key`) |
| **Espaço** (sem nada em andamento) | Descarta a foto pendente |
| **Ctrl+C** | Encerra o programa (restaura o terminal) |

> A tecla de cancelamento é configurável em `[ux] cancel_key` (`space`,
> `esc`, `enter`, `tab`, `backspace`, `ctrl+c` ou uma letra). O padrão é
> **Espaço** porque o display Tk usa **Esc** para sair da tela cheia.


## Docker

```bash
# Build local (arquitetura do host)
docker build -t hai .

# Run (monta config com secrets)
docker run -it --rm \
  --device /dev/snd \
  --device /dev/video0 \
  -v $(pwd)/config:/app/config \
  hai

# Build multi-arch (amd64 + arm64) via Buildx
docker buildx build --platform linux/amd64,linux/arm64 -t hai .
```

## Display (janela X11 no HDMI)

O `display/` renderiza a resposta do tutor em Markdown numa janela X11,
mais um **flash-card** com o resumo do tópico da pergunta atual, gerado
pela LLM a cada utterance:

<pre>
┌──────────────────────────────────────┬──────────────────┐
│                                      │ Resumo do        │
│  ## Resposta em Markdown do tutor    │    tópico        │
│  negrito, itálico, código,           │                  |
│  listas, blocos de código etc.       │ ## Fotossíntese  │
│                                      │ Resumo: ...      │
│                                      │ - ponto 1        │
│                                      │ - ponto 2        │
└──────────────────────────────────────┴──────────────────┘
</pre>
Se não houver `tkinter` disponível ou nenhum servidor X (`$DISPLAY`), o
driver cai automaticamente em modo headless: o pipeline continua
funcionando normalmente (texto no terminal + áudio), só sem a janela.

Configuração em `config/settings.toml`:

```toml
[display]
enabled = true
fullscreen = true 
width = 1024 
height = 600
font_size = 20
flashcard_width = 340 
```


## Configuração (`config/settings.toml`)

```toml
[api]
model = "gemma-4-26b-a4b-it"

[stt]
language = "pt"
whisper_model = "small"       # tiny | small | medium
whisper_device = "cpu"
whisper_compute_type = "int8" # sempre int8 na CPU

[vad]
threshold = 0.5
preroll_ms = 500
silence_ms = 700
interim_interval_ms = 1500    # 0 = desativa streaming parcial

[tts]
backend = "piper"             # piper | espeak | pyttsx3
piper_bin   = "/home/rafa/piper/piper/piper"
piper_model = "/home/rafa/piper/voices/pt_BR-faber-medium.onnx"
rate = 160
lang = "pt-br"

[display]
enabled = true
fullscreen = true 
width = 1024 
height = 600
font_size = 20
flashcard_width = 340 

[camera]
enabled = true
device = 0                    # índice V4L2 ou "/dev/video0" — a mesma webcam do microfone
width = 1280
height = 720
max_side = 1024               # lado maior (px) da foto enviada ao LLM
jpeg_quality = 85
warmup_frames = 8             # estabiliza exposição/branco antes do frame final
photo_ttl_s = 120             # foto pendente expira sem pergunta
save_dir = ""                 # vazio = não grava fotos em disco

[ux]
mute_while_responding = true  # false = mic continua aberto durante a resposta (barge-in)
cancel_key = "space"          # tecla de cancelamento (Esc é usado pelo display p/ tela cheia)
photo_key = "f"               # tecla de foto (vazio = só gatilho de voz)
```

## Testes

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Targets de latência

| Etapa | Target |
|---|---|
| STT (whisper small int8) | < 2s |
| Início da resposta falada | < 1s após transcrição |
| Ciclo completo | < 3–5s |

## Palavras-chave de controle

Dizer **"resetar"** ou **"nova sessão"** durante a conversa apaga o histórico e reinicia a sessão com o LLM.
