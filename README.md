# HAI - Human-AI Interaction Platform

Plataforma de atividades educacionais de inteligência artificial para um
Raspberry Pi 5 com tela de toque de 1024 × 600. A aplicação abre um menu e
cada atividade é um módulo independente.

| Módulo | Padrão | O que faz | Documentação |
|---|---|---|---|
| **Conversar com a IA** | ativo | O aluno monta uma pergunta com texto, fala (Whisper local) e fotos da webcam; um LLM remoto responde em texto e em voz (Piper). | [modules/chat/README.md](modules/chat/README.md) |
| **Módulo de exemplo** | desativado | Divisores e números primos de um número digitado. Não usa rede nem hardware; serve de modelo para novos módulos. | [modules/exemplo/README.md](modules/exemplo/README.md) |

Para ativar ou desativar um módulo numa instalação, use `[modules]` no
`config/settings.toml` (por exemplo, `exemplo = true`). O padrão de cada um
fica em `REGISTRY`, em `modules/__init__.py`.

Mais documentação

- [docs/architecture.md](docs/architecture.md): inicialização, navegação, serviços compartilhados e ciclo de vida dos módulos.
- [docs/development.md](docs/development.md): convenções, testes e como criar um módulo.

## Requisitos

- Raspberry Pi 5 com Raspberry Pi OS 64-bit (Bookworm) e sessão gráfica. A
  interface é Qt Quick (PySide6), Wayland nativo; também roda em X11.
- Python 3.11 ou superior.
- Tela de toque 1024 × 600 (outros tamanhos funcionam; o layout se ajusta).
- Para o chat: internet e uma chave da API do Google GenAI, webcam USB (câmera
  e microfone) e saída de áudio (HDMI ou P2).

| Recurso | Depende de |
|---|---|
| Interface | sessão gráfica (`$WAYLAND_DISPLAY` ou `$DISPLAY`) e PySide6 (pip) |
| Respostas da IA | internet e `[api] key` em `config/secrets.toml` |
| Entrada por voz | microfone; o modelo Whisper é baixado na primeira vez e depois funciona offline |
| Fotos | webcam em `[camera] device` |
| Resposta em voz | saída de áudio e Piper (ou espeak-ng) |

Sem chave da API, o chat aparece como indisponível no menu e o resto da
aplicação funciona.

## Instalação

```bash
# Pacotes do sistema
sudo apt install -y portaudio19-dev libsndfile1 espeak-ng alsa-utils

# Piper (voz) - Raspberry Pi 5 / arm64
mkdir -p ~/piper/voices && cd ~/piper
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
tar -xzf piper_linux_aarch64.tar.gz
wget -P voices https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
wget -P voices https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json
cd -

# Python
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # inclui PySide6 (Qt Quick e o teclado da tela) e qasync
```

O PySide6 do pip traz o Qt inteiro, com o teclado da tela (Qt Virtual
Keyboard, layout pt-BR). Ainda não foi testado no Pi 5; se o wheel aarch64
der problema, o Pi OS tem os pacotes `python3-pyside6.*` e
`qml6-module-qtquick-virtualkeyboard` no apt (crie a venv com
`--system-site-packages`).

## Configuração

```bash
cp config/settings.example.toml config/settings.toml

cat > config/secrets.toml << 'TOML'
[api]
key = "SUA_CHAVE_AQUI"
TOML
```

Os dois arquivos estão no `.gitignore`; não versione a chave.
`config/settings.example.toml` documenta cada opção:

| Seção | Chaves principais |
|---|---|
| `[api]` | `model`, `timeout_s` (espera máxima por trecho da resposta; padrão 30 s) |
| `[stt]` | `language`, `whisper_model` (tiny, base, small…), `whisper_device`, `whisper_compute_type`, `preload` |
| `[tts]` | `backend` (piper, espeak, pyttsx3), `piper_bin`, `piper_model`, `rate`, `lang` |
| `[display]` | `fullscreen`, `width`, `height`, `on_screen_keyboard`, `open_single_module` |
| `[modules]` | `<id> = true/false` para ativar ou desativar módulos (ex.: `exemplo = true`) |
| `[camera]` | `enabled`, `device`, `width`, `height`, `max_side`, `jpeg_quality`, `warmup_frames`, `save_dir` |

Seções de versões anteriores (`[vad]`, `[ux]`, `display.font_size` etc.) são
ignoradas e podem ser apagadas.

Áudio pelo HDMI, se necessário:

```bash
printf 'defaults.pcm.card 0\ndefaults.ctl.card 0\n' > ~/.asoundrc
aplay -l    # saídas
arecord -l  # entradas
```

## Execução

```bash
python core/main.py                      # tela cheia
python core/main.py --windowed           # em janela (desenvolvimento)
python core/main.py --no-tts             # respostas só em texto
python core/main.py --tts-backend espeak # força o backend de voz
```

