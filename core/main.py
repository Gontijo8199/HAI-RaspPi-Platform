"""
python core/main.py          # VAD automático
python core/main.py --ptt    # Push-to-Talk via Enter

Arquitetura:
- Event loop asyncio como espinha dorsal; nada bloqueia o loop principal.
- STT, LLM e TTS rodam como tasks/threads concorrentes.
- HAIPipeline orquestra o fluxo utterance -> LLM stream -> TTS.
- LLM usa streaming: o TTS começa a falar antes da resposta terminar.
- TTS roda em thread daemon: não bloqueia capturas futuras.
"""

import argparse
import asyncio
import logging
import sys
import tomllib
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from api.llm_client import LLMClient
from core.pipeline import HAIPipeline
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
    return parser.parse_args()


def display_response(text: str) -> None:
    # TODO: integrar com display/driver quando disponível
    pass


async def async_main(ptt: bool, tts_backend: str | None, no_tts: bool) -> None:
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

    # TTS (thread daemon)
    if no_tts:
        tts = None
        logger.info("TTS desativado por --no-tts.")
    else:
        tts_cfg = settings.get("tts", {})
        backend = tts_backend or tts_cfg.get("backend", "piper")
        tts = TTSSpeaker(
            backend=backend,
            piper_bin=tts_cfg.get("piper_bin", "/home/rafa/piper/piper/piper"),
            piper_model=tts_cfg.get(
                "piper_model", "/home/rafa/piper/voices/pt_BR-faber-medium.onnx"
            ),
            rate=tts_cfg.get("rate", 160),
            lang=tts_cfg.get("lang", "pt-br"),
        )

    # LLM client com streaming
    llm_client = LLMClient(api_key=api_key, model=model)

    # Pipeline orquestrador
    pipeline = HAIPipeline(
        llm_client=llm_client,
        tts=tts if tts else _NullTTS(),
        display_fn=display_response,
    )

    # STT (VAD ou PTT)
    if ptt:
        stt = PttStream(
            language=lang,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            whisper_compute_type=whisper_compute_type,
        )
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

    modo = "PTT (Enter)" if ptt else "VAD automático"
    print(f"Iniciando captura de voz [{modo}]... (Pressione Ctrl+C para sair)")
    await stt.start()

    try:
        while True:
            # Aguarda próximo utterance; não bloqueia tasks em andamento
            utterance = await stt.get_utterance()
            # Dispara pipeline sem await, continua ouvindo imediatamente
            pipeline.process_utterance(utterance)

    except asyncio.CancelledError:
        logger.info("Loop principal cancelado.")
    finally:
        print("\nDesligando...")
        stt.stop()
        await pipeline.wait_pending()
        if tts:
            tts.shutdown()


class _NullTTS:
    def speak(self, text: str) -> None:
        pass

    async def speak_stream(self, token_stream) -> None:
        async for _ in token_stream:
            pass

    def stop_speaking(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(
            async_main(
                ptt=args.ptt,
                tts_backend=args.tts_backend,
                no_tts=args.no_tts,
            )
        )
    except KeyboardInterrupt:
        print("\nEncerrando o programa.")


if __name__ == "__main__":
    main()
