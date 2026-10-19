# Dockerfile — HAI Platform
# Build multi-arch: linux/amd64 (dev/CI) e linux/arm64 (Raspberry Pi 5)
#
# A aplicação é gráfica (Qt Quick): o container não tem tela própria e usa a
# sessão Wayland do hospedeiro, o microfone/alto-falante e a webcam dele.
# Exemplo de execução (detalhes no README, seção Docker):
#
#   docker run --rm \
#     -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY -e XDG_RUNTIME_DIR=/tmp/xdg \
#     -v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/tmp/xdg/$WAYLAND_DISPLAY \
#     --device /dev/dri \
#     --device /dev/snd --device /dev/video0 \
#     -v "$PWD/config:/app/config:ro" \
#     ghcr.io/gontijo8199/hai-raspi-module:latest

FROM python:3.12-slim

# Dependências do sistema
# - libegl1, libgl1, libxkbcommon0, libfontconfig1, libdbus-1-3, libwayland-*:
#   o que o Qt (PySide6, do pip) precisa do sistema para abrir a janela no
#   Wayland. fonts-dejavu-core: fonte da interface.
# - portaudio19-dev + build-essential: compilar o PyAudio.
# - alsa-utils: aplay, que toca o áudio do Piper.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libegl1 \
    libgl1 \
    libxkbcommon0 \
    libfontconfig1 \
    libdbus-1-3 \
    libwayland-client0 \
    libwayland-cursor0 \
    libwayland-egl1 \
    fonts-dejavu-core \
    portaudio19-dev \
    alsa-utils \
    libsndfile1 \
    espeak-ng \
    libespeak-ng-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Piper TTS — binário diferente por arquitetura
ARG TARGETARCH
RUN mkdir -p /opt/piper && \
    if [ "$TARGETARCH" = "arm64" ]; then \
        wget -qO- https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz | tar -xz -C /opt/piper; \
    else \
        wget -qO- https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz | tar -xz -C /opt/piper; \
    fi

# Voz pt-BR (Faber medium)
RUN mkdir -p /opt/piper/voices && \
    wget -q -O /opt/piper/voices/pt_BR-faber-medium.onnx \
        https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx && \
    wget -q -O /opt/piper/voices/pt_BR-faber-medium.onnx.json \
        https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
# Falha o build já aqui se o Qt Quick não carregar (não precisa de tela).
RUN QT_QPA_PLATFORM=offscreen python -c "from PySide6.QtGui import QGuiApplication; from PySide6.QtQuick import QQuickView; QGuiApplication([])"

COPY . .

# settings.toml e secrets.toml são montados em runtime — nunca buildar com eles.
VOLUME ["/app/config"]

# Lidos por core/services.py quando [tts] piper_bin/piper_model não estão no settings.toml.
ENV PIPER_BIN=/opt/piper/piper/piper
ENV PIPER_MODEL=/opt/piper/voices/pt_BR-faber-medium.onnx

# Interface gráfica em tela cheia. Sem $WAYLAND_DISPLAY nem $DISPLAY, sai com
# código 1 e explica o motivo.
CMD ["python", "core/main.py"]
