# Dockerfile — HAI Platform
# Build multi-arch: linux/amd64 (dev/CI) e linux/arm64 (Raspberry Pi 5)

FROM python:3.12-slim

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    portaudio19-dev \
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

# Instala torch CPU antes do resto (evita baixar versão CUDA)
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# secrets.toml deve ser montado em runtime — nunca buildar com ele
VOLUME ["/app/config"]

# Variáveis de ambiente para os caminhos do Piper dentro do container
ENV PIPER_BIN=/opt/piper/piper/piper
ENV PIPER_MODEL=/opt/piper/voices/pt_BR-faber-medium.onnx

CMD ["python", "core/main.py"]
