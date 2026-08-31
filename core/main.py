"""
python core/main.py          # VAD automático
python core/main.py --ptt    # Push-to-Talk via Enter

Arquitetura:
- Event loop asyncio como espinha dorsal; nada bloqueia o loop principal.
- STT, LLM e TTS rodam como tasks/threads concorrentes.
- HAIPipeline orquestra o fluxo utterance -> LLM stream -> TTS.
- LLM usa streaming: o TTS começa a falar antes da resposta terminar.
- TTS roda em thread daemon: não bloqueia capturas futuras.

Controle (UX):
- Turnos controlados: enquanto o tutor processa/responde, o microfone fica
  pausado no nível do PortAudio (nada é capturado nem retido).
- A tecla de cancelamento (padrão Espaço; configurável em [ux] cancel_key)
  interrompe imediatamente o pedido em andamento: corta o stream do LLM na
  camada de rede, mata o áudio do TTS e limpa as tasks do pipeline. Não é
  Esc de propósito: o display Tk usa Esc para sair da tela cheia.
- No modo PTT, a tecla de cancelamento durante a gravação descarta o áudio.
- Hotkeys rodam numa thread leitora (termios cbreak) e chegam ao event loop
  por fila assíncrona; sem TTY (CI/docker), tudo degrada sem teclado.
"""

import argparse
import asyncio
import logging
import sys
import tomllib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from api.llm_client import LLMClient
from core import ui
from core.hotkeys import HotkeyListener, parse_key, pretty_key
from core.pipeline import HAIPipeline
from display.markdown_display import MarkdownDisplay
from stt.capture import WhisperStream
from stt.ptt import PttStream
from tts.speaker import TTSSpeaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config/settings.toml"
SECRETS_PATH = Path(__file__).parent.parent / "config/secrets.toml"

_TTS_DRAIN_TIMEOUT_S = 120.0


class _Quit(Exception):
    """Sinaliza desligamento elegante acionado pelo usuário."""


def load_config() -> tuple[dict, dict]:
    with open(CONFIG_PATH, "rb") as f:
        settings = tomllib.load(f)
    with open(SECRETS_PATH, "rb") as f:
        secrets = tomllib.load(f)
    return settings, secrets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tutor Virtual HAI")
    parser.add_argument(
        "--ptt",
        action="store_true",
        help="Ativa o modo Push-to-Talk (Enter para gravar/parar).",
    )
    parser.add_argument(
        "--tts-backend",
        default=None,
        choices=["pyttsx3", "espeak"],
        help="Backend de síntese de voz (padrão: pyttsx3).",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Desativa TTS (apenas texto no terminal).",
    )
    parser.add_argument(
        "--allow-barge-in",
        action="store_true",
        help="Mantém o microfone capturando enquanto o tutor responde "
        "(o padrão é pausar o mic durante cada resposta).",
    )
    return parser.parse_args()


def _build_tts(settings: dict, tts_backend: str | None, no_tts: bool) -> TTSSpeaker | None:
    if no_tts:
        logger.info("TTS desativado por --no-tts.")
        return None
    tts_cfg = settings.get("tts", {})
    backend = tts_backend or tts_cfg.get("backend", "piper")
    return TTSSpeaker(
        backend=backend,
        piper_bin=tts_cfg.get("piper_bin", "/home/rafa/piper/piper/piper"),
<<<<<<< HEAD
        piper_model=tts_cfg.get("piper_model", "/home/rafa/piper/voices/pt_BR-faber-medium.onnx"),
=======
        piper_model=tts_cfg.get(
            "piper_model", "/home/rafa/piper/voices/pt_BR-faber-medium.onnx"
        ),
>>>>>>> refs/remotes/origin/main
        rate=tts_cfg.get("rate", 160),
        lang=tts_cfg.get("lang", "pt-br"),
    )


class _NullTTS:
    def speak(self, text: str) -> None:
        pass

    def stop_speaking(self) -> None:
        pass

    def is_busy(self) -> bool:
        return False

    def shutdown(self) -> None:
        pass


