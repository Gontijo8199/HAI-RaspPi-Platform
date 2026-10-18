"""
Gravação "segurar para falar" da interface de toque (módulo de conversa).

Design (mesmo MicrophoneStream de stt/audio_stream.py, sem VAD):
- open() abre o microfone e o deixa PAUSADO no nível do PortAudio: nada é
  capturado nem retido até o aluno segurar o botão.
- start() retoma a captura e acumula os chunks numa task do event loop.
- stop() pausa de novo e devolve o PCM-16 gravado; discard() joga fora.
- close() fecha o dispositivo — chamado quando o aluno sai do módulo.
- A transcrição fica a cargo do WhisperEngine compartilhado (core/services.py),
  então o modelo não é recarregado a cada entrada no módulo.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable

from .audio_stream import MicrophoneStream

logger = logging.getLogger(__name__)


class MicrophoneError(RuntimeError):
    """Microfone ausente, ocupado ou recusado pelo sistema."""


class VoiceRecorder:
    """Gravador sob demanda, com o microfone pausado entre as gravações.

    Parâmetros
    ----------
    sample_rate, chunk_samples : int
        Formato pedido ao PortAudio (16 kHz mono é o que o Whisper espera).
    device_index : int | None
        Índice do dispositivo PyAudio. None usa o padrão do sistema.
    min_seconds : float
        Gravações mais curtas que isso são tratadas como toque acidental.
    mic_factory : callable
        Construtor do microfone (injetável nos testes).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_samples: int = 512,
        device_index: int | None = None,
        min_seconds: float = 0.3,
        mic_factory: Callable[..., MicrophoneStream] = MicrophoneStream,
    ):
        self.sample_rate = sample_rate
        self._chunk_samples = chunk_samples
        self._device_index = device_index
        self._min_bytes = int(min_seconds * sample_rate) * 2  # PCM-16 mono
        self._mic_factory = mic_factory
        self._mic: MicrophoneStream | None = None
        self._chunks: list[bytes] = []
        self._collector: asyncio.Task | None = None

    @property
    def is_open(self) -> bool:
        return self._mic is not None

    @property
    def recording(self) -> bool:
        return self._collector is not None and not self._collector.done()

    def open(self) -> None:
        """Abre o microfone (pausado). Idempotente. Levanta MicrophoneError."""
        if self._mic is not None:
            return
        loop = asyncio.get_running_loop()
        try:
            mic = self._mic_factory(
                sample_rate=self.sample_rate,
                chunk_samples=self._chunk_samples,
                preroll_ms=0,
                device_index=self._device_index,
            )
            mic.start(loop)
            mic.pause()
        except Exception as exc:
            logger.warning("Microfone indisponível: %s", exc)
            raise MicrophoneError(
                "Não consegui abrir o microfone. Ele está conectado e livre?"
            ) from exc
        self._mic = mic

    def start(self) -> None:
        """Começa a gravar (o microfone precisa estar aberto)."""
        if self._mic is None:
            raise MicrophoneError("O microfone não está aberto.")
        if self.recording:
            return
        self._chunks = []
        self._mic.resume()
        self._collector = asyncio.create_task(self._collect(self._mic), name="voice-recorder")

    async def stop(self) -> bytes | None:
        """Encerra a gravação. Retorna o PCM gravado, ou None se for curto demais."""
        await self._halt()
        audio = b"".join(self._chunks)
        self._chunks = []
        if len(audio) < self._min_bytes:
            logger.debug("Gravação curta demais (%d bytes), descartada.", len(audio))
            return None
        return audio

    async def discard(self) -> None:
        """Interrompe a gravação em andamento e descarta o áudio."""
        await self._halt()
        self._chunks = []

    async def close(self) -> None:
        """Descarta qualquer gravação e fecha o dispositivo. Idempotente."""
        await self.discard()
        mic, self._mic = self._mic, None
        if mic is not None:
            try:
                mic.stop()
            except Exception as exc:
                logger.debug("Erro ao fechar o microfone: %s", exc)

    async def _halt(self) -> None:
        collector, self._collector = self._collector, None
        if collector is not None and not collector.done():
            collector.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await collector
        if self._mic is not None:
            self._mic.pause()

    async def _collect(self, mic: MicrophoneStream) -> None:
        while True:
            self._chunks.append(await mic.read_chunk())
