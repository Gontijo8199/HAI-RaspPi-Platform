#!/usr/bin/env bash
# install.sh — instala a HAI no Raspberry Pi OS 64-bit (Bookworm).
# Uso: ./install.sh   (como usuário normal; pede sudo só para o apt)
# Pode rodar de novo: pula o que já existe e não sobrescreve config/.
set -euo pipefail

cd "$(dirname "$0")"
[ "$(id -u)" -ne 0 ] || { echo "Rode sem sudo: ./install.sh" >&2; exit 1; }

PIPER_DIR="$HOME/piper"
PIPER_REL=https://github.com/rhasspy/piper/releases/download/2023.11.14-2
VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx

case "$(uname -m)" in
    aarch64) PIPER_TAR=piper_linux_aarch64.tar.gz ;;
    x86_64) PIPER_TAR=piper_linux_x86_64.tar.gz ;;
    *) echo "Arquitetura não suportada: $(uname -m) (use o Pi OS 64-bit)" >&2; exit 1 ;;
esac

echo "==> Pacotes do sistema"
sudo apt-get update
# build-essential/python3-dev/portaudio19-dev: compilar o PyAudio (sem wheel aarch64).
sudo apt-get install -y --no-install-recommends \
    python3-venv python3-dev build-essential \
    portaudio19-dev libsndfile1 espeak-ng alsa-utils wget

echo "==> Piper (voz) em $PIPER_DIR"
mkdir -p "$PIPER_DIR/voices"
[ -x "$PIPER_DIR/piper/piper" ] || wget -qO- "$PIPER_REL/$PIPER_TAR" | tar -xz -C "$PIPER_DIR"
[ -s "$PIPER_DIR/voices/pt_BR-faber-medium.onnx" ] || wget -q -O "$PIPER_DIR/voices/pt_BR-faber-medium.onnx" "$VOICE_URL"
[ -s "$PIPER_DIR/voices/pt_BR-faber-medium.onnx.json" ] || wget -q -O "$PIPER_DIR/voices/pt_BR-faber-medium.onnx.json" "$VOICE_URL.json"

echo "==> Ambiente Python (venv)"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "==> Modelo do Treinar reconhecedor (MobileNetV2)"
venv/bin/python -m modules.treinar_imagem.embedder --download

echo "==> Configuração"
if [ ! -f config/settings.toml ]; then
    # O exemplo aponta para /home/pi/piper; ajusta para o usuário atual.
    sed "s#/home/pi/piper#$PIPER_DIR#g" config/settings.example.toml > config/settings.toml
    echo "    criado config/settings.toml"
fi
if [ ! -f config/secrets.toml ]; then
    printf '[api]\nkey = "SUA_CHAVE_AQUI"\n' > config/secrets.toml
    chmod 600 config/secrets.toml
    echo "    criado config/secrets.toml — coloque a chave da API do Google GenAI nele"
fi

echo
echo "Pronto. Para abrir: $PWD/venv/bin/python $PWD/core/main.py"