async def _wait_tts_drain(tts) -> None:
    """Aguarda o TTS terminar de falar a fila atual (para só então retomar o mic)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _TTS_DRAIN_TIMEOUT_S
    while tts.is_busy():
        if loop.time() > deadline:
            logger.warning("Timeout aguardando o fim da fala do TTS.")
            tts.stop_speaking()
            return
        await asyncio.sleep(0.05)


async def async_main(
    ptt: bool, tts_backend: str | None, no_tts: bool, allow_barge_in: bool
) -> None:
    settings, secrets = load_config()

    api_key = secrets["api"]["key"]
    if not api_key:
        raise ValueError("api.key não definida em config/secrets.toml")

    model = settings["api"].get("model", "gemma-4-26b-a4b-it")
    lang = settings["stt"].get("language", "pt")

    whisper_model = settings.get("stt", {}).get("whisper_model", "small")
    whisper_device = settings.get("stt", {}).get("whisper_device", "cpu")
    whisper_compute_type = settings.get("stt", {}).get("whisper_compute_type", "int8")

    vad_cfg = settings.get("vad", {})
    vad_threshold = vad_cfg.get("threshold", 0.5)
    preroll_ms = vad_cfg.get("preroll_ms", 500)
    silence_ms = vad_cfg.get("silence_ms", 700)
    interim_interval_ms = vad_cfg.get("interim_interval_ms", 1500)

    mute_during_response = (
        settings.get("ux", {}).get("mute_while_responding", True) and not allow_barge_in
    )

    try:
        cancel_key = parse_key(settings.get("ux", {}).get("cancel_key", "space"))
    except ValueError as exc:
        logger.warning("%s Usando Espaço como tecla de cancelamento.", exc)
        cancel_key = "space"
    tecla_cancel = pretty_key(cancel_key)
    ui.set_cancel_hint(tecla_cancel)

    tts = _build_tts(settings, tts_backend, no_tts) or _NullTTS()

    # LLM client com streaming
    llm_client = LLMClient(api_key=api_key, model=model)

    # Display: janela X11 no HDMI com resposta em Markdown + flash-card do tópico. Se desativado ou sem servidor X, cai em modo headless sozinho.
    display_cfg = settings.get("display", {})
    if display_cfg.get("enabled", True):
        display = MarkdownDisplay(
            fullscreen=display_cfg.get("fullscreen", True),
            width=display_cfg.get("width", 1024),
            height=display_cfg.get("height", 600),
            font_size=display_cfg.get("font_size", 20),
            flashcard_width=display_cfg.get("flashcard_width", 340),
        )
        if not display.available:
            logger.warning(
                "Display X11 indisponível — rodando sem exibição gráfica "
                "(resposta continua no terminal e no áudio)."
            )
    else:
        display = None
        logger.info("Display desativado via config/settings.toml [display] enabled=false.")

    # Pipeline orquestrador
    pipeline = HAIPipeline(
        llm_client=llm_client,
        tts=tts,
        display=display,
    )

    # Teclas de controle (cancelamento/Ctrl+C). Sem TTY, degrada sem hotkeys.
    hotkeys = HotkeyListener()
    await hotkeys.start()

    # STT (VAD ou PTT)
    if ptt:
        stt = PttStream(
            language=lang,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            whisper_compute_type=whisper_compute_type,
            hotkeys=hotkeys,
            cancel_key=cancel_key,
        )
        mode = "PTT (Enter)"
        controls = [
            ("Enter", "começar / encerrar gravação"),
            (tecla_cancel, "descartar gravação • cancelar resposta"),
            ("Ctrl+C", "encerrar o programa"),
        ]
    else:
        stt = WhisperStream(
            language=lang,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            whisper_compute_type=whisper_compute_type,
            vad_threshold=vad_threshold,
            preroll_ms=preroll_ms,
            silence_ms=silence_ms,
            interim_interval_ms=interim_interval_ms,
        )
        mode = "VAD automático"
        controls = [
            ("Falar", "o tutor detecta a voz automaticamente"),
            ('Dizer "resetar"', "limpa o histórico da sessão"),
            (tecla_cancel, "cancelar resposta em andamento (fala + LLM)"),
            ("Ctrl+C", "encerrar o programa"),
        ]

    ui.banner(mode, controls)
    if mute_during_response:
        ui.dim("Mic pausado automaticamente enquanto o tutor responde.\n")

    await stt.start()

    quit_requested = False
    try:
        while not quit_requested:
            # ---------- Fase de escuta ----------
            utterance, key = await _listen_once(stt, hotkeys)

            if key == "ctrl+c":
                quit_requested = True
                break
            if key == cancel_key:
                _handle_cancel(pipeline, tts)
                ui.listening()
                continue
            if utterance is None:
                ui.listening()
                continue

            # ---------- Turno do tutor ----------
            turn = asyncio.create_task(
                _run_turn(pipeline, stt, tts, display, utterance, mute_during_response)
            )
            quit_requested = await _watch_turn(turn, hotkeys, pipeline, tts, cancel_key)

    except _Quit:
        pass
    except asyncio.CancelledError:
        logger.info("Loop principal cancelado.")
    finally:
        print("\nDesligando...")
        hotkeys.stop()  # restaura o terminal antes de qualquer coisa
        stt.stop()
        await pipeline.wait_pending()
        tts.shutdown()
        if display:
            display.shutdown()


async def _listen_once(stt, hotkeys: HotkeyListener) -> tuple[str | None, str | None]:
    """Espera simultaneamente um utterance e uma tecla. Retorna o que chegar."""
    utterance_task = asyncio.create_task(stt.get_utterance(), name="await-utterance")
    key_task = (
<<<<<<< HEAD
        asyncio.create_task(hotkeys.get_key(), name="await-key") if hotkeys.available else None
=======
        asyncio.create_task(hotkeys.get_key(), name="await-key")
        if hotkeys.available
        else None
>>>>>>> refs/remotes/origin/main
    )
    waiters = {utterance_task} | ({key_task} if key_task else set())

    done, _pending = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)

    utterance: str | None = None
    key: str | None = None
    for task in (utterance_task, key_task):
        if task is None:
            continue
        if task in done:
            if task is utterance_task:
                utterance = task.result()
            else:
                key = task.result()
        else:
            task.cancel()

    # Evita teclas fantasma acumuladas durante a escuta.
    hotkeys.clear()
    return utterance, key


async def _watch_turn(
    turn: asyncio.Task,
    hotkeys: HotkeyListener,
    pipeline,
    tts,
    cancel_key: str = "space",
) -> bool:
    """Vigia o turno até ele acabar, tratando cancelamento/Ctrl+C no caminho.

    Retorna True se o usuário pediu para sair.
    """
    while True:
        key_task = (
<<<<<<< HEAD
            asyncio.create_task(hotkeys.get_key(), name="turn-key") if hotkeys.available else None
=======
            asyncio.create_task(hotkeys.get_key(), name="turn-key")
            if hotkeys.available
            else None
>>>>>>> refs/remotes/origin/main
        )
        waiters = {turn} | ({key_task} if key_task else set())

        done, _pending = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)

        key: str | None = None
        if key_task is not None:
            if key_task in done:
                key = key_task.result()
            else:
                key_task.cancel()

        if turn in done:
            try:
                turn.result()
            except asyncio.CancelledError:
                pass  # turno cancelado (o pipeline já reportou)
            except Exception as exc:
                ui.error(f"[ERRO] {exc}")
            return False

        if key == "ctrl+c":
            pipeline.cancel_active()
            return True

        if key == cancel_key:
            _handle_cancel(pipeline, tts)
            # continua vigiando até o turno encerrar de fato


def _handle_cancel(pipeline, tts) -> None:
    """Tecla de cancelamento: interrompe o que estiver em andamento.

    - Turno do pipeline em curso: ele mesmo imprime o ✗ na linha do texto.
    - Só o TTS drenando (fim da resposta): corta o áudio e reporta.
    - Nada acontecendo: avisa e segue.
    """
    turn_busy = pipeline.busy
    tts_busy = tts.is_busy()
    pipeline.cancel_active()
    if turn_busy:
        return  # feedback já dado pelo pipeline
    if tts_busy:
        ui.cancelled()
    else:
        ui.dim("Nada em andamento para cancelar.")


async def _run_turn(
    pipeline: HAIPipeline,
    stt,
    tts,
    display: MarkdownDisplay | None,
    utterance: str,
    mute: bool,
) -> None:
    """Um turno completo: pausa o mic, processa, espera a fala acabar, retoma."""
    muted = False
    if mute:
        stt.pause()
        ui.muted_mic()
        muted = True
    try:
        await pipeline.run_turn(utterance)
        await _wait_tts_drain(tts)
    finally:
        if muted:
            stt.resume()
        if display:
            try:
                display.show_status("Ouvindo...")
            except Exception:
                pass
        ui.listening()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(
            async_main(
                ptt=args.ptt,
                tts_backend=args.tts_backend,
                no_tts=args.no_tts,
                allow_barge_in=args.allow_barge_in,
            )
        )
    except KeyboardInterrupt:
        print("\nEncerrando o programa.")


if __name__ == "__main__":
    main()