F11 alterna a tela cheia; fechar a janela, Ctrl+C ou SIGTERM encerram a
aplicação liberando microfone, áudio e conexões. Sem sessão gráfica, o
programa termina com código 1 e explica o que falta. Com
`[display] open_single_module = true` e um só módulo ativo, ele abre direto.

**Entrada de texto.** Tocar num campo de texto abre o teclado da tela
(Qt Virtual Keyboard em português: segure uma vogal para os acentos). A tela
encolhe para o teclado não cobrir o editor; com ele aberto, o chat mostra
uma prévia do fim da conversa e **▴ Ver tudo**, que fecha o teclado. Quem usa
teclado físico pode desligar o da tela no menu ⋯ do chat (**Teclado na
tela**). Com `[display] on_screen_keyboard = false` ele nem é carregado.

| Teclado físico (chat) | Ação |
|---|---|
| Ctrl+Enter | envia |
| Enter | quebra a linha |
| Esc | cancela a resposta, a gravação, a foto ou a leitura em andamento |
| Tab / Espaço | percorre e aciona os botões principais (anel de foco azul) |
| F11 | alterna a tela cheia |

O motivo de não usar o teclado virtual do sistema está em
[docs/architecture.md](docs/architecture.md#teclado-na-tela).

**Diagnóstico da câmera:**

```bash
python -m vision.camera --list              # índices de câmera que entregam frames
python -m vision.camera --device 0 -o t.jpg # foto de teste, sem a interface
```

### Iniciar com o sistema (quiosque)

No Pi OS Bookworm com labwc, acrescente ao `~/.config/labwc/autostart`:

```bash
/home/pi/HAI-RaspPi-Module/venv/bin/python /home/pi/HAI-RaspPi-Module/core/main.py &
```

Ajuste os caminhos à instalação. Com o Wayfire (versões anteriores do
Bookworm), use a seção `[autostart]` do `~/.config/wayfire.ini`.

## Docker

A imagem roda a interface gráfica usando a sessão gráfica, o áudio e a
webcam do hospedeiro:

```bash
docker build -t hai .

docker run --rm \
  -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY -e XDG_RUNTIME_DIR=/tmp/xdg \
  -v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/tmp/xdg/$WAYLAND_DISPLAY \
  --device /dev/dri --device /dev/snd --device /dev/video0 \
  -v "$PWD/config:/app/config:ro" \
  hai

docker buildx build --platform linux/amd64,linux/arm64 -t hai .
```

`config/` é montada em tempo de execução (o build não copia `settings.toml`
nem `secrets.toml`). A imagem define `PIPER_BIN` e `PIPER_MODEL`, usados quando
o `settings.toml` não informa os caminhos do Piper. Se o hospedeiro usar
PipeWire ou PulseAudio, o acesso direto a `/dev/snd` pode estar ocupado; nesse
caso, repasse o socket do servidor de áudio.

## Testes

```bash
pip install -r requirements-dev.txt
pytest                     # interface incluída: o Qt desenha em memória (offscreen), sem X
ruff check . && ruff format --check .
```

Os testes não usam microfone, câmera, rede nem chave da API. Detalhes em
[docs/development.md](docs/development.md#testes).

## Privacidade

- Conversas, transcrições e fotos ficam só na memória e são apagadas ao sair
  do chat ou tocar em **Nova conversa**.
- O microfone só captura enquanto o botão de falar está pressionado.
- Os logs não contêm perguntas, transcrições, respostas nem imagens.
- Não há telemetria; o único envio externo é a requisição ao LLM configurado.
- `[camera] save_dir` grava fotos em disco para depuração; vazio por padrão.

## Limitações conhecidas

- **Latência do LLM:** o modelo padrão (`gemma-4-26b-a4b-it`) levou de 16 a 43 s
  por resposta nos testes com a API real. Acima de `[api] timeout_s` a tela mostra
  erro e a pergunta volta ao rascunho; use 60 ou mais se isso for frequente.
- **Primeira execução:** o Whisper é baixado da internet. Até terminar, o
  botão de voz mostra "Preparando a voz…"; texto e foto funcionam.
- **Fotos só da webcam:** não há como anexar arquivos.
- **Validação no Pi:** a interface foi testada num PC (GNOME, Wayland e
  XWayland) e nos testes automáticos (offscreen). Ainda falta validar no Pi
  real: o PySide6 do pip no aarch64, a tela de toque e o teclado da tela no
  labwc, o áudio e o tempo de transcrição.
- **Teclado físico com o da tela ligado:** as teclas mortas (´ + a → á) ainda
  não foram conferidas. Se falharem, use `[display] on_screen_keyboard = false`.

## Licenças

O código do projeto é MIT (`LICENSE`). A interface usa o Qt (LGPLv3) e o
**Qt Virtual Keyboard, que é GPLv3**: distribuir a aplicação junto com o
teclado (uma imagem do Pi, por exemplo) segue a GPLv3 no conjunto.
