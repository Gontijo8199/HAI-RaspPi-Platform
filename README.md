# HAI — Human-AI Interaction Platform

Tutor virtual de apoio escolar embarcado: capta a voz do aluno, transcreve localmente com Whisper e consulta um LLM remoto, respondendo em voz natural via Piper TTS. Projetado para rodar em Raspberry Pi 5 sem depender de conexão contínua para o STT.

## Pipeline

```
voz → VAD (Silero) → STT (Whisper) → LLM API (streaming) → TTS (Piper) → speaker
```

Cada etapa é assíncrona e não-bloqueante:
- O microfone continua ouvindo enquanto o Whisper transcreve.
- O TTS começa a falar antes da resposta do LLM terminar (streaming).
- Transcrição parcial é enviada ao LLM enquanto o aluno ainda fala (streaming STT).

## Hardware

- Raspberry Pi 5
- Raspberry Pi OS Lite (64-bit)
- Saída de áudio: HDMI ou jack 3.5mm

## Estrutura

```
├── stt/        captura de áudio, VAD e transcrição Whisper
├── api/        cliente LLM com streaming assíncrono
├── tts/        síntese de voz não-bloqueante (Piper, espeak, pyttsx3)
├── display/    driver do display físico
├── core/       orquestração do pipeline (main + pipeline)
└── config/     configurações e segredos
```

## Instalação

### 1. Dependências do sistema

```bash
sudo apt install -y portaudio19-dev libsndfile1 espeak-ng libespeak-ng-dev
```

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
```

## Docker

```bash
# Build local (arquitetura do host)
docker build -t hai .

# Run (monta config com secrets)
docker run -it --rm \
  --device /dev/snd \
  -v $(pwd)/config:/app/config \
  hai

# Build multi-arch (amd64 + arm64) via Buildx
docker buildx build --platform linux/amd64,linux/arm64 -t hai .
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
